"""Send WhatsApp interactive messages via Meta Cloud API (Graph)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.services.admissions_intake_flow import IntakeReply
from app.services.messaging import (
    WHATSAPP_GRAPH_API_BASE,
    WhatsAppDeliveryError,
    extract_meta_message_id,
    format_meta_graph_error,
)
from app.services.phone_utils import clean_phone_number
from app.services.twilio_whatsapp_interactive import (
    InteractivePayload,
    ListPickerPayload,
    QuickReplyPayload,
    build_text_fallback,
)
from app.services.whatsapp_config import resolve_whatsapp_phone_number_id

logger = logging.getLogger(__name__)


def _graph_headers() -> dict[str, str]:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _messages_url() -> str:
    phone_number_id = resolve_whatsapp_phone_number_id()
    if not phone_number_id:
        raise WhatsAppDeliveryError("WHATSAPP_PHONE_NUMBER_ID is not configured.")
    return f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"


def compose_intake_message_text(reply: IntakeReply) -> str:
    """Plain-text body with numbered options when a picker is attached."""
    interactive: InteractivePayload | None = reply.quick_reply or reply.list_picker
    if not interactive:
        return (reply.text or "Please reply to continue.").strip()

    fallback = build_text_fallback(interactive)
    intro = (reply.text or "").strip()
    if intro and intro not in fallback:
        lines = fallback.split("\n")
        option_lines = lines[1:] if len(lines) > 1 else lines
        return f"{intro}\n\n" + "\n".join(option_lines).strip()
    return fallback


def _build_list_payload(to_number: str, picker: ListPickerPayload) -> dict[str, Any]:
    rows = [
        {
            "id": str(item.get("id", index))[:200],
            "title": str(item.get("item", f"Option {index}"))[:24],
            "description": str(item.get("description", ""))[:72],
        }
        for index, item in enumerate(picker.items[:10], start=1)
    ]
    return {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": (picker.body or "Choose an option")[:1024]},
            "action": {
                "button": (picker.button or "Choose")[:20],
                "sections": [{"title": "Options", "rows": rows}],
            },
        },
    }


def _build_button_payload(to_number: str, picker: QuickReplyPayload) -> dict[str, Any]:
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": str(action.get("id", index))[:256],
                "title": str(action.get("title", f"Option {index}"))[:20],
            },
        }
        for index, action in enumerate(picker.actions[:3], start=1)
    ]
    return {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": (picker.body or "Choose an option")[:1024]},
            "action": {"buttons": buttons},
        },
    }


async def _post_message(payload: dict[str, Any]) -> None:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not token:
        raise WhatsAppDeliveryError("WHATSAPP_ACCESS_TOKEN is not configured.")

    to_number = str(payload.get("to") or "")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(_messages_url(), json=payload, headers=_graph_headers())
        if response.status_code >= 400:
            detail = format_meta_graph_error(response, to_number=to_number or None)
            logger.error("Meta interactive send failed: status=%s body=%s", response.status_code, response.text)
            raise WhatsAppDeliveryError(detail, status_code=response.status_code)
        extract_meta_message_id(response)


async def _send_plain_text(to_number: str, body: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "text",
        "text": {"body": body[:4096]},
    }
    await _post_message(payload)


async def send_meta_interactive(to_number: str, payload: InteractivePayload) -> bool:
    if isinstance(payload, ListPickerPayload):
        if not payload.items:
            return False
        await _post_message(_build_list_payload(to_number, payload))
        return True
    if isinstance(payload, QuickReplyPayload):
        if not payload.actions:
            return False
        await _post_message(_build_button_payload(to_number, payload))
        return True
    return False


async def deliver_meta_intake_reply(to_number: str, reply: IntakeReply) -> str:
    """
    Deliver an intake reply on Meta Cloud API.

    Tries interactive list/button messages first, then falls back to numbered plain text.
    Returns the text stored in the message history table.
    """
    interactive: InteractivePayload | None = reply.quick_reply or reply.list_picker
    stored_text = compose_intake_message_text(reply)

    if interactive:
        payload: InteractivePayload = interactive
        if isinstance(payload, QuickReplyPayload):
            payload = QuickReplyPayload(
                kind=payload.kind,
                body=stored_text[:1024],
                actions=payload.actions,
            )
        elif isinstance(payload, ListPickerPayload):
            payload = ListPickerPayload(
                kind=payload.kind,
                body=stored_text[:1024],
                button=payload.button,
                items=payload.items,
            )

        try:
            sent = await send_meta_interactive(to_number, payload)
            if sent:
                return stored_text
            logger.warning(
                "Meta interactive intake had no sendable actions; falling back to plain text for %s",
                to_number,
            )
        except WhatsAppDeliveryError as exc:
            logger.warning("Meta interactive intake send failed, using text fallback: %s", exc)

    await _send_plain_text(to_number, stored_text)
    return stored_text
