from __future__ import annotations

import logging

from backend.models.schemas import DocIssue, DocReport
from backend.utils.llm_client import call_llm_json
from backend.utils.severity_scorer import score_from_findings
from backend.models.schemas import Severity

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior technical writer and developer advocate who believes code
should be self-documenting and readable by any developer joining the team.

Analyze the code for documentation quality and return ONLY this JSON (no other text):
{
  "documented_code": "<the full code with all docstrings/JSDoc added — escape newlines as \\n>",
  "issues": [
    {
      "element": "<function/class/variable name>",
      "issue_type": "<missing_docstring|confusing_name|needs_comment|missing_type_hints>",
      "suggestion": "<specific, actionable suggestion>"
    }
  ],
  "plain_english_summary": "<3-5 sentence plain English explanation of what this code does, for a developer new to the codebase>"
}

Rules for documented_code:
- Add docstrings to EVERY function and class that lacks one
- Python: use Google-style docstrings (Args:, Returns:, Raises:, Example:)
- JavaScript/TypeScript: use JSDoc (@param, @returns, @throws, @example)
- Java: use Javadoc
- Add type hints where missing (Python)
- Rename nothing — only add documentation
- Add inline comments for any non-obvious logic (why, not what)
- The documented_code field must be a valid JSON string (\\n for newlines)

Issues to flag:
- Missing docstrings on any public function or class
- Single-letter variable names (except well-known loops like i, j, k)
- Ambiguous names (data, result, temp, obj, val without context)
- Complex one-liners that need explanation
- Missing return type documentation

Return ONLY valid JSON. No markdown. No prose outside the JSON."""


async def analyze(code: str, language: str) -> DocReport:
    user_prompt = f"Language: {language}\n\nCode to document:\n```\n{code}\n```"
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt, max_tokens=6144)
        issues = [DocIssue(**i) for i in data.get("issues", [])]
        issue_count = len(issues)
        # Penalise missing documentation: each issue costs points
        score = max(0.0, 100.0 - issue_count * 8.0)
        return DocReport(
            documented_code=data.get("documented_code", code),
            issues=issues,
            plain_english_summary=data.get("plain_english_summary", ""),
            score=score,
        )
    except Exception as exc:
        logger.error("Doc agent failed: %s", exc)
        return DocReport(
            documented_code=code,
            issues=[],
            plain_english_summary="Documentation analysis could not be completed.",
            score=50.0,
            error=str(exc),
        )
