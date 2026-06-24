from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from app.services.twilio_outbound import get_twilio_client, resolve_whatsapp_addresses

logger = logging.getLogger(__name__)

PickerKind = Literal["date", "time", "consent"]


def _create_content_template(client, friendly_name: str, types_payload: dict) -> str | None:
    """
    Create a Twilio Content template for interactive WhatsApp messages.
    Uses a direct REST call so we send the documented `twilio/list-picker` JSON shape
    regardless of Twilio Python SDK version differences.
    """
    try:
        import httpx

        response = httpx.post(
            "https://content.twilio.com/v1/Content",
            auth=(client.username, client.password),
            json={
                "friendly_name": friendly_name[:200],
                "language": "en",
                "types": types_payload,
            },
            headers={"Accept": "application/json"},
            timeout=30.0,
        )
        if response.status_code >= 400:
            logger.error(
                "Twilio Content API returned status %s: %s",
                response.status_code,
                response.text,
            )
            return None
        content_sid = response.json().get("sid")
        return str(content_sid) if content_sid else None
    except Exception:
        logger.exception("Twilio Content API template creation failed")
        return None


@dataclass
class ListPickerPayload:
    kind: PickerKind
    body: str
    button: str
    items: list[dict[str, str]]


@dataclass
class QuickReplyPayload:
    kind: PickerKind
    body: str
    actions: list[dict[str, str]]


@dataclass
class FlowPayload:
    body: str
    flow_token: str
    flow_id: str
    button: str = "Book consultation"


InteractivePayload = ListPickerPayload | QuickReplyPayload


def _send_content_message(client, formatted_from: str, formatted_to: str, content_sid: str) -> bool:
    try:
        client.messages.create(
            from_=formatted_from,
            to=formatted_to,
            content_sid=content_sid,
        )
        return True
    except Exception:
        logger.exception("Twilio content message send failed for sid=%s", content_sid)
        return False


def dispatch_whatsapp_interactive(to_phone: str, payload: InteractivePayload) -> tuple[bool, str]:
    """
    Send a WhatsApp interactive message (list menu or quick-reply buttons).
    Works inside the 24-hour user-initiated session window.
    Falls back to numbered plain text if the Content API call fails.
    """
    fallback = _build_text_fallback(payload)
    client_bundle = get_twilio_client()
    if not client_bundle:
        return False, fallback

    client, formatted_from = client_bundle
    formatted_to, _ = resolve_whatsapp_addresses(to_phone)
    if not formatted_to:
        return False, fallback

    friendly_name = f"nexus_{payload.kind}_{int(time.time())}"
    types_payload = _build_types_payload(payload)
    if not types_payload:
        return False, fallback

    content_sid = _create_content_template(client, friendly_name, types_payload)
    if not content_sid:
        return False, fallback

    if _send_content_message(client, formatted_from, formatted_to, content_sid):
        return True, payload.body

    return False, fallback


def dispatch_whatsapp_list_picker(to_phone: str, picker: ListPickerPayload) -> tuple[bool, str]:
    return dispatch_whatsapp_interactive(to_phone, picker)


def dispatch_whatsapp_quick_reply(to_phone: str, picker: QuickReplyPayload) -> tuple[bool, str]:
    return dispatch_whatsapp_interactive(to_phone, picker)


def dispatch_whatsapp_flow(to_phone: str, flow: FlowPayload) -> tuple[bool, str]:
    fallback = (
        f"{flow.body}\n\nOpen the booking form using the button above, "
        "or reply *change slot* to reschedule with text options."
    )
    client_bundle = get_twilio_client()
    if not client_bundle:
        return False, fallback

    client, formatted_from = client_bundle
    formatted_to, _ = resolve_whatsapp_addresses(to_phone)
    if not formatted_to:
        return False, fallback

    types_payload = {
        "whatsapp/flows": {
            "body": flow.body[:1024],
            "button_text": flow.button[:20],
            "flow_id": flow.flow_id,
            "flow_token": flow.flow_token[:256],
            "flow_first_page_id": "BOOKING",
            "is_flow_first_page_endpoint": True,
        }
    }
    content_sid = _create_content_template(client, f"nexus_flow_{int(time.time())}", types_payload)
    if not content_sid:
        return False, fallback
    if _send_content_message(client, formatted_from, formatted_to, content_sid):
        return True, flow.body
    return False, fallback


def _build_types_payload(payload: InteractivePayload) -> dict | None:
    if isinstance(payload, ListPickerPayload):
        if not payload.items:
            return None
        return {
            "twilio/list-picker": {
                "body": payload.body[:1024],
                "button": payload.button[:20],
                "items": [
                    {
                        "id": str(item.get("id", index))[:200],
                        "item": str(item.get("item", f"Option {index}"))[:24],
                        "description": str(item.get("description", ""))[:72],
                    }
                    for index, item in enumerate(payload.items[:10], start=1)
                ],
            }
        }

    if isinstance(payload, QuickReplyPayload):
        if not payload.actions:
            return None
        return {
            "twilio/quick-reply": {
                "body": payload.body[:1024],
                "actions": [
                    {
                        "type": "QUICK_REPLY",
                        "title": str(action.get("title", f"Option {index}"))[:20],
                        "id": str(action.get("id", f"option_{index}"))[:200],
                    }
                    for index, action in enumerate(payload.actions[:3], start=1)
                ],
            }
        }

    return None


def _build_text_fallback(payload: InteractivePayload) -> str:
    lines = [payload.body, "Reply with the number of your choice:\n"]

    if isinstance(payload, ListPickerPayload):
        for index, item in enumerate(payload.items, start=1):
            label = item.get("item") or item.get("title") or f"Option {index}"
            lines.append(f"{index}. {label}")
    else:
        for index, action in enumerate(payload.actions, start=1):
            label = action.get("title") or action.get("item") or f"Option {index}"
            lines.append(f"{index}. {label}")

    lines.append("\nExample: reply *1* for the first option.")
    return "\n".join(lines)
