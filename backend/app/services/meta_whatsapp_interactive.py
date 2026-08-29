"""Send WhatsApp interactive messages via Meta Cloud API (Graph)."""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from app.config import settings
from app.services.admissions_intake_flow import IntakeReply
from app.services.messaging import (
    WHATSAPP_GRAPH_API_BASE,
    WhatsAppDeliveryError,
    extract_meta_message_id,
    format_meta_graph_error,
    get_whatsapp_graph_http_client,
)
from app.services.phone_utils import clean_phone_number
from app.services.twilio_whatsapp_interactive import (
    FlowPayload,
    InteractivePayload,
    ListPickerPayload,
    QuickReplyPayload,
    build_text_fallback,
)
from app.services.whatsapp_config import resolve_whatsapp_phone_number_id

logger = logging.getLogger(__name__)

_REPLY_NUMBER_PROMPT_RE = re.compile(
    r"(?:\n+\s*)?Reply with the number of your choice:?\s*$",
    re.IGNORECASE,
)


def _strip_reply_number_prompt(text: str) -> str:
    cleaned = _REPLY_NUMBER_PROMPT_RE.sub("", (text or "").strip())
    return cleaned.strip()


def _list_title_with_icon(label: str, picker_kind: str) -> str:
    """Decorate study choices while keeping Meta's 24-character row limit."""
    normalized_kind = (picker_kind or "").strip().lower()
    if normalized_kind == "degree":
        return f"🎓 {label}"[:24]
    if normalized_kind != "major":
        return label[:24]

    lowered = label.lower()
    if any(term in lowered for term in ("computer", "data", "software", " ai")):
        icon = "💻"
    elif any(term in lowered for term in ("business", "management", "mba")):
        icon = "💼"
    elif any(term in lowered for term in ("finance", "account")):
        icon = "💰"
    elif "engineer" in lowered:
        icon = "⚙️"
    elif any(term in lowered for term in ("health", "medicine", "medical")):
        icon = "🩺"
    elif any(term in lowered for term in ("art", "humanit", "design")):
        icon = "🎨"
    elif "law" in lowered:
        icon = "⚖️"
    else:
        icon = "📚"
    return f"{icon} {label}"[:24]


def _graph_headers() -> dict[str, str]:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _messages_url() -> str:
    phone_number_id = resolve_whatsapp_phone_number_id()
    if not phone_number_id:
        raise WhatsAppDeliveryError("WHATSAPP_PHONE_NUMBER_ID is not configured.")
    return f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"


def compose_intake_message_text(reply: IntakeReply) -> str:
    """Human-facing prompt for intake replies (no numbered 'reply with N' fallback text)."""
    intro = (reply.text or "").strip()
    interactive: InteractivePayload | None = reply.quick_reply or reply.list_picker
    if not interactive:
        return _strip_reply_number_prompt(intro or "Please reply to continue.")

    # Prefer the agent/template prompt. Interactive buttons/lists carry the choices.
    body = intro or (interactive.body or "").strip()
    return _strip_reply_number_prompt(body or "Please reply to continue.")


def compose_intake_plain_text_fallback(reply: IntakeReply) -> str:
    """Numbered plain-text fallback used only when interactive send is unavailable."""
    interactive: InteractivePayload | None = reply.quick_reply or reply.list_picker
    prompt = compose_intake_message_text(reply)
    if not interactive:
        return prompt

    if isinstance(interactive, QuickReplyPayload):
        payload: InteractivePayload = QuickReplyPayload(
            kind=interactive.kind,
            body=prompt,
            actions=interactive.actions,
        )
    else:
        payload = ListPickerPayload(
            kind=interactive.kind,
            body=prompt,
            button=interactive.button,
            items=interactive.items,
        )
    return build_text_fallback(payload)


def _build_list_row(item: dict[str, Any], index: int, *, picker_kind: str) -> dict[str, str]:
    item_id = str(item.get("id", index))
    label = str(item.get("item", f"Option {index}"))
    description = str(item.get("description", ""))

    if picker_kind == "date" and item_id.lower().startswith("date:"):
        try:
            slot_day = date.fromisoformat(item_id.split(":", 1)[1])
        except ValueError:
            pass
        else:
            lowered = label.strip().lower()
            if lowered.startswith("today"):
                title = f"Today {slot_day.strftime('%d %b, %Y')}"
            elif lowered.startswith("tomorrow"):
                title = f"Tomorrow {slot_day.strftime('%d %b, %Y')}"
            else:
                title = slot_day.strftime("%a %d %b, %Y")
            return {
                "id": item_id[:200],
                "title": title[:24],
            }

    row = {
        "id": item_id[:200],
        "title": _list_title_with_icon(label, picker_kind),
    }
    if description and picker_kind != "time":
        row["description"] = description[:72]
    return row


def _build_list_payload(to_number: str, picker: ListPickerPayload) -> dict[str, Any]:
    rows = [
        _build_list_row(item, index, picker_kind=picker.kind)
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


def _build_flow_payload(to_number: str, flow: FlowPayload) -> dict[str, Any]:
    """Build Meta Cloud API's native WhatsApp Flow message."""
    return {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {"text": flow.body[:1024]},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": flow.flow_token[:256],
                    "flow_id": flow.flow_id,
                    "flow_cta": flow.button[:20],
                    "flow_action": "navigate",
                    "flow_action_payload": {"screen": "BOOKING"},
                },
            },
        },
    }


async def _post_message(payload: dict[str, Any]) -> None:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not token:
        raise WhatsAppDeliveryError("WHATSAPP_ACCESS_TOKEN is not configured.")

    to_number = str(payload.get("to") or "")
    response = await get_whatsapp_graph_http_client().post(
        _messages_url(),
        json=payload,
        headers=_graph_headers(),
    )
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


async def send_meta_interactive(
    to_number: str,
    payload: InteractivePayload | FlowPayload,
) -> bool:
    if isinstance(payload, FlowPayload):
        await _post_message(_build_flow_payload(to_number, payload))
        return True
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
    prompt_text = compose_intake_message_text(reply)

    if reply.whatsapp_flow:
        try:
            await send_meta_interactive(to_number, reply.whatsapp_flow)
            return prompt_text
        except WhatsAppDeliveryError as exc:
            logger.warning(
                "Meta Flow send failed; using list/button fallback for %s: %s",
                to_number,
                exc,
            )

    interactive: InteractivePayload | None = reply.quick_reply or reply.list_picker
    if interactive:
        payload: InteractivePayload = interactive
        if isinstance(payload, QuickReplyPayload):
            payload = QuickReplyPayload(
                kind=payload.kind,
                body=prompt_text[:1024],
                actions=payload.actions,
            )
        elif isinstance(payload, ListPickerPayload):
            payload = ListPickerPayload(
                kind=payload.kind,
                body=prompt_text[:1024],
                button=payload.button,
                items=payload.items,
            )

        try:
            sent = await send_meta_interactive(to_number, payload)
            if sent:
                return prompt_text
            logger.warning(
                "Meta interactive intake had no sendable actions; falling back to plain text for %s",
                to_number,
            )
        except WhatsAppDeliveryError as exc:
            logger.warning("Meta interactive intake send failed, using text fallback: %s", exc)

    fallback_text = compose_intake_plain_text_fallback(reply)
    await _send_plain_text(to_number, fallback_text)
    return fallback_text
