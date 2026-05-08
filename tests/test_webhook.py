"""Tests for the GitHub webhook endpoint."""
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings


def _make_signature(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def webhook_client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    get_settings.cache_clear()
    from backend.main import app
    yield TestClient(app)
    get_settings.cache_clear()


def _pr_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": 42,
            "title": "Add new feature",
            "url": "https://api.github.com/repos/test/repo/pulls/42",
            "comments_url": "https://api.github.com/repos/test/repo/issues/42/comments",
        },
        "repository": {"full_name": "test/repo"},
    }


class TestWebhookSignatureVerification:
    def test_missing_signature_returns_401(self, webhook_client):
        payload = json.dumps(_pr_payload()).encode()
        resp = webhook_client.post(
            "/webhook/github",
            content=payload,
            headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 401

    def test_wrong_signature_returns_401(self, webhook_client):
        payload = json.dumps(_pr_payload()).encode()
        resp = webhook_client.post(
            "/webhook/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=wrongsignature",
            },
        )
        assert resp.status_code == 401

    def test_valid_signature_passes(self, webhook_client):
        payload = json.dumps(_pr_payload()).encode()
        sig = _make_signature(payload, "test-secret")
        with patch("backend.api.github_webhook._run_pr_review", new_callable=AsyncMock):
            resp = webhook_client.post(
                "/webhook/github",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                },
            )
        assert resp.status_code == 200


class TestWebhookEventFiltering:
    def _post(self, client, payload: dict, event: str = "pull_request"):
        raw = json.dumps(payload).encode()
        sig = _make_signature(raw, "test-secret")
        return client.post(
            "/webhook/github",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": event,
                "X-Hub-Signature-256": sig,
            },
        )

    def test_non_pr_event_is_ignored(self, webhook_client):
        resp = self._post(webhook_client, {"action": "created"}, event="push")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_closed_action_is_ignored(self, webhook_client):
        resp = self._post(webhook_client, _pr_payload(action="closed"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_opened_action_queues_review(self, webhook_client):
        with patch("backend.api.github_webhook._run_pr_review", new_callable=AsyncMock):
            resp = self._post(webhook_client, _pr_payload(action="opened"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "review_queued"
        assert data["pr"] == 42

    def test_synchronize_action_queues_review(self, webhook_client):
        with patch("backend.api.github_webhook._run_pr_review", new_callable=AsyncMock):
            resp = self._post(webhook_client, _pr_payload(action="synchronize"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "review_queued"
