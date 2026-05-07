from __future__ import annotations

import logging

from backend.models.schemas import FixReport
from backend.utils.diff_generator import generate_diff
from backend.utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a principal software engineer doing a thorough code review.
You receive a list of issues found by a security, performance, and architecture review team,
and you produce a corrected version of the code that addresses ALL of them.

Return ONLY this JSON (no other text):
{
  "fixed_code": "<the complete corrected code — escape newlines as \\n>",
  "explanation": "<2-3 sentences explaining the overall approach to the fixes>",
  "changes": [
    "<concise description of each individual change made>"
  ]
}

Rules:
- Address EVERY issue listed, in priority order (CRITICAL first)
- Do NOT introduce new issues while fixing existing ones
- Preserve the original code's logic and intent — only change what is broken/risky
- Add security fixes: parameterised queries, input validation, secret management
- Add performance fixes: better algorithms, caching, efficient data structures
- Improve architecture only where necessary to fix the identified issues
- The fixed_code must be complete and runnable — not a snippet
- The fixed_code field must be a valid JSON string (\\n for newlines, \\" for quotes)
- changes[] should have one entry per logical change, ordered most-important-first

Return ONLY valid JSON. No markdown. No prose outside the JSON."""


async def apply_fixes(
    code: str, language: str, issues: list[str], original_filename: str = "code"
) -> FixReport:
    issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "General code quality improvement"
    user_prompt = (
        f"Language: {language}\n\n"
        f"Issues to fix:\n{issues_text}\n\n"
        f"Original code:\n```\n{code}\n```"
    )
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt, max_tokens=8192)
        fixed_code = data.get("fixed_code", code)
        diff = generate_diff(code, fixed_code, filename=original_filename)
        return FixReport(
            fixed_code=fixed_code,
            diff=diff,
            explanation=data.get("explanation", ""),
            changes=data.get("changes", []),
        )
    except Exception as exc:
        logger.error("Fix agent failed: %s", exc)
        return FixReport(
            fixed_code=code,
            diff="",
            explanation="Fix generation could not be completed.",
            changes=[],
            error=str(exc),
        )
