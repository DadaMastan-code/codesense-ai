"""Integration tests for the FastAPI endpoints."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.models.schemas import (
    ArchitectureReport,
    CodeSenseScore,
    DocReport,
    FixReport,
    FullAnalysisResponse,
    OverallRating,
    PerformanceReport,
    SecurityReport,
    TestReport,
)


def _make_full_response() -> FullAnalysisResponse:
    score = CodeSenseScore.compute(80, 80, 80, 80)
    return FullAnalysisResponse(
        language="python",
        score=score,
        security=SecurityReport(findings=[], summary="All clear.", score=80),
        performance=PerformanceReport(issues=[], complexity_analysis=[], summary="OK", score=80),
        architecture=ArchitectureReport(
            rating=OverallRating.GOOD, suggestions=[], solid_principles=[],
            design_patterns=[], summary="Good", score=80,
        ),
        tests=TestReport(test_cases=[], generated_code="# test", untested_branches=[], framework="pytest"),
        documentation=DocReport(
            documented_code="x = 1", issues=[],
            plain_english_summary="Simple code.", score=80,
        ),
        fix=FixReport(fixed_code="x = 1", diff="", explanation="No changes.", changes=[]),
        analysis_time_seconds=1.5,
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient with a fake API key so has_any_llm_key is True."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    from backend.main import app
    yield TestClient(app)
    get_settings.cache_clear()


@pytest.fixture
def client_no_key(monkeypatch):
    """TestClient with NO API keys configured."""
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    from backend.main import app
    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_shape(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "provider" in data
        assert "model" in data


class TestSupportedLanguages:
    def test_returns_list(self, client):
        resp = client.get("/supported-languages")
        assert resp.status_code == 200
        data = resp.json()
        assert "languages" in data
        assert isinstance(data["languages"], list)
        assert "python" in data["languages"]

    def test_includes_common_languages(self, client):
        resp = client.get("/supported-languages")
        data = resp.json()
        langs = data["languages"]
        for lang in ["python", "javascript", "java", "go", "rust"]:
            assert lang in langs


class TestAnalyzeEndpoint:
    def test_analyze_requires_code(self, client):
        resp = client.post("/analyze", json={})
        assert resp.status_code == 422

    def test_analyze_empty_code_rejected(self, client):
        resp = client.post("/analyze", json={"code": ""})
        assert resp.status_code == 422

    def test_analyze_returns_full_response(self, client):
        full = _make_full_response()
        with patch("backend.main.run_full_analysis", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = full
            resp = client.post("/analyze", json={"code": "x = 1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "security" in data
        assert "performance" in data
        assert "architecture" in data
        assert "tests" in data
        assert "documentation" in data
        assert "fix" in data

    def test_analyze_with_language_hint(self, client):
        full = _make_full_response()
        with patch("backend.main.run_full_analysis", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = full
            resp = client.post("/analyze", json={"code": "x = 1", "language": "python"})
        assert resp.status_code == 200
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[1] == "python"

    def test_analyze_with_context(self, client):
        full = _make_full_response()
        with patch("backend.main.run_full_analysis", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = full
            resp = client.post("/analyze", json={"code": "x = 1", "context": "auth handler"})
        assert resp.status_code == 200
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[2] == "auth handler"

    def test_analyze_503_when_no_key(self, client_no_key):
        resp = client_no_key.post("/analyze", json={"code": "x = 1"})
        assert resp.status_code == 503

    def test_analyze_response_has_language(self, client):
        full = _make_full_response()
        with patch("backend.main.run_full_analysis", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = full
            resp = client.post("/analyze", json={"code": "def foo(): pass"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "python"

    def test_analyze_score_structure(self, client):
        full = _make_full_response()
        with patch("backend.main.run_full_analysis", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = full
            resp = client.post("/analyze", json={"code": "x = 1"})
        data = resp.json()
        score = data["score"]
        assert "total" in score
        assert "rating" in score
        assert "security" in score
        assert "performance" in score


class TestFixEndpoint:
    def test_fix_requires_code(self, client):
        resp = client.post("/fix", json={})
        assert resp.status_code == 422

    def test_fix_returns_fix_report(self, client):
        fix = FixReport(
            fixed_code="x = 2",
            diff="-x=1\n+x=2",
            explanation="Fixed",
            changes=["changed x"],
        )
        with patch("backend.main.fix_agent.apply_fixes", new_callable=AsyncMock) as mock_fix:
            mock_fix.return_value = fix
            resp = client.post("/fix", json={"code": "x = 1", "issues": ["x should be 2"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["fixed_code"] == "x = 2"
        assert data["diff"] == "-x=1\n+x=2"

    def test_fix_with_empty_issues_list(self, client):
        fix = FixReport(fixed_code="x = 1", diff="", explanation="No changes.", changes=[])
        with patch("backend.main.fix_agent.apply_fixes", new_callable=AsyncMock) as mock_fix:
            mock_fix.return_value = fix
            resp = client.post("/fix", json={"code": "x = 1", "issues": []})
        assert resp.status_code == 200

    def test_fix_503_when_no_key(self, client_no_key):
        resp = client_no_key.post("/fix", json={"code": "x = 1", "issues": []})
        assert resp.status_code == 503


class TestGenerateTestsEndpoint:
    def test_generate_tests_requires_code(self, client):
        resp = client.post("/generate-tests", json={})
        assert resp.status_code == 422

    def test_generate_tests_returns_test_report(self, client):
        report = TestReport(
            test_cases=[],
            generated_code="def test_foo(): assert True",
            untested_branches=[],
            framework="pytest",
        )
        with patch("backend.main.test_agent.suggest", new_callable=AsyncMock) as mock_tests:
            mock_tests.return_value = report
            resp = client.post("/generate-tests", json={"code": "def foo(): return 1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_code" in data
        assert "test_cases" in data

    def test_generate_tests_default_framework_is_pytest(self, client):
        report = TestReport(test_cases=[], generated_code="", untested_branches=[], framework="pytest")
        with patch("backend.main.test_agent.suggest", new_callable=AsyncMock) as mock_tests:
            mock_tests.return_value = report
            resp = client.post("/generate-tests", json={"code": "def foo(): pass"})
        assert resp.status_code == 200
        mock_tests.assert_called_once()
        assert mock_tests.call_args[0][2] == "pytest"

    def test_generate_tests_jest_framework(self, client):
        report = TestReport(test_cases=[], generated_code="", untested_branches=[], framework="jest")
        with patch("backend.main.test_agent.suggest", new_callable=AsyncMock) as mock_tests:
            mock_tests.return_value = report
            resp = client.post("/generate-tests", json={"code": "function foo() {}", "framework": "jest"})
        assert resp.status_code == 200

    def test_generate_tests_503_when_no_key(self, client_no_key):
        resp = client_no_key.post("/generate-tests", json={"code": "def foo(): pass"})
        assert resp.status_code == 503
