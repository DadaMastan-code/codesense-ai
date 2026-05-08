from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from backend.config import get_settings
from backend.evolution.tracker import save_review
from backend.pipelines.orchestrator import run_full_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["GitHub Webhook"])

_ACCEPT_ACTIONS = {"opened", "synchronize", "reopened"}


# ── Signature verification ────────────────────────────────────────────────────

def _verify_signature(payload: bytes, header: str, secret: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)


# ── GitHub API helpers ────────────────────────────────────────────────────────

async def _fetch_pr_diff(pr_url: str, token: str) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(pr_url, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        return resp.text


async def _post_comment(comments_url: str, token: str, body: str) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(comments_url, headers=headers, json={"body": body})
        resp.raise_for_status()


# ── PR review comment formatter ───────────────────────────────────────────────

def _format_review_comment(results: Any, elapsed: float, pr_title: str) -> str:
    score = results.score
    sec = results.security
    perf = results.performance
    arch = results.architecture
    tests = results.tests
    docs = results.documentation

    rating_emoji = {
        "EXCELLENT": "🟢",
        "GOOD": "🔵",
        "NEEDS WORK": "🟡",
        "POOR": "🟠",
        "CRITICAL": "🔴",
    }.get(score.rating.value, "⚪")

    critical_findings = [f for f in sec.findings if f.severity.value == "CRITICAL"]
    high_findings = [f for f in sec.findings if f.severity.value == "HIGH"]

    lines = [
        "## 🔍 CodeSense AI Review",
        "",
        f"**{rating_emoji} Overall Score: `{score.total:.0f}/100`** — {score.rating.value}",
        "",
        "| Agent | Score | Issues |",
        "|---|---|---|",
        f"| 🔒 Security | `{score.security:.0f}/100` | {len(sec.findings)} findings |",
        f"| ⚡ Performance | `{score.performance:.0f}/100` | {len(perf.issues)} findings |",
        f"| 🏗️ Architecture | `{score.architecture:.0f}/100` | {len(arch.suggestions)} suggestions |",
        f"| 🧪 Tests | — | {len(tests.test_cases)} test cases generated |",
        f"| 📝 Docs | `{score.documentation:.0f}/100` | {len(docs.issues)} issues |",
        "",
    ]

    if critical_findings or high_findings:
        lines.append("### 🚨 Critical & High Severity Issues")
        lines.append("")
        for f in (critical_findings + high_findings)[:5]:
            lines.append(f"**[{f.severity.value}] {f.title}**")
            if f.line_number:
                lines.append(f"> Line {f.line_number}: {f.description}")
            else:
                lines.append(f"> {f.description}")
            lines.append(f"> **Fix:** {f.fix_recommendation}")
            lines.append(f"> **OWASP:** [{f.owasp_category}]({f.owasp_reference})")
            lines.append("")

    fix = results.fix
    if fix.diff:
        lines.append("### ✅ Auto-Fix Preview")
        lines.append("")
        lines.append("```diff")
        lines.append(fix.diff[:2000])
        lines.append("```")
        lines.append("")

    lines.append(f"<sub>Reviewed by [CodeSense AI](https://github.com/DadaMastan-code/codesense-ai) in {elapsed:.1f}s · 6 agents · LangGraph orchestration</sub>")

    return "\n".join(lines)


# ── Background task: full review ──────────────────────────────────────────────

async def _run_pr_review(
    pr_url: str,
    comments_url: str,
    pr_number: int,
    pr_title: str,
    repo_full_name: str,
    token: str,
    language: str | None = None,
) -> None:
    try:
        diff = await _fetch_pr_diff(pr_url, token)
        if not diff.strip():
            logger.info("PR #%d has empty diff — skipping review", pr_number)
            return

        # Cap diff size to avoid token limits
        code_to_analyze = diff[:30_000]

        results = await run_full_analysis(code_to_analyze, language, context=f"GitHub PR #{pr_number}: {pr_title}")
        elapsed = results.analysis_time_seconds

        # Post the review comment
        comment = _format_review_comment(results, elapsed, pr_title)
        await _post_comment(comments_url, token, comment)

        # Save to evolution tracker
        critical_count = sum(
            1 for f in results.security.findings
            if f.severity.value == "CRITICAL"
        )
        total_issues = (
            len(results.security.findings)
            + len(results.performance.issues)
            + len(results.architecture.suggestions)
        )
        await save_review(
            repo=repo_full_name,
            pr_number=pr_number,
            pr_title=pr_title,
            overall_score=results.score.total,
            security_score=results.score.security,
            performance_score=results.score.performance,
            architecture_score=results.score.architecture,
            test_score=50.0,
            docs_score=results.score.documentation,
            critical_issues=critical_count,
            total_issues=total_issues,
            language=results.language,
            analysis_time=elapsed,
        )

        logger.info("PR review complete | repo=%s pr=%d score=%.1f", repo_full_name, pr_number, results.score.total)

    except Exception as exc:
        logger.error("PR review failed | repo=%s pr=%d | error=%s", repo_full_name, pr_number, exc)
        try:
            err_comment = f"## 🔍 CodeSense AI\n\n❌ Review failed: `{exc}`\n\nPlease check the CodeSense API logs."
            await _post_comment(comments_url, token, err_comment)
        except Exception:
            pass


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/github")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict[str, Any]:
    settings = get_settings()
    payload = await request.body()

    # Signature verification (skip if no secret configured — useful for dev)
    if settings.github_webhook_secret and not _verify_signature(payload, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    data = await request.json()
    action = data.get("action", "")

    if action not in _ACCEPT_ACTIONS:
        return {"status": "ignored", "reason": f"action={action}"}

    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN not configured")

    if not settings.has_any_llm_key:
        raise HTTPException(status_code=503, detail="No LLM API key configured")

    pr = data.get("pull_request", {})
    pr_url = pr.get("url", "")
    comments_url = pr.get("comments_url", "")
    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    repo_full_name = data.get("repository", {}).get("full_name", "unknown/unknown")

    logger.info("PR webhook received | repo=%s pr=%d action=%s", repo_full_name, pr_number, action)

    background_tasks.add_task(
        _run_pr_review,
        pr_url=pr_url,
        comments_url=comments_url,
        pr_number=pr_number,
        pr_title=pr_title,
        repo_full_name=repo_full_name,
        token=settings.github_token,
    )

    return {"status": "review_queued", "pr": pr_number, "repo": repo_full_name}
