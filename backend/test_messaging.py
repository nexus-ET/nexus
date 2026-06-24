"""Tests for Meta webhook payload parsing and messaging provider routing."""

from __future__ import annotations

import pytest

from app.services.messaging import (
    PROVIDER_TWILIO,
    PROVIDER_WHATSAPP,
    get_active_provider,
    parse_whatsapp_payload,
)


def test_parse_whatsapp_payload_extracts_text_message() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "919876543210"}],
                            "messages": [
                                {
                                    "id": "wamid.test",
                                    "from": "919876543210",
                                    "type": "text",
                                    "text": {"body": "Hello Nexus"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    parsed = parse_whatsapp_payload(payload)
    assert parsed is not None
    assert parsed.sender_id == "919876543210"
    assert parsed.message_body == "Hello Nexus"
    assert parsed.message_id == "wamid.test"


def test_parse_whatsapp_payload_ignores_status_updates() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"id": "wamid.test", "status": "delivered"}]
                        }
                    }
                ]
            }
        ]
    }

    assert parse_whatsapp_payload(payload) is None


def test_get_active_provider_defaults_to_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "PROVIDER", "")
    assert get_active_provider() == PROVIDER_TWILIO

    monkeypatch.setattr(settings, "PROVIDER", PROVIDER_WHATSAPP)
    assert get_active_provider() == PROVIDER_WHATSAPP
