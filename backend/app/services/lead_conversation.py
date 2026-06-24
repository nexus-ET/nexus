from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.services.phone_utils import phone_match_keys


def lead_has_advisor_messages(db: Session, lead_id: int) -> bool:
    if (
        db.query(Message.id)
        .filter(
            Message.lead_id == lead_id,
            Message.sender.in_(["advisor", "user", "system"]),
        )
        .first()
        is not None
    ):
        return True

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    summary = getattr(lead, "academic_summary", None) if lead else None
    return bool(summary and "Advisor:" in summary)


def is_human_handoff_lead(lead: Lead) -> bool:
    """True only when a human advisor owns the thread (not routine AI Active chat)."""
    stage = str(lead.stage or "").upper()
    return bool(lead.is_human_locked or "HANDOFF" in stage or "HUMAN" in stage)


def is_active_handoff_conversation(db: Session, lead: Lead) -> bool:
    stage = str(lead.stage or "").upper()
    if lead.is_human_locked or "HANDOFF" in stage or "HUMAN" in stage:
        return True
    return lead_has_advisor_messages(db, lead.id)


def ensure_handoff_for_inbound(db: Session, lead: Lead) -> None:
    lead.stage = LeadStage.HANDOFF
    lead.is_human_locked = True
    lead.updated_at = datetime.utcnow()


def touch_lead_activity(db: Session, lead: Lead) -> None:
    lead.updated_at = datetime.utcnow()


def find_lead_for_inbound_whatsapp(db: Session, raw_phone: str | None) -> Lead | None:
    keys = phone_match_keys(raw_phone)
    if not keys:
        return None

    candidates: list[Lead] = []
    for lead in db.query(Lead).filter(Lead.phone_number.isnot(None)).all():
        if keys & phone_match_keys(lead.phone_number):
            candidates.append(lead)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def rank(lead: Lead) -> tuple[int, int, datetime]:
        stage = str(lead.stage or "").upper()
        is_handoff = int(
            lead.is_human_locked or "HANDOFF" in stage or "HUMAN" in stage
        )
        has_advisor = int(lead_has_advisor_messages(db, lead.id))
        updated = lead.updated_at or datetime.min
        return (is_handoff, has_advisor, updated)

    return max(candidates, key=rank)
