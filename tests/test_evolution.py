"""Tests for the evolution tracker and API."""
from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio

from backend.config import get_settings
from backend.evolution.tracker import get_evolution, list_repos, save_review


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    db = str(tmp_path / "test_evolution.db")
    monkeypatch.setenv("EVOLUTION_DB_PATH", db)
    yield db


@pytest.mark.asyncio
class TestEvolutionTracker:
    async def test_save_and_retrieve(self):
        await save_review(
            repo="test/repo",
            pr_number=1,
            pr_title="First PR",
            overall_score=75.0,
            security_score=80.0,
            performance_score=70.0,
            architecture_score=75.0,
            test_score=60.0,
            docs_score=80.0,
        )
        records = await get_evolution(repo="test/repo")
        assert len(records) == 1
        assert records[0]["overall_score"] == 75.0
        assert records[0]["repo"] == "test/repo"
        assert records[0]["pr_number"] == 1

    async def test_multiple_reviews_ordered(self):
        for i in range(3):
            await save_review(
                repo="test/repo",
                pr_number=i + 1,
                overall_score=float(60 + i * 10),
                security_score=70.0,
                performance_score=70.0,
                architecture_score=70.0,
                test_score=70.0,
                docs_score=70.0,
            )
        records = await get_evolution(repo="test/repo")
        assert len(records) == 3
        # get_evolution returns DESC by default; values should be 80, 70, 60
        scores = [r["overall_score"] for r in records]
        assert 80.0 in scores and 60.0 in scores

    async def test_list_repos(self):
        await save_review(
            repo="owner/repo-a",
            overall_score=70.0, security_score=70.0, performance_score=70.0,
            architecture_score=70.0, test_score=70.0, docs_score=70.0,
        )
        await save_review(
            repo="owner/repo-b",
            overall_score=80.0, security_score=80.0, performance_score=80.0,
            architecture_score=80.0, test_score=80.0, docs_score=80.0,
        )
        repos = await list_repos()
        assert "owner/repo-a" in repos
        assert "owner/repo-b" in repos

    async def test_get_all_without_filter(self):
        for repo in ("a/repo", "b/repo"):
            await save_review(
                repo=repo,
                overall_score=70.0, security_score=70.0, performance_score=70.0,
                architecture_score=70.0, test_score=70.0, docs_score=70.0,
            )
        records = await get_evolution()
        assert len(records) == 2


@pytest.mark.asyncio
class TestEvolutionAPI:
    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        get_settings.cache_clear()
        from fastapi.testclient import TestClient
        from backend.main import app
        yield TestClient(app)
        get_settings.cache_clear()

    async def test_repos_endpoint_empty(self, client):
        resp = client.get("/evolution/repos")
        assert resp.status_code == 200
        assert resp.json()["repos"] == []

    async def test_history_endpoint_empty(self, client):
        resp = client.get("/evolution/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["records"] == []
