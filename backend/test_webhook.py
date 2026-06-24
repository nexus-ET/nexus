"""
Simulate Meta's GET /api/webhook verification handshake.

Run:
    pytest test_webhook.py -v

Or against a live tunnel/server:
    WEBHOOK_BASE_URL=https://your-tunnel.trycloudflare.com pytest test_webhook.py -v
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers import webhooks

TEST_VERIFY_TOKEN = "test-verify-token-for-meta-handshake"
TEST_CHALLENGE = "test_challenge_123"
WEBHOOK_PATH = "/api/webhook"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "WEBHOOK_VERIFY_TOKEN", TEST_VERIFY_TOKEN)
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", None)

    test_app = FastAPI()
    test_app.include_router(webhooks.router, prefix="/api")
    return TestClient(test_app)


def test_meta_handshake_returns_challenge(client: TestClient) -> None:
    response = client.get(
        WEBHOOK_PATH,
        params={
            "hub.mode": "subscribe",
            "hub.challenge": TEST_CHALLENGE,
            "hub.verify_token": TEST_VERIFY_TOKEN,
        },
    )

    assert response.status_code == 200
    assert response.text == TEST_CHALLENGE


def test_meta_handshake_rejects_wrong_token(client: TestClient) -> None:
    response = client.get(
        WEBHOOK_PATH,
        params={
            "hub.mode": "subscribe",
            "hub.challenge": TEST_CHALLENGE,
            "hub.verify_token": "wrong-token",
        },
    )

    assert response.status_code == 403
    assert response.text == "Forbidden"


def test_meta_handshake_rejects_missing_parameters(client: TestClient) -> None:
    response = client.get(WEBHOOK_PATH, params={"hub.mode": "subscribe"})

    assert response.status_code == 400
    assert "Missing required query parameters" in response.text


def test_meta_handshake_strips_whitespace(client: TestClient) -> None:
    response = client.get(
        WEBHOOK_PATH,
        params={
            "hub.mode": " subscribe ",
            "hub.challenge": f" {TEST_CHALLENGE} ",
            "hub.verify_token": f" {TEST_VERIFY_TOKEN} ",
        },
    )

    assert response.status_code == 200
    assert response.text == TEST_CHALLENGE


@pytest.mark.skipif(
    not os.getenv("WEBHOOK_BASE_URL"),
    reason="Set WEBHOOK_BASE_URL to run live tunnel integration test",
)
def test_meta_handshake_against_live_base_url() -> None:
    base_url = os.environ["WEBHOOK_BASE_URL"].rstrip("/")
    verify_token = (settings.WEBHOOK_VERIFY_TOKEN or "").strip()
    assert verify_token, "WEBHOOK_VERIFY_TOKEN must be set in .env for live test"

    with httpx.Client(base_url=base_url, timeout=30.0) as http:
        ok = http.get(
            WEBHOOK_PATH,
            params={
                "hub.mode": "subscribe",
                "hub.challenge": TEST_CHALLENGE,
                "hub.verify_token": verify_token,
            },
        )
        bad = http.get(
            WEBHOOK_PATH,
            params={
                "hub.mode": "subscribe",
                "hub.challenge": TEST_CHALLENGE,
                "hub.verify_token": "wrong-token",
            },
        )

    assert ok.status_code == 200
    assert ok.text == TEST_CHALLENGE
    assert bad.status_code == 403
