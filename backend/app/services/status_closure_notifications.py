from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.message import Message
from app.services.admissions_intake_flow import BRAND_NAME
from app.services.lead_conversation import touch_lead_activity
from app.services.messaging import _recent_identical_outbound, send_message_sync
from app.services.phone_utils import clean_phone_number
from app.services.status_definition_service import (
    STATUS_LEAD_CANCELLED_NO_ANSWER,
    STATUS_LEAD_CANCELLED_NOT_INTERESTED,
    STATUS_LEAD_DEFERRED,
)
from app.services.system_log_service import log_system_event

logger = logging.getLogger(__name__)

CLOSURE_WHATSAPP_STATUS_IDS = frozenset(
    {
        STATUS_LEAD_CANCELLED_NO_ANSWER,
        STATUS_LEAD_CANCELLED_NOT_INTERESTED,
        STATUS_LEAD_DEFERRED,
    }
)

_REOPEN_INVITATION = (
    "Whenever you would like to continue, you can always message us here with your "
    "questions or to book a consultation — we will be glad to help."
)


def _lead_first_name(lead: Lead) -> str:
    name = (lead.full_name or "there").strip()
    return name.split()[0] if name else "there"


def render_closure_whatsapp_message(*, lead: Lead, status_id: int) -> str | None:
    first = _lead_first_name(lead)
    if status_id == STATUS_LEAD_CANCELLED_NO_ANSWER:
        return (
            f"Hi {first}, thank you for connecting with {BRAND_NAME}. "
            "We have not been able to reach you recently, so we have paused follow-up for now. "
            f"{_REOPEN_INVITATION}"
        )
    if status_id == STATUS_LEAD_CANCELLED_NOT_INTERESTED:
        return (
            f"Hi {first}, thank you for taking the time to speak with us at {BRAND_NAME}. "
            "We understand you have decided not to continue at this time, and we respect your decision. "
            f"{_REOPEN_INVITATION}"
        )
    if status_id == STATUS_LEAD_DEFERRED:
        return (
            f"Hi {first}, thank you for sharing your plans with {BRAND_NAME}. "
            "We have noted that you would like to postpone for now. "
            f"{_REOPEN_INVITATION}"
        )
    return None


def notify_lead_status_closure_whatsapp(db: Session, lead: Lead, *, status_id: int) -> bool:
    """
    Send a polite WhatsApp note when a lead is marked closed/deferred by an admin.
    Never raises — failures are logged for follow-up.
    """
    if status_id not in CLOSURE_WHATSAPP_STATUS_IDS:
        return False

    message = render_closure_whatsapp_message(lead=lead, status_id=status_id)
    if not message:
        return False

    phone = clean_phone_number(lead.phone_number or "")
    if not phone:
        log_system_event(
            db,
            level="warning",
            source="status_closure_whatsapp",
            message="Skipped closure WhatsApp — lead has no phone number.",
            context={"status_id": status_id},
            student_id=lead.id,
            commit=True,
        )
        return False

    if _recent_identical_outbound(db, lead.id, message, within_minutes=60):
        return False

    try:
        sent = send_message_sync(phone, message)
    except Exception:
        logger.exception("Closure WhatsApp send failed for lead_id=%s", lead.id)
        log_system_event(
            db,
            level="error",
            source="status_closure_whatsapp",
            message="Failed to send closure WhatsApp message.",
            context={"status_id": status_id, "phone": phone},
            student_id=lead.id,
            commit=True,
        )
        return False

    if not sent:
        log_system_event(
            db,
            level="warning",
            source="status_closure_whatsapp",
            message="Closure WhatsApp message was not delivered.",
            context={"status_id": status_id, "phone": phone},
            student_id=lead.id,
            commit=True,
        )
        return False

    db.add(
        Message(
            lead_id=lead.id,
            sender="advisor",
            text=message,
            ai_confidence=1.0,
            is_read=True,
        )
    )
    touch_lead_activity(db, lead)
    db.commit()
    return True
