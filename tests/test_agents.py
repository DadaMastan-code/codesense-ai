"""Unit tests for all CodeSense AI agents."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.schemas import (
    ArchitectureReport,
    DocReport,
    FixReport,
    OverallRating,
    PerformanceReport,
    SecurityReport,
    Severity,
    TestReport,
)
from backend.utils.diff_generator import generate_diff, generate_html_diff
from backend.utils.language_detector import detect_language
from backend.utils.severity_scorer import score_from_findings, severity_label


# ── Language detector ─────────────────────────────────────────────────────────

class TestLanguageDetector:
    def test_detects_python(self):
        code = "def hello():\n    print('world')\n"
        assert detect_language(code) == "python"

    def test_detects_javascript(self):
        code = "const x = () => { console.log('hi'); };"
        assert detect_language(code) == "javascript"

    def test_detects_typescript(self):
        code = "const x: string = 'hello'; interface Foo { bar: number; }"
        assert detect_language(code) == "typescript"

    def test_detects_java(self):
        code = "public class Main { public static void main(String[] args) {} }"
        assert detect_language(code) == "java"

    def test_detects_go(self):
        code = "package main\nimport \"fmt\"\nfunc main() { fmt.Println(\"hi\") }"
        assert detect_language(code) == "go"

    def test_detects_rust(self):
        code = "fn main() { let mut x = 5; println!(\"{}\", x); }"
        assert detect_language(code) == "rust"

    def test_returns_unknown_for_empty(self):
        # No recognisable patterns
        result = detect_language("hello world 123")
        assert isinstance(result, str)

    def test_detects_cpp(self):
        code = "#include <iostream>\nint main() { std::cout << 'hi'; return 0; }"
        assert detect_language(code) == "cpp"


# ── Severity scorer ───────────────────────────────────────────────────────────

class TestSeverityScorer:
    def test_no_findings_gives_100(self):
        assert score_from_findings([]) == 100.0

    def test_critical_deducts_40(self):
        assert score_from_findings([Severity.CRITICAL]) == 60.0

    def test_high_deducts_20(self):
        assert score_from_findings([Severity.HIGH]) == 80.0

    def test_medium_deducts_10(self):
        assert score_from_findings([Severity.MEDIUM]) == 90.0

    def test_low_deducts_4(self):
        assert score_from_findings([Severity.LOW]) == 96.0

    def test_floor_at_zero(self):
        sevs = [Severity.CRITICAL] * 10
        assert score_from_findings(sevs) == 0.0

    def test_mixed_findings(self):
        sevs = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM]
        # 100 - 40 - 20 - 10 = 30
        assert score_from_findings(sevs) == 30.0

    def test_severity_label_critical(self):
        assert severity_label(30) == "CRITICAL"

    def test_severity_label_needs_work(self):
        assert severity_label(55) == "NEEDS WORK"

    def test_severity_label_good(self):
        assert severity_label(75) == "GOOD"

    def test_severity_label_excellent(self):
        assert severity_label(95) == "EXCELLENT"


# ── Diff generator ────────────────────────────────────────────────────────────

class TestDiffGenerator:
    def test_identical_code_produces_empty_diff(self):
        code = "x = 1\ny = 2\n"
        diff = generate_diff(code, code)
        assert diff == ""

    def test_diff_shows_removed_line(self):
        original = "x = 1\ny = 2\n"
        fixed = "x = 1\n"
        diff = generate_diff(original, fixed)
        assert "-y = 2" in diff

    def test_diff_shows_added_line(self):
        original = "x = 1\n"
        fixed = "x = 1\ny = 2\n"
        diff = generate_diff(original, fixed)
        assert "+y = 2" in diff

    def test_diff_has_correct_file_headers(self):
        diff = generate_diff("a\n", "b\n", filename="test.py")
        assert "a/test.py" in diff
        assert "b/test.py" in diff

    def test_html_diff_returns_string(self):
        html = generate_html_diff("x = 1\n", "x = 2\n")
        assert isinstance(html, str)
        assert "<table" in html.lower()


# ── CodeSenseScore ────────────────────────────────────────────────────────────

class TestCodeSenseScore:
    def test_excellent_rating(self):
        from backend.models.schemas import CodeSenseScore
        score = CodeSenseScore.compute(95, 95, 95, 95)
        assert score.rating == OverallRating.EXCELLENT
        assert score.total >= 90

    def test_good_rating(self):
        from backend.models.schemas import CodeSenseScore
        score = CodeSenseScore.compute(80, 75, 70, 80)
        assert score.rating == OverallRating.GOOD

    def test_needs_work_rating(self):
        from backend.models.schemas import CodeSenseScore
        score = CodeSenseScore.compute(50, 50, 50, 50)
        assert score.rating == OverallRating.NEEDS_WORK

    def test_critical_rating(self):
        from backend.models.schemas import CodeSenseScore
        score = CodeSenseScore.compute(10, 10, 10, 10)
        assert score.rating == OverallRating.CRITICAL

    def test_weighted_calculation(self):
        from backend.models.schemas import CodeSenseScore
        # sec=100, perf=0, arch=0, doc=0 → total = 100*0.4 = 40
        score = CodeSenseScore.compute(100, 0, 0, 0)
        assert score.total == 40.0

    def test_score_clamped_to_range(self):
        from backend.models.schemas import CodeSenseScore
        score = CodeSenseScore.compute(100, 100, 100, 100)
        assert 0 <= score.total <= 100


# ── Security agent ────────────────────────────────────────────────────────────

class TestSecurityAgent:
    @pytest.mark.asyncio
    async def test_returns_security_report_on_success(self):
        mock_response = {
            "findings": [
                {
                    "line_number": 5,
                    "severity": "CRITICAL",
                    "title": "SQL Injection",
                    "description": "Unsanitised user input in query",
                    "fix_recommendation": "Use parameterised queries",
                    "owasp_category": "A03:2021 - Injection",
                    "owasp_reference": "https://owasp.org/Top10/A03_2021-Injection/",
                }
            ],
            "summary": "Critical SQL injection found.",
        }
        with patch("backend.agents.security_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            from backend.agents.security_agent import analyze
            report = await analyze("SELECT * FROM users WHERE id = " + "'" + "1'", "python")
        assert isinstance(report, SecurityReport)
        assert len(report.findings) == 1
        assert report.findings[0].severity == Severity.CRITICAL
        assert report.score < 100

    @pytest.mark.asyncio
    async def test_returns_error_report_on_llm_failure(self):
        with patch("backend.agents.security_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM timeout")
            from backend.agents.security_agent import analyze
            report = await analyze("x = 1", "python")
        assert report.error is not None
        assert report.score == 50.0


# ── Performance agent ─────────────────────────────────────────────────────────

class TestPerformanceAgent:
    @pytest.mark.asyncio
    async def test_returns_performance_report(self):
        mock_response = {
            "complexity_analysis": [
                {"function_name": "find_dups", "time_complexity": "O(n²)", "space_complexity": "O(n)", "explanation": "Nested loops"}
            ],
            "issues": [],
            "summary": "One quadratic function found.",
        }
        with patch("backend.agents.performance_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            from backend.agents.performance_agent import analyze
            report = await analyze("for i in items:\n  for j in items:\n    pass", "python")
        assert isinstance(report, PerformanceReport)
        assert len(report.complexity_analysis) == 1
        assert report.complexity_analysis[0].time_complexity == "O(n²)"

    @pytest.mark.asyncio
    async def test_graceful_failure(self):
        with patch("backend.agents.performance_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("timeout")
            from backend.agents.performance_agent import analyze
            report = await analyze("x=1", "python")
        assert report.error is not None


# ── Architecture agent ────────────────────────────────────────────────────────

class TestArchitectureAgent:
    @pytest.mark.asyncio
    async def test_returns_architecture_report(self):
        mock_response = {
            "rating": "GOOD",
            "solid_principles": [
                {"principle": "Single Responsibility", "passed": True, "explanation": "Each class has one job"}
            ],
            "suggestions": [],
            "design_patterns": ["Factory"],
            "summary": "Well structured code.",
        }
        with patch("backend.agents.architecture_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            from backend.agents.architecture_agent import analyze
            report = await analyze("class Foo:\n  pass", "python")
        assert isinstance(report, ArchitectureReport)
        assert report.rating == OverallRating.GOOD
        assert "Factory" in report.design_patterns

    @pytest.mark.asyncio
    async def test_graceful_failure(self):
        with patch("backend.agents.architecture_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("timeout")
            from backend.agents.architecture_agent import analyze
            report = await analyze("x=1", "python")
        assert report.error is not None


# ── Doc agent ─────────────────────────────────────────────────────────────────

class TestDocAgent:
    @pytest.mark.asyncio
    async def test_returns_doc_report(self):
        mock_response = {
            "documented_code": "def foo():\n    \"\"\"Does foo.\"\"\"\n    pass",
            "issues": [{"element": "foo", "issue_type": "missing_docstring", "suggestion": "Add a docstring"}],
            "plain_english_summary": "This code defines a function foo.",
        }
        with patch("backend.agents.doc_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            from backend.agents.doc_agent import analyze
            report = await analyze("def foo():\n    pass", "python")
        assert isinstance(report, DocReport)
        assert "foo" in report.documented_code
        assert len(report.issues) == 1

    @pytest.mark.asyncio
    async def test_graceful_failure(self):
        with patch("backend.agents.doc_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("timeout")
            from backend.agents.doc_agent import analyze
            report = await analyze("x=1", "python")
        assert report.error is not None


# ── Fix agent ─────────────────────────────────────────────────────────────────

class TestFixAgent:
    @pytest.mark.asyncio
    async def test_returns_fix_report_with_diff(self):
        original = "x = 1\n"
        fixed = "x = 2\n"
        mock_response = {
            "fixed_code": fixed,
            "explanation": "Changed x to 2.",
            "changes": ["Updated x value from 1 to 2"],
        }
        with patch("backend.agents.fix_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            from backend.agents.fix_agent import apply_fixes
            report = await apply_fixes(original, "python", ["x should be 2"])
        assert isinstance(report, FixReport)
        assert report.fixed_code == fixed
        assert "-x = 1" in report.diff
        assert "+x = 2" in report.diff

    @pytest.mark.asyncio
    async def test_graceful_failure(self):
        with patch("backend.agents.fix_agent.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("timeout")
            from backend.agents.fix_agent import apply_fixes
            report = await apply_fixes("x=1", "python", [])
        assert report.error is not None
        assert report.fixed_code == "x=1"  # returns original on failure
