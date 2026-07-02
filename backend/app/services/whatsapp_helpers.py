from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadStage
from app.services.lead_conversation import ensure_handoff_for_inbound, is_human_handoff_lead
from app.services.lead_conversation import find_lead_for_inbound_whatsapp
from app.services.phone_utils import (
    build_inbound_whatsapp_lead_name,
    clean_phone_number,
    digits_only,
)

logger = logging.getLogger(__name__)


@dataclass
class InboundWhatsAppMessage:
    message_id: str
    sender_phone: str
    wa_id: str
    message_text: str


def clean_phone_number(raw_phone: str) -> str:
    if not raw_phone:
        return ""
    cleaned = str(raw_phone).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned.replace("whatsapp:", "", 1)
    return cleaned


def extract_inbound_messages(payload: dict[str, Any]) -> list[InboundWhatsAppMessage]:
    messages: list[InboundWhatsAppMessage] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            contacts = value.get("contacts") or []
            contact_wa_id = contacts[0].get("wa_id") if contacts else None

            for message in value.get("messages") or []:
                message_id = message.get("id")
                sender_phone = message.get("from") or contact_wa_id
                wa_id = contact_wa_id or sender_phone
                message_text = _extract_message_text(message)

                if not message_id or not sender_phone or not message_text:
                    logger.debug("Skipping incomplete WhatsApp message payload: %s", message)
                    continue

                messages.append(
                    InboundWhatsAppMessage(
                        message_id=str(message_id),
                        sender_phone=clean_phone_number(str(sender_phone)),
                        wa_id=clean_phone_number(str(wa_id or sender_phone)),
                        message_text=message_text.strip(),
                    )
                )

    return messages


def _extract_message_text(message: dict[str, Any]) -> str:
    message_type = message.get("type")
    if message_type == "text":
        return (message.get("text") or {}).get("body") or ""
    if message_type == "button":
        return (message.get("button") or {}).get("text") or ""
    if message_type == "interactive":
        interactive = message.get("interactive") or {}
        if "button_reply" in interactive:
            reply = interactive.get("button_reply") or {}
            return (reply.get("id") or reply.get("title") or "").strip()
        if "list_reply" in interactive:
            reply = interactive.get("list_reply") or {}
            return (reply.get("id") or reply.get("title") or "").strip()
    return ""


def get_or_create_lead_for_phone(db: Session, sender_phone: str, wa_id: str) -> Lead:
    phone = clean_phone_number(sender_phone)
    lead = find_lead_for_inbound_whatsapp(db, phone or wa_id)

    if lead:
        if is_human_handoff_lead(lead):
            ensure_handoff_for_inbound(db, lead)
            db.commit()
            db.refresh(lead)
        return lead

    safe_slug = digits_only(phone or wa_id) or "unknown"
    lead = Lead(
        full_name=build_inbound_whatsapp_lead_name(phone or wa_id),
        email=f"wa_{safe_slug}@whatsapp.nexus",
        phone_number=phone or clean_phone_number(wa_id),
        channel=LeadChannel.WHATSAPP,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    from app.services.student_status_service import on_lead_created

    on_lead_created(db, lead, source="WhatsApp inbound")
    return lead
