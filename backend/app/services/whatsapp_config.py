"""Resolve active Meta WhatsApp IDs per deployment environment."""

from __future__ import annotations

from app.config import settings

_LOCAL_DEV_LABELS = frozenset({"development", "dev", "local"})


def _env_labels() -> set[str]:
    return {
        (settings.NEXUS_INSTANCE or "").strip().lower(),
        (settings.ENVIRONMENT or "").strip().lower(),
    }


def is_local_development() -> bool:
    labels = _env_labels() - {""}
    if labels & _LOCAL_DEV_LABELS:
        return True
    return any(label.startswith("dev") and label not in {"devops"} for label in labels)


def resolve_whatsapp_phone_number_id() -> str:
    """Meta phone_number_id used for outbound API calls and inbound filtering."""
    override = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
    if override:
        return override
    if is_local_development():
        return (settings.WHATSAPP_TEST_PHONE_NUMBER_ID or "").strip()
    return (settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID or "").strip()


def resolve_whatsapp_waba_id() -> str:
    """WABA used for messaging and webhook registration in this environment."""
    override = (settings.WHATSAPP_BUSINESS_ACCOUNT_ID or "").strip()
    if override:
        return override
    if is_local_development():
        return (settings.WHATSAPP_TEST_WABA_ID or "").strip()
    return (settings.WHATSAPP_BUSINESS_WABA_ID or "").strip()


def resolve_whatsapp_handoff_waba_id() -> str:
    """Business WABA restored to staging when local development stops."""
    return (
        (settings.WHATSAPP_BUSINESS_WABA_ID or "").strip()
        or (settings.WHATSAPP_BUSINESS_ACCOUNT_ID or "").strip()
    )


def resolve_whatsapp_display_phone() -> str:
    """Human-readable line shown in UI and logs."""
    if is_local_development():
        test_phone = (settings.WHATSAPP_TEST_PHONE_NUMBER or "").strip()
        if test_phone:
            return test_phone
    return (settings.WHATSAPP_BUSINESS_PHONE_NUMBER or "").strip()


def resolve_whatsapp_line_label() -> str:
    return "test" if is_local_development() else "business"
