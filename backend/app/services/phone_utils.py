from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.lead import Lead

# ITU E.161 / NANP vanity keypad mapping (e.g. CAREY -> 22739).
_VANITY_KEYPAD = {
    "a": "2",
    "b": "2",
    "c": "2",
    "d": "3",
    "e": "3",
    "f": "3",
    "g": "4",
    "h": "4",
    "i": "4",
    "j": "5",
    "k": "5",
    "l": "5",
    "m": "6",
    "n": "6",
    "o": "6",
    "p": "7",
    "q": "7",
    "r": "7",
    "s": "7",
    "t": "8",
    "u": "8",
    "v": "8",
    "w": "9",
    "x": "9",
    "y": "9",
    "z": "9",
}


def digits_only(phone: str | None) -> str:
    """Return keypad digits, converting vanity letters (e.g. CAREY -> 22739)."""
    if not phone:
        return ""
    text = str(phone).replace("whatsapp:", "", 1)
    mapped: list[str] = []
    for char in text:
        lower = char.lower()
        if lower in _VANITY_KEYPAD:
            mapped.append(_VANITY_KEYPAD[lower])
        elif char.isdigit():
            mapped.append(char)
    return "".join(mapped)


def clean_phone_number(raw_phone: str | None) -> str:
    digits = digits_only(raw_phone)
    if not digits:
        return ""
    return f"+{digits}" if not str(raw_phone or "").strip().startswith("+") else f"+{digits}"


def format_phone_display(raw_phone: str | None) -> str:
    cleaned = clean_phone_number(raw_phone)
    return cleaned or "Unknown number"


def build_inbound_whatsapp_lead_name(
    raw_phone: str | None,
    profile_name: str | None = None,
) -> str:
    display_name = str(profile_name or "").strip()
    if display_name and display_name.lower() not in {"unknown", "whatsapp user"}:
        return display_name[:255]
    return f"WhatsApp Contact ({format_phone_display(raw_phone)})"


def phone_match_keys(raw_phone: str | None) -> set[str]:
    digits = digits_only(raw_phone)
    if not digits:
        return set()

    keys = {digits, f"+{digits}"}
    if len(digits) >= 8:
        keys.add(digits[-8:])
    if len(digits) >= 10:
        keys.add(digits[-10:])
    return keys


def find_lead_by_phone(db: Session, raw_phone: str | None) -> Lead | None:
    from app.services.lead_conversation import find_lead_for_inbound_whatsapp

    return find_lead_for_inbound_whatsapp(db, raw_phone)


def find_lead_by_phone_query(db: Session, raw_phone: str | None):
    digits = digits_only(raw_phone)
    if not digits:
        return db.query(Lead).filter(Lead.id == -1)

    suffix = digits[-8:] if len(digits) >= 8 else digits
    return db.query(Lead).filter(
        or_(
            Lead.phone_number == digits,
            Lead.phone_number == f"+{digits}",
            Lead.phone_number.contains(suffix),
        )
    )


def _dig_interactive_selection(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""

    for key in ("list_reply", "button_reply"):
        reply = payload.get(key)
        if isinstance(reply, dict):
            reply_id = str(reply.get("id") or "").strip()
            reply_title = str(reply.get("title") or reply.get("text") or "").strip()
            if reply_id or reply_title:
                return reply_id, reply_title

    for nested_key in ("data", "context", "interactive"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            reply_id, reply_title = _dig_interactive_selection(nested)
            if reply_id or reply_title:
                return reply_id, reply_title

    reply_id = str(payload.get("id") or payload.get("postbackData") or "").strip()
    reply_title = str(payload.get("title") or payload.get("text") or "").strip()
    return reply_id, reply_title


def extract_inbound_whatsapp_text(form_data: Mapping[str, Any]) -> str:
    """
    Normalize Twilio WhatsApp inbound text, including list-picker and button replies
    where Body may be empty but ButtonPayload / InteractiveData carry the selection.
    """
    body = str(form_data.get("Body") or "").strip()
    if body:
        return body

    button_payload = str(form_data.get("ButtonPayload") or "").strip()
    if button_payload:
        return button_payload

    button_text = str(form_data.get("ButtonText") or "").strip()
    if button_text:
        return button_text

    interactive_raw = form_data.get("InteractiveData")
    if interactive_raw:
        try:
            if isinstance(interactive_raw, (bytes, bytearray)):
                interactive_raw = interactive_raw.decode("utf-8", errors="ignore")
            payload = json.loads(interactive_raw) if isinstance(interactive_raw, str) else interactive_raw
            reply_id, reply_title = _dig_interactive_selection(payload)
            if reply_id:
                return reply_id
            if reply_title:
                return reply_title
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    list_id = str(form_data.get("ListId") or form_data.get("ListReply") or "").strip()
    if list_id:
        return list_id

    return ""
