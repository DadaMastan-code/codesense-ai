from __future__ import annotations

import logging

from backend.models.schemas import (
    ArchitectureReport,
    ArchitectureSuggestion,
    OverallRating,
    SolidPrinciple,
)
from backend.utils.llm_client import call_llm_json
from backend.utils.severity_scorer import score_from_findings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a staff software architect with 15+ years of experience designing
systems at scale. You review code for structural quality the way a principal engineer would
before approving a major PR — evaluating SOLID principles, design patterns, and long-term maintainability.

Analyze the code architecture and return ONLY this JSON (no other text):
{
  "rating": "<EXCELLENT|GOOD|NEEDS WORK|POOR>",
  "solid_principles": [
    {
      "principle": "<Single Responsibility|Open/Closed|Liskov Substitution|Interface Segregation|Dependency Inversion>",
      "passed": <true|false>,
      "explanation": "<specific observation about this code>"
    }
  ],
  "suggestions": [
    {
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFO>",
      "title": "<short title>",
      "description": "<detailed description of the architectural issue>",
      "pattern_suggestion": "<specific design pattern or refactoring approach that applies>"
    }
  ],
  "design_patterns": ["<patterns that would improve this code, e.g. Factory, Strategy, Repository>"],
  "summary": "<2-3 sentence architectural assessment with justification for the rating>"
}

Evaluate ALL of the following:
- Single Responsibility: does each class/function do exactly one thing?
- Open/Closed: can behaviour be extended without modifying existing code?
- Liskov Substitution: are subclasses truly substitutable for their parents?
- Interface Segregation: are interfaces lean and focused?
- Dependency Inversion: are high-level modules independent of low-level details?
- DRY violations: duplicated logic that should be abstracted
- God classes/functions: classes doing too many unrelated things
- Deeply nested conditionals (arrow anti-pattern)
- Tight coupling between components
- Missing abstractions / leaky abstractions
- Inappropriate use of inheritance vs composition
- Hard-coded configuration that should be injected
- Missing error boundary / separation of error handling

Rate conservatively — only give EXCELLENT if the code is genuinely exemplary.
Return ONLY valid JSON. No markdown. No prose outside the JSON."""

_RATING_MAP = {
    "EXCELLENT": OverallRating.EXCELLENT,
    "GOOD": OverallRating.GOOD,
    "NEEDS WORK": OverallRating.NEEDS_WORK,
    "POOR": OverallRating.POOR,
}


async def analyze(code: str, language: str) -> ArchitectureReport:
    user_prompt = f"Language: {language}\n\nCode to review:\n```\n{code}\n```"
    try:
        data = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
        suggestions = [ArchitectureSuggestion(**s) for s in data.get("suggestions", [])]
        solid = [SolidPrinciple(**p) for p in data.get("solid_principles", [])]
        rating_str = data.get("rating", "GOOD").upper().strip()
        rating = _RATING_MAP.get(rating_str, OverallRating.GOOD)
        severities = [s.severity for s in suggestions]
        return ArchitectureReport(
            rating=rating,
            solid_principles=solid,
            suggestions=suggestions,
            design_patterns=data.get("design_patterns", []),
            summary=data.get("summary", ""),
            score=score_from_findings(severities),
        )
    except Exception as exc:
        logger.error("Architecture agent failed: %s", exc)
        return ArchitectureReport(
            rating=OverallRating.GOOD,
            suggestions=[],
            solid_principles=[],
            design_patterns=[],
            summary="Architecture analysis could not be completed.",
            score=50.0,
            error=str(exc),
        )
