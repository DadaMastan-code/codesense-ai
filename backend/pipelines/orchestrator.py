from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.agents import (
    architecture_agent,
    doc_agent,
    fix_agent,
    performance_agent,
    security_agent,
    test_agent,
)
from backend.models.schemas import (
    ArchitectureReport,
    CodeSenseScore,
    DocReport,
    FixReport,
    FullAnalysisResponse,
    PerformanceReport,
    SecurityReport,
    TestReport,
)
from backend.utils.language_detector import detect_language

logger = logging.getLogger(__name__)


def _safe(result: Any, default: Any) -> Any:
    """Return result unless it's an exception, in which case return default."""
    return default if isinstance(result, BaseException) else result


async def run_full_analysis(
    code: str,
    language: str | None = None,
    context: str | None = None,
) -> FullAnalysisResponse:
    start = time.monotonic()
    lang = language or detect_language(code)
    logger.info("Starting full analysis | language=%s | code_length=%d", lang, len(code))

    # Run the five analysis agents in parallel
    (
        sec_result,
        perf_result,
        arch_result,
        test_result,
        doc_result,
    ) = await asyncio.gather(
        security_agent.analyze(code, lang),
        performance_agent.analyze(code, lang),
        architecture_agent.analyze(code, lang),
        test_agent.suggest(code, lang),
        doc_agent.analyze(code, lang),
        return_exceptions=True,
    )

    sec: SecurityReport = _safe(sec_result, SecurityReport(score=50.0, error="Agent failed"))
    perf: PerformanceReport = _safe(perf_result, PerformanceReport(score=50.0, error="Agent failed"))
    arch: ArchitectureReport = _safe(arch_result, ArchitectureReport(score=50.0, error="Agent failed"))
    tests: TestReport = _safe(test_result, TestReport(error="Agent failed"))
    docs: DocReport = _safe(doc_result, DocReport(score=50.0, error="Agent failed"))

    # Collect all issue descriptions for the fix agent
    all_issues: list[str] = []
    for finding in sec.findings:
        all_issues.append(f"[SECURITY {finding.severity}] {finding.title}: {finding.description}")
    for issue in perf.issues:
        all_issues.append(f"[PERFORMANCE {issue.severity}] {issue.title}: {issue.description}")
    for suggestion in arch.suggestions:
        all_issues.append(f"[ARCHITECTURE {suggestion.severity}] {suggestion.title}: {suggestion.description}")

    fix_result = await fix_agent.apply_fixes(code, lang, all_issues[:20])  # cap to 20 issues
    fix: FixReport = _safe(fix_result, FixReport(fixed_code=code, error="Fix agent failed"))

    score = CodeSenseScore.compute(
        security=sec.score,
        performance=perf.score,
        architecture=arch.score,
        documentation=docs.score,
    )

    elapsed = round(time.monotonic() - start, 2)
    logger.info("Analysis complete | score=%.1f | elapsed=%.2fs", score.total, elapsed)

    return FullAnalysisResponse(
        language=lang,
        score=score,
        security=sec,
        performance=perf,
        architecture=arch,
        tests=tests,
        documentation=docs,
        fix=fix,
        analysis_time_seconds=elapsed,
        metadata={"context": context or ""},
    )


async def stream_analysis(
    code: str,
    language: str | None = None,
    context: str | None = None,
):
    """Async generator that yields (agent_name, result) tuples as each agent completes."""
    lang = language or detect_language(code)
    yield ("language_detected", {"language": lang})

    agents = [
        ("security", security_agent.analyze(code, lang)),
        ("performance", performance_agent.analyze(code, lang)),
        ("architecture", architecture_agent.analyze(code, lang)),
        ("tests", test_agent.suggest(code, lang)),
        ("documentation", doc_agent.analyze(code, lang)),
    ]

    results: dict[str, Any] = {}
    tasks = {name: asyncio.create_task(coro) for name, coro in agents}

    pending = set(tasks.values())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            # Find which agent this task belongs to
            for name, t in tasks.items():
                if t is task:
                    try:
                        results[name] = task.result()
                    except Exception as exc:
                        results[name] = {"error": str(exc)}
                    yield (name, results[name])
                    break

    # Run fix agent after all others complete
    all_issues: list[str] = []
    sec = results.get("security")
    perf = results.get("performance")
    arch = results.get("architecture")
    if isinstance(sec, SecurityReport):
        for f in sec.findings:
            all_issues.append(f"[SECURITY {f.severity}] {f.title}")
    if isinstance(perf, PerformanceReport):
        for i in perf.issues:
            all_issues.append(f"[PERFORMANCE {i.severity}] {i.title}")
    if isinstance(arch, ArchitectureReport):
        for s in arch.suggestions:
            all_issues.append(f"[ARCHITECTURE {s.severity}] {s.title}")

    fix = await fix_agent.apply_fixes(code, lang, all_issues[:20])
    yield ("fix", fix)
