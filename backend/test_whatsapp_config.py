"""Tests for environment-specific WhatsApp line resolution."""

from app.services.whatsapp_config import (
    is_local_development,
    resolve_whatsapp_display_phone,
    resolve_whatsapp_handoff_waba_id,
    resolve_whatsapp_phone_number_id,
    resolve_whatsapp_waba_id,
)

TEST_PHONE_ID = "1176133525584040"
TEST_WABA_ID = "1985156525441903"
BUSINESS_PHONE_ID = "1097416893464116"
BUSINESS_WABA_ID = "1312656237246811"


def _patch_dev(monkeypatch):
    monkeypatch.setattr("app.services.whatsapp_config.settings.NEXUS_INSTANCE", "development")
    monkeypatch.setattr("app.services.whatsapp_config.settings.ENVIRONMENT", "development")
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_PHONE_NUMBER_ID", None)
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_ACCOUNT_ID", None)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_TEST_PHONE_NUMBER_ID",
        TEST_PHONE_ID,
    )
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_TEST_WABA_ID", TEST_WABA_ID)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_TEST_PHONE_NUMBER",
        "+15556656397",
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID",
        BUSINESS_PHONE_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_WABA_ID",
        BUSINESS_WABA_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER",
        "+917411952525",
    )


def _patch_staging(monkeypatch):
    monkeypatch.setattr("app.services.whatsapp_config.settings.NEXUS_INSTANCE", "nexus-dev")
    monkeypatch.setattr("app.services.whatsapp_config.settings.ENVIRONMENT", "staging")
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_PHONE_NUMBER_ID", None)
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_ACCOUNT_ID", None)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_TEST_PHONE_NUMBER_ID",
        TEST_PHONE_ID,
    )
    monkeypatch.setattr("app.services.whatsapp_config.settings.WHATSAPP_TEST_WABA_ID", TEST_WABA_ID)
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID",
        BUSINESS_PHONE_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_WABA_ID",
        BUSINESS_WABA_ID,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_config.settings.WHATSAPP_BUSINESS_PHONE_NUMBER",
        "+917411952525",
    )


def test_dev_uses_test_line(monkeypatch):
    _patch_dev(monkeypatch)
    assert is_local_development() is True
    assert resolve_whatsapp_phone_number_id() == TEST_PHONE_ID
    assert resolve_whatsapp_waba_id() == TEST_WABA_ID
    assert resolve_whatsapp_display_phone() == "+15556656397"
    assert resolve_whatsapp_handoff_waba_id() == BUSINESS_WABA_ID


def test_staging_uses_business_line(monkeypatch):
    _patch_staging(monkeypatch)
    assert is_local_development() is False
    assert resolve_whatsapp_phone_number_id() == BUSINESS_PHONE_ID
    assert resolve_whatsapp_waba_id() == BUSINESS_WABA_ID
    assert resolve_whatsapp_display_phone() == "+917411952525"
    assert resolve_whatsapp_handoff_waba_id() == BUSINESS_WABA_ID
