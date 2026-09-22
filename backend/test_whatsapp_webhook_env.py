"""Tests for per-environment WhatsApp webhook routing helpers."""

from app.services.whatsapp_webhook_env import (
    explain_meta_registration_failure,
    extract_webhook_phone_number_id,
    probe_webhook_challenge,
    resolve_webhook_callback_url,
    should_process_inbound_phone_number_id,
)

TEST_PHONE_ID = "1176133525584040"
BUSINESS_PHONE_ID = "1097416893464116"


def test_resolve_webhook_callback_url():
    assert (
        resolve_webhook_callback_url("https://example.test")
        == "https://example.test/api/webhook"
    )


def test_extract_webhook_phone_number_id():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": BUSINESS_PHONE_ID},
                            "messages": [{"from": "918754545407", "type": "text"}],
                        }
                    }
                ]
            }
        ]
    }
    assert extract_webhook_phone_number_id(payload) == BUSINESS_PHONE_ID


def test_should_process_inbound_phone_number_id_dev(monkeypatch):
    monkeypatch.setattr("app.services.whatsapp_config.settings.NEXUS_INSTANCE", "development")
    monkeypatch.setattr("app.services.whatsapp_config.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_PHONE_NUMBER_ID", None)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_TEST_PHONE_NUMBER_ID",
        TEST_PHONE_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID",
        BUSINESS_PHONE_ID,
    )

    assert should_process_inbound_phone_number_id(TEST_PHONE_ID) is True
    assert should_process_inbound_phone_number_id(BUSINESS_PHONE_ID) is False
    assert should_process_inbound_phone_number_id(None) is True


def test_should_process_inbound_phone_number_id_staging(monkeypatch):
    monkeypatch.setattr("app.services.whatsapp_config.settings.NEXUS_INSTANCE", "nexus-dev")
    monkeypatch.setattr("app.services.whatsapp_config.settings.ENVIRONMENT", "staging")
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_PHONE_NUMBER_ID", None)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_TEST_PHONE_NUMBER_ID",
        TEST_PHONE_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID",
        BUSINESS_PHONE_ID,
    )

    assert should_process_inbound_phone_number_id(BUSINESS_PHONE_ID) is True
    assert should_process_inbound_phone_number_id(TEST_PHONE_ID) is False
    assert should_process_inbound_phone_number_id(None) is True


def test_explain_meta_registration_failure_mentions_verify_token():
    message = explain_meta_registration_failure(
        400,
        '{"error":{"message":"(#2200) Callback verification failed ... HTTP Status Code = 403"}}',
    )
    assert "WEBHOOK_VERIFY_TOKEN" in message
    assert "NEXUS_WHATSAPP_AUTO_SYNC" in message


def test_probe_webhook_challenge_ok(monkeypatch):
    class _Resp:
        status_code = 200
        text = "nexus-webhook-challenge-probe"

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            assert "hub.verify_token" in params
            return _Resp()

    monkeypatch.setattr(
        "app.services.whatsapp_webhook_env.httpx.Client",
        _Client,
    )
    ok, detail = probe_webhook_challenge(
        "https://example.test/api/webhook",
        verify_token="shared-token",
    )
    assert ok is True
    assert detail == "ok"


def test_probe_webhook_challenge_forbidden(monkeypatch):
    class _Resp:
        status_code = 403
        text = "Forbidden"

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            return _Resp()

    monkeypatch.setattr(
        "app.services.whatsapp_webhook_env.httpx.Client",
        _Client,
    )
    ok, detail = probe_webhook_challenge(
        "https://nexus-dev.edutrust.in/api/webhook",
        verify_token="wrong-token",
    )
    assert ok is False
    assert "403" in detail
    assert "verify token" in detail.lower()
