from __future__ import annotations

from backend.models.schemas import Severity

_SEVERITY_PENALTIES: dict[Severity, float] = {
    Severity.CRITICAL: 40.0,
    Severity.HIGH: 20.0,
    Severity.MEDIUM: 10.0,
    Severity.LOW: 4.0,
    Severity.INFO: 1.0,
}


def score_from_findings(severities: list[Severity], base: float = 100.0) -> float:
    """Deduct points for each finding; floor at 0."""
    total_penalty = sum(_SEVERITY_PENALTIES.get(s, 0) for s in severities)
    return max(0.0, base - total_penalty)


def severity_label(score: float) -> str:
    if score < 40:
        return "CRITICAL"
    if score < 70:
        return "NEEDS WORK"
    if score < 90:
        return "GOOD"
    return "EXCELLENT"
