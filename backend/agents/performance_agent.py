from __future__ import annotations

import logging

from backend.models.schemas import (
    ComplexityInfo,
    PerformanceIssue,
    PerformanceReport,
)
from backend.utils.llm_client import call_llm_json
from backend.utils.severity_scorer import score_from_findings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a principal performance engineer who has worked at high-scale companies
(Google, Meta, Netflix). You profile code the way APM tools do — finding bottlenecks before they hit production.

Analyze the provided code for performance issues and return ONLY this JSON (no other text):
{
  "complexity_analysis": [
    {
      "function_name": "<name>",
      "time_complexity": "<e.g. O(n²)>",
      "space_complexity": "<e.g. O(n)>",
      "explanation": "<why this complexity, what drives it>"
    }
  ],
  "issues": [
    {
      "line_number": <integer or null>,
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFO>",
      "title": "<short title>",
      "description": "<detailed explanation of the bottleneck>",
      "before_code": "<problematic code snippet>",
      "after_code": "<optimised replacement>",
      "expected_improvement": "<e.g. 'Reduces O(n²) to O(n log n) for large datasets'>"
    }
  ],
  "summary": "<1-2 sentence overall performance assessment>"
}

Look for ALL of the following:
- Quadratic or worse time complexity hidden in loops (nested loops over large data)
- N+1 query problems (database calls inside loops)
- Unnecessary repeated computation (results that should be cached/memoized)
- Inefficient data structure choices (list when set/dict is needed)
- Memory leaks (unbounded growth, circular references, unclosed resources)
- Blocking I/O in async contexts
- Unnecessary string concatenation in loops (use join)
- Missing indexes implied by query patterns
- Redundant database roundtrips (batch instead)
- Object creation inside tight loops
- Synchronous calls that could be parallelised
- Regex compilation inside loops (compile once)

Be specific: always include before/after code for each issue.
Return ONLY valid JSON. No markdown. No prose outside the JSON."""


async def analyze(code: str, language: str) -> PerformanceReport:
    user_prompt = f"Language: {language}\n\nCode to profile:\n```\n{code}\n```"
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
        issues = [PerformanceIssue(**i) for i in data.get("issues", [])]
        complexity = [ComplexityInfo(**c) for c in data.get("complexity_analysis", [])]
        severities = [i.severity for i in issues]
        return PerformanceReport(
            issues=issues,
            complexity_analysis=complexity,
            summary=data.get("summary", ""),
            score=score_from_findings(severities),
        )
    except Exception as exc:
        logger.error("Performance agent failed: %s", exc)
        return PerformanceReport(
            issues=[],
            complexity_analysis=[],
            summary="Performance analysis could not be completed.",
            score=50.0,
            error=str(exc),
        )
