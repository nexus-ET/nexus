from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.whatsapp_config import (
    is_local_development,
    resolve_whatsapp_display_phone,
    resolve_whatsapp_handoff_waba_id,
    resolve_whatsapp_line_label,
    resolve_whatsapp_phone_number_id,
    resolve_whatsapp_waba_id,
)

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@dataclass(frozen=True)
class WhatsAppWebhookStatus:
    nexus_instance: str
    environment: str
    expected_callback_url: str | None
    verify_token_configured: bool
    meta_override_callback_url: str | None
    meta_application_callback_url: str | None
    owned_by_this_environment: bool
    whatsapp_phone_number_id: str | None
    whatsapp_business_account_id: str | None
    whatsapp_display_phone: str | None
    whatsapp_line: str | None


def _normalize_base_url(url: str | None) -> str | None:
    raw = (url or "").strip().rstrip("/")
    return raw or None


def resolve_nexus_instance() -> str:
    return (
        (settings.NEXUS_INSTANCE or "").strip()
        or (settings.ENVIRONMENT or "").strip()
        or "unknown"
    )


def resolve_webhook_base_url() -> str | None:
    return _normalize_base_url(settings.PUBLIC_TUNNEL_BASE or os.getenv("PUBLIC_TUNNEL_BASE"))


def resolve_webhook_callback_url(base_url: str | None = None) -> str | None:
    base = _normalize_base_url(base_url) or resolve_webhook_base_url()
    if not base:
        return None
    return f"{base}/api/webhook"


def resolve_verify_token() -> str:
    for value in (settings.WEBHOOK_VERIFY_TOKEN, settings.WHATSAPP_VERIFY_TOKEN):
        token = (value or "").strip()
        if token:
            return token
    return ""


def _callback_hosts_match(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return False
    expected_host = urlparse(expected).netloc.lower()
    actual_host = urlparse(actual).netloc.lower()
    return bool(expected_host) and expected_host == actual_host


def _graph_headers() -> dict[str, str]:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_meta_webhook_configuration(
    client: httpx.Client | None = None,
) -> tuple[str | None, str | None]:
    """
    Return (waba_override_callback_url, phone_application_callback_url) from Meta.
  """
    waba_id = resolve_whatsapp_waba_id()
    phone_id = resolve_whatsapp_phone_number_id()
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not token or not waba_id:
        return None, None

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=30)

    assert client is not None
    override_url: str | None = None
    application_url: str | None = None

    try:
        apps = client.get(
            f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps",
            headers=_graph_headers(),
        )
        if apps.status_code < 400:
            data = apps.json().get("data") or []
            if data:
                override_url = (
                    (data[0].get("override_callback_uri") or "").strip() or None
                )

        if phone_id:
            phone = client.get(
                f"{GRAPH_API_BASE}/{phone_id}",
                headers=_graph_headers(),
                params={"fields": "webhook_configuration"},
            )
            if phone.status_code < 400:
                config = phone.json().get("webhook_configuration") or {}
                application_url = (config.get("application") or "").strip() or None
                waba_phone_url = (config.get("whatsapp_business_account") or "").strip() or None
                if waba_phone_url and not override_url:
                    override_url = waba_phone_url
    finally:
        if owns_client:
            client.close()

    return override_url, application_url


def get_webhook_status() -> WhatsAppWebhookStatus:
    expected = resolve_webhook_callback_url()
    override_url, application_url = fetch_meta_webhook_configuration()
    effective_meta_url = override_url or application_url
    return WhatsAppWebhookStatus(
        nexus_instance=resolve_nexus_instance(),
        environment=(settings.ENVIRONMENT or "").strip() or "unknown",
        expected_callback_url=expected,
        verify_token_configured=bool(resolve_verify_token()),
        meta_override_callback_url=override_url,
        meta_application_callback_url=application_url,
        owned_by_this_environment=_callback_hosts_match(expected, effective_meta_url),
        whatsapp_phone_number_id=resolve_whatsapp_phone_number_id() or None,
        whatsapp_business_account_id=resolve_whatsapp_waba_id() or None,
        whatsapp_display_phone=resolve_whatsapp_display_phone() or None,
        whatsapp_line=resolve_whatsapp_line_label(),
    )


def register_webhook_callback(
    callback_url: str,
    verify_token: str | None = None,
    *,
    waba_id: str | None = None,
) -> dict[str, Any]:
    """
    Point a WABA inbound webhook at callback_url for this environment.
    """
    resolved_waba = (waba_id or resolve_whatsapp_waba_id()).strip()
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    verify = (verify_token or resolve_verify_token()).strip()
    callback = (callback_url or "").strip().rstrip("/")

    if not resolved_waba:
        raise ValueError("WhatsApp WABA id is not configured.")
    if not token:
        raise ValueError("WHATSAPP_ACCESS_TOKEN is not configured.")
    if not callback:
        raise ValueError("Webhook callback URL is required.")
    if not verify:
        raise ValueError("WEBHOOK_VERIFY_TOKEN is not configured.")

    payload = {"override_callback_uri": callback, "verify_token": verify}
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{GRAPH_API_BASE}/{resolved_waba}/subscribed_apps",
            headers=_graph_headers(),
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Meta webhook registration failed ({response.status_code}): {response.text}"
            )
        return response.json()


def sync_webhook_for_current_environment() -> WhatsAppWebhookStatus:
    callback = resolve_webhook_callback_url()
    if not callback:
        raise ValueError(
            "PUBLIC_TUNNEL_BASE is not set. For local dev, start dev.ps1 with a tunnel. "
            "For nexus-dev, set PUBLIC_TUNNEL_BASE=https://nexus-dev.edutrust.in"
        )

    register_webhook_callback(callback)
    status = get_webhook_status()
    logger.info(
        "WhatsApp webhook registered for %s → %s (owned=%s)",
        status.nexus_instance,
        callback,
        status.owned_by_this_environment,
    )
    return status


def release_webhook_to_handoff_url() -> WhatsAppWebhookStatus | None:
    """
    Return webhook ownership to the configured handoff environment (e.g. nexus-dev).
    Used when local development stops so the shared WABA routes back to the server.
    """
    handoff_base = _normalize_base_url(settings.NEXUS_WHATSAPP_HANDOFF_URL)
    if not handoff_base:
        logger.info("NEXUS_WHATSAPP_HANDOFF_URL not set; leaving Meta webhook unchanged.")
        return None

    callback = f"{handoff_base}/api/webhook"
    handoff_waba = resolve_whatsapp_handoff_waba_id()
    if not handoff_waba:
        raise ValueError("WHATSAPP_BUSINESS_WABA_ID is not configured for webhook handoff.")
    register_webhook_callback(callback, waba_id=handoff_waba)

    if is_local_development():
        test_waba = (settings.WHATSAPP_TEST_WABA_ID or "").strip()
        if test_waba and test_waba != handoff_waba:
            try:
                register_webhook_callback(callback, waba_id=test_waba)
            except Exception:
                logger.warning(
                    "Failed to hand off test WABA %s webhook to %s",
                    test_waba,
                    callback,
                    exc_info=True,
                )
    status = get_webhook_status()
    logger.info(
        "WhatsApp webhook handed off from %s → %s",
        resolve_nexus_instance(),
        callback,
    )
    return status


def should_process_inbound_phone_number_id(phone_number_id: str | None) -> bool:
    """
    Ignore inbound webhooks that belong to a different Meta phone number.
    Prevents cross-environment message bleed when webhook routing is misconfigured.
    """
    expected = resolve_whatsapp_phone_number_id()
    incoming = (phone_number_id or "").strip()
    if not expected or not incoming:
        return True
    if incoming == expected:
        return True

    logger.warning(
        "Ignoring inbound WhatsApp webhook for phone_number_id=%s (this environment expects %s, instance=%s)",
        incoming,
        expected,
        resolve_nexus_instance(),
    )
    return False


def extract_webhook_phone_number_id(payload: dict[str, Any]) -> str | None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = metadata.get("phone_number_id")
            if phone_number_id:
                return str(phone_number_id)
    return None
