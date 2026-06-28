"""Tests for per-environment WhatsApp webhook routing helpers."""

from app.services.whatsapp_webhook_env import (
    extract_webhook_phone_number_id,
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
