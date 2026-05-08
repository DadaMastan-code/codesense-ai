from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class OverallRating(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    NEEDS_WORK = "NEEDS WORK"
    POOR = "POOR"
    CRITICAL = "CRITICAL"


class TestFramework(str, Enum):
    PYTEST = "pytest"
    JEST = "jest"
    MOCHA = "mocha"
    JUNIT = "junit"


# ── Request models ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    language: str | None = Field(None, description="Auto-detected if omitted")
    context: str | None = Field(None, max_length=1_000)


class FixRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    issues: list[str] = Field(default_factory=list)


class GenerateTestsRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50_000)
    framework: TestFramework = TestFramework.PYTEST


# ── Security agent ────────────────────────────────────────────────────────────

class SecurityFinding(BaseModel):
    line_number: int | None = None
    severity: Severity
    title: str
    description: str
    fix_recommendation: str
    owasp_category: str
    owasp_reference: str


class SecurityReport(BaseModel):
    findings: list[SecurityFinding] = Field(default_factory=list)
    summary: str = ""
    score: float = Field(100.0, ge=0, le=100)
    error: str | None = None


# ── Performance agent ─────────────────────────────────────────────────────────

class ComplexityInfo(BaseModel):
    function_name: str
    time_complexity: str
    space_complexity: str
    explanation: str


class PerformanceIssue(BaseModel):
    line_number: int | None = None
    severity: Severity
    title: str
    description: str
    before_code: str = ""
    after_code: str = ""
    expected_improvement: str = ""


class PerformanceReport(BaseModel):
    issues: list[PerformanceIssue] = Field(default_factory=list)
    complexity_analysis: list[ComplexityInfo] = Field(default_factory=list)
    summary: str = ""
    score: float = Field(100.0, ge=0, le=100)
    error: str | None = None


# ── Architecture agent ────────────────────────────────────────────────────────

class SolidPrinciple(BaseModel):
    principle: str
    passed: bool
    explanation: str


class ArchitectureSuggestion(BaseModel):
    severity: Severity
    title: str
    description: str
    pattern_suggestion: str = ""


class ArchitectureReport(BaseModel):
    rating: OverallRating = OverallRating.GOOD
    solid_principles: list[SolidPrinciple] = Field(default_factory=list)
    suggestions: list[ArchitectureSuggestion] = Field(default_factory=list)
    design_patterns: list[str] = Field(default_factory=list)
    summary: str = ""
    score: float = Field(100.0, ge=0, le=100)
    error: str | None = None


# ── Test agent ────────────────────────────────────────────────────────────────

class TestCase(BaseModel):
    name: str
    category: str  # happy_path | edge_case | error_case | boundary
    description: str


class TestReport(BaseModel):
    test_cases: list[TestCase] = Field(default_factory=list)
    generated_code: str = ""
    untested_branches: list[str] = Field(default_factory=list)
    framework: str = "pytest"
    error: str | None = None


# ── Doc agent ─────────────────────────────────────────────────────────────────

class DocIssue(BaseModel):
    element: str  # function / class / variable name
    issue_type: str  # missing_docstring | confusing_name | needs_comment
    suggestion: str


class DocReport(BaseModel):
    documented_code: str = ""
    issues: list[DocIssue] = Field(default_factory=list)
    plain_english_summary: str = ""
    score: float = Field(100.0, ge=0, le=100)
    error: str | None = None


# ── Fix agent ─────────────────────────────────────────────────────────────────

class FixReport(BaseModel):
    fixed_code: str = ""
    diff: str = ""
    explanation: str = ""
    changes: list[str] = Field(default_factory=list)
    error: str | None = None


# ── Composite output ──────────────────────────────────────────────────────────

class CodeSenseScore(BaseModel):
    total: float = Field(..., ge=0, le=100)
    security: float = Field(..., ge=0, le=100)
    performance: float = Field(..., ge=0, le=100)
    architecture: float = Field(..., ge=0, le=100)
    documentation: float = Field(..., ge=0, le=100)
    rating: OverallRating

    @classmethod
    def compute(
        cls,
        security: float,
        performance: float,
        architecture: float,
        documentation: float,
    ) -> CodeSenseScore:
        total = (
            security * 0.40
            + performance * 0.30
            + architecture * 0.20
            + documentation * 0.10
        )
        if total >= 90:
            rating = OverallRating.EXCELLENT
        elif total >= 70:
            rating = OverallRating.GOOD
        elif total >= 40:
            rating = OverallRating.NEEDS_WORK
        else:
            rating = OverallRating.CRITICAL
        return cls(
            total=round(total, 1),
            security=round(security, 1),
            performance=round(performance, 1),
            architecture=round(architecture, 1),
            documentation=round(documentation, 1),
            rating=rating,
        )


class FullAnalysisResponse(BaseModel):
    language: str
    score: CodeSenseScore
    security: SecurityReport
    performance: PerformanceReport
    architecture: ArchitectureReport
    tests: TestReport
    documentation: DocReport
    fix: FixReport
    analysis_time_seconds: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "ok"
    provider: str
    model: str
    version: str = "1.0.0"


class SupportedLanguagesResponse(BaseModel):
    languages: list[str]
