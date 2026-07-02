from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead, LeadStage
from app.models.status_history import ChangedByType, StatusHistory
from app.models.user import User
from app.services.security_service import input_sanitizer
from app.services.status_consistency_service import (
    assert_single_active_pipeline_status,
    validate_status_data_consistency,
)
from app.services.status_definition_service import (
    STAGE_COUNSELLING_FINISHED,
    STAGE_LEAD_OUTREACH,
    STATUS_COUNSELLING_SCHEDULED,
    STATUS_LEAD_ENGAGEMENT,
    STATUS_LEAD_NEW,
    STATUS_LEAD_OUTREACH,
    STATUS_LEAD_SESSION_BOOKED,
    STATUS_LEAD_SESSION_CANCELLED,
    STATUS_LEAD_SESSION_RESCHEDULED,
    STATUS_LEAD_CANCELLED_NO_ANSWER,
    STATUS_LEAD_CANCELLED_NOT_INTERESTED,
    STATUS_LEAD_DEFERRED,
    STATUS_PROSPECT_CANCELLED,
    STATUS_PROSPECT_ENROLLED,
    STATUS_PROSPECT_RELAUNCH,
    get_status_definition,
)
from app.services.status_transition_service import can_transition_to, is_terminal_status
from app.services.system_log_service import log_system_event

ChangedByTypeLiteral = Literal["system", "admin"]

AUTOMATION_SOURCE = "status_automation"


def _format_user_name(user: User | None) -> str:
    if not user:
        return "System"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email or "Admin"


def record_status_history(
    db: Session,
    *,
    student_id: int,
    status_id: int,
    changed_by_type: ChangedByTypeLiteral,
    changed_by_user_id: int | None = None,
    comments: str | None = None,
    booking_id: int | None = None,
    created_at: datetime | None = None,
) -> StatusHistory:
    actor_type = ChangedByType.ADMIN if changed_by_type == "admin" else ChangedByType.SYSTEM
    row = StatusHistory(
        student_id=student_id,
        status_id=status_id,
        changed_by_user_id=changed_by_user_id,
        changed_by_type=actor_type,
        comments=comments,
        booking_id=booking_id,
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row


def _validate_before_update(db: Session, student_id: int) -> None:
    issues = validate_status_data_consistency(db, student_id=student_id)
    for issue in issues:
        log_system_event(
            db,
            level="warning",
            source="status_consistency",
            message=issue.message,
            context={"code": issue.code, **issue.details},
            student_id=student_id,
            commit=False,
        )


def update_student_status(
    db: Session,
    *,
    student_id: int,
    status_id: int,
    changed_by_type: ChangedByTypeLiteral,
    changed_by_user_id: int | None = None,
    comments: str | None = None,
    booking_id: int | None = None,
    booking: CounsellingBooking | None = None,
    skip_if_unchanged: bool = True,
    allow_override: bool = False,
    force_history: bool = False,
    commit: bool = True,
) -> dict:
    """Central entry point for pipeline status changes + history logging."""
    lead = db.query(Lead).filter(Lead.id == student_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Student not found.")

    assert_single_active_pipeline_status(lead)
    _validate_before_update(db, student_id)

    current_status_id = lead.status_definition_id
    if skip_if_unchanged and not force_history and current_status_id == status_id:
        return {
            "changed": False,
            "student_id": student_id,
            "status_id": status_id,
            "stage_name": None,
            "history_id": None,
            "trigger_outreach": False,
            "skipped": "unchanged_lead_status",
        }

    transition = can_transition_to(
        db,
        current_status_id,
        status_id,
        allow_override=allow_override,
        force_repeat=force_history,
    )
    if not transition.allowed:
        if changed_by_type == "system":
            log_system_event(
                db,
                level="error",
                source=AUTOMATION_SOURCE,
                message=transition.reason,
                context={
                    "current_status_id": current_status_id,
                    "requested_status_id": status_id,
                },
                student_id=student_id,
                commit=commit,
            )
            return {
                "changed": False,
                "blocked": True,
                "student_id": student_id,
                "status_id": status_id,
                "reason": transition.reason,
            }
        raise HTTPException(status_code=400, detail=transition.reason)

    sanitized_comments = input_sanitizer(comments) if comments else None
    if transition.requires_override_comment and not (sanitized_comments or "").strip():
        detail = "A comment is required when overriding the standard pipeline flow."
        if changed_by_type == "admin":
            raise HTTPException(status_code=400, detail=detail)
        log_system_event(
            db,
            level="error",
            source=AUTOMATION_SOURCE,
            message=detail,
            context={
                "current_status_id": current_status_id,
                "requested_status_id": status_id,
                "transition_reason": transition.reason,
            },
            student_id=student_id,
            commit=commit,
        )
        return {"changed": False, "blocked": True, "student_id": student_id, "reason": detail}

    if transition.is_override and sanitized_comments and not sanitized_comments.startswith("[Override]"):
        sanitized_comments = f"[Override] {sanitized_comments}"

    definition = get_status_definition(db, status_id)
    now = datetime.utcnow()
    previous_id = current_status_id

    if force_history and current_status_id == status_id:
        history = record_status_history(
            db,
            student_id=lead.id,
            status_id=definition.id,
            changed_by_type=changed_by_type,
            changed_by_user_id=changed_by_user_id,
            comments=sanitized_comments,
            booking_id=booking_id,
        )
        lead.status_entered_at = now
        lead.updated_at = now
        if commit:
            db.commit()
            db.refresh(lead)
        else:
            db.flush()
        return {
            "changed": True,
            "student_id": lead.id,
            "previous_status_id": previous_id,
            "status_id": definition.id,
            "stage_name": definition.stage_name,
            "history_id": history.id,
            "trigger_outreach": False,
            "booking_id": booking_id,
            "booking_status": booking.status if booking else None,
            "override": False,
            "repeated": True,
        }

    lead.status_definition_id = definition.id
    lead.status_entered_at = now
    lead.updated_at = now

    if definition.category == "Counselling":
        lead.admission_stage = "COUNSELLING"
        lead.admission_stage_entered_at = now
    elif definition.category == "Admission":
        lead.admission_stage = "APPLIED"
        lead.admission_stage_entered_at = now
    elif definition.id == STATUS_PROSPECT_ENROLLED:
        lead.admission_stage = "ENROLLED"
        lead.admission_stage_entered_at = now
    elif definition.id in {STATUS_PROSPECT_CANCELLED, STATUS_PROSPECT_RELAUNCH}:
        lead.admission_stage = "ARCHIVED"
        lead.admission_stage_entered_at = now

    history = record_status_history(
        db,
        student_id=lead.id,
        status_id=definition.id,
        changed_by_type=changed_by_type,
        changed_by_user_id=changed_by_user_id,
        comments=sanitized_comments,
        booking_id=booking_id,
    )

    trigger_outreach = False
    if definition.stage_name == STAGE_LEAD_OUTREACH:
        from app.models.consultation_slot import ConsultationSlot
        from app.services.counselling_service import cancel_active_counselling_bookings_for_lead

        slot = db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).first()
        if slot:
            slot.lead_id = None
        lead.consultation_scheduled_at = None
        lead.calendar_booking_id = None
        cancel_active_counselling_bookings_for_lead(db, lead.id, commit=False)
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        trigger_outreach = changed_by_type == "admin"

    if definition.stage_name == STAGE_COUNSELLING_FINISHED and booking is not None:
        booking.status = "COMPLETED"
        booking.completed_at = now
        booking.updated_at = now

    if definition.id == STATUS_PROSPECT_RELAUNCH:
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        trigger_outreach = True

    if commit:
        db.commit()
        db.refresh(lead)
        if booking is not None:
            db.refresh(booking)
    else:
        db.flush()

    if (
        previous_id != definition.id
        and definition.id
        in {
            STATUS_LEAD_CANCELLED_NO_ANSWER,
            STATUS_LEAD_CANCELLED_NOT_INTERESTED,
            STATUS_LEAD_DEFERRED,
        }
    ):
        from app.services.status_closure_notifications import notify_lead_status_closure_whatsapp

        notify_lead_status_closure_whatsapp(db, lead, status_id=definition.id)

    return {
        "changed": True,
        "student_id": lead.id,
        "previous_status_id": previous_id,
        "status_id": definition.id,
        "stage_name": definition.stage_name,
        "history_id": history.id,
        "trigger_outreach": trigger_outreach,
        "booking_id": booking.id if booking else booking_id,
        "booking_status": booking.status if booking else None,
        "override": transition.is_override,
    }


def try_automated_status_transition(
    db: Session,
    lead: Lead,
    *,
    status_id: int,
    source: str,
    comments: str | None = None,
    booking_id: int | None = None,
    commit: bool = True,
    force_history: bool = False,
) -> dict:
    """Safe automation entry point — never raises; logs invalid attempts."""
    if is_terminal_status(lead.status_definition_id):
        message = (
            f"Automated transition blocked: student is in terminal status "
            f"{lead.status_definition_id}."
        )
        log_system_event(
            db,
            level="error",
            source=AUTOMATION_SOURCE,
            message=message,
            context={"handler": source, "requested_status_id": status_id},
            student_id=lead.id,
            commit=commit,
        )
        return {"changed": False, "blocked": True, "reason": message}

    return update_student_status(
        db,
        student_id=lead.id,
        status_id=status_id,
        changed_by_type="system",
        comments=comments,
        booking_id=booking_id,
        skip_if_unchanged=not force_history,
        allow_override=False,
        force_history=force_history,
        commit=commit,
    )


def on_session_rescheduled(
    db: Session,
    lead: Lead,
    *,
    source: str,
    had_active_booking: bool = True,
) -> None:
    comment = (
        "Student requested to reschedule their consultation via WhatsApp."
        if had_active_booking
        else "Student started the consultation scheduling flow again."
    )
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_SESSION_RESCHEDULED,
        source=source,
        comments=comment,
        force_history=True,
        commit=True,
    )


def on_session_cancelled(
    db: Session,
    lead: Lead,
    *,
    source: str,
    had_active_booking: bool = True,
) -> None:
    comment = (
        "Student cancelled their consultation appointment via WhatsApp."
        if had_active_booking
        else "Student sent a cancel request with no active appointment on file."
    )
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_SESSION_CANCELLED,
        source=source,
        comments=comment,
        force_history=True,
        commit=True,
    )


def get_student_journey(db: Session, student_id: int) -> list[dict]:
    from app.models.status_definition import StatusDefinition

    rows = (
        db.query(StatusHistory, StatusDefinition, User)
        .join(StatusDefinition, StatusDefinition.id == StatusHistory.status_id)
        .outerjoin(User, User.id == StatusHistory.changed_by_user_id)
        .filter(StatusHistory.student_id == student_id)
        .order_by(StatusHistory.created_at.asc(), StatusHistory.id.asc())
        .all()
    )
    return [
        {
            "id": history.id,
            "status_id": definition.id,
            "stage_name": definition.stage_name,
            "category": definition.category,
            "description": definition.description,
            "changed_by_type": history.changed_by_type.value,
            "changed_by_user_id": history.changed_by_user_id,
            "changed_by_label": (
                _format_user_name(user)
                if history.changed_by_type == ChangedByType.ADMIN
                else "System"
            ),
            "comments": history.comments,
            "created_at": history.created_at,
        }
        for history, definition, user in rows
    ]


def on_lead_created(db: Session, lead: Lead, *, source: str) -> None:
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_NEW,
        source=source,
        comments=f"Lead created via {source}.",
        commit=True,
    )


def on_whatsapp_outreach(db: Session, lead: Lead, *, source: str) -> None:
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_OUTREACH,
        source=source,
        comments=f"WhatsApp outreach triggered ({source}).",
        commit=True,
    )


def on_whatsapp_inbound(db: Session, lead: Lead) -> None:
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_ENGAGEMENT,
        source="whatsapp_inbound",
        comments="Student replied on WhatsApp.",
        commit=True,
    )


def on_session_booked(db: Session, lead: Lead) -> None:
    try_automated_status_transition(
        db,
        lead,
        status_id=STATUS_LEAD_SESSION_BOOKED,
        source="session_booked",
        comments="Counselling session confirmed via WhatsApp.",
        commit=True,
    )


def on_counselling_scheduled(
    db: Session,
    lead: Lead,
    *,
    booking_id: int | None,
    counsellor_id: int | None,
    changed_by_type: ChangedByTypeLiteral = "system",
) -> None:
    if changed_by_type == "system":
        try_automated_status_transition(
            db,
            lead,
            status_id=STATUS_COUNSELLING_SCHEDULED,
            source="counselling_scheduled",
            comments="Counselling appointment scheduled.",
            booking_id=booking_id,
            commit=True,
        )
        return

    update_student_status(
        db,
        student_id=lead.id,
        status_id=STATUS_COUNSELLING_SCHEDULED,
        changed_by_type="admin",
        changed_by_user_id=counsellor_id,
        comments="Counselling appointment scheduled.",
        booking_id=booking_id,
        skip_if_unchanged=True,
        allow_override=True,
        commit=False,
    )
