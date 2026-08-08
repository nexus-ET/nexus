from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.services.phone_utils import phone_match_keys
from app.utils.timezone import utc_now


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
    lead.updated_at = utc_now()


AI_AUTO_HANDOFF_REASON_PREFIXES = (
    "AI confidence below escalation threshold",
    "AI could not generate a reliable answer",
)


def is_human_requested_handoff(lead: Lead) -> bool:
    """Handoff explicitly requested by the student or because the agent is inactive."""
    reason = (lead.handoff_reason or "").strip().lower()
    if not reason:
        return False
    if reason in {"keyword trigger", "agent inactive"}:
        return True
    return reason.startswith("keyword") or reason.startswith("agent inactive")


def should_retry_ai_after_handoff(lead: Lead) -> bool:
    """
    Allow Ollama to answer follow-up questions when the previous handoff was caused
    by an empty AI response, not when the student asked for a human advisor.
    """
    if not is_human_handoff_lead(lead):
        return False
    if is_human_requested_handoff(lead):
        return False
    reason = (lead.handoff_reason or "").strip()
    if not reason:
        return True
    return any(reason.startswith(prefix) for prefix in AI_AUTO_HANDOFF_REASON_PREFIXES)


def release_ai_handoff(db: Session, lead: Lead) -> None:
    """Return an AI-auto-handoff lead to the automated assistant."""
    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    lead.handoff_reason = None
    lead.handoff_ai_confidence = None
    lead.updated_at = utc_now()


def touch_lead_activity(db: Session, lead: Lead) -> None:
    lead.updated_at = utc_now()


def _inbound_lead_rank(db: Session, lead: Lead) -> tuple[int, int, int, int, datetime]:
    """Prefer non-handoff leads with an active intake session, then AI-Active outreach threads."""
    from app.services.admissions_intake_flow import INTAKE_STEP_COMPLETE, get_intake_step

    stage = str(lead.stage or "").upper()
    is_handoff = int(
        lead.is_human_locked or "HANDOFF" in stage or "HUMAN" in stage
    )
    step = get_intake_step(lead)
    intake_active = int(
        bool(getattr(lead, "intake_step", None)) and step != INTAKE_STEP_COMPLETE
    )
    is_ai_active = int("AI_ACTIVE" in stage)
    has_advisor = int(lead_has_advisor_messages(db, lead.id))
    updated = lead.updated_at or datetime.min
    return (-is_handoff, intake_active, is_ai_active, has_advisor, updated)


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

    return max(candidates, key=lambda lead: _inbound_lead_rank(db, lead))
