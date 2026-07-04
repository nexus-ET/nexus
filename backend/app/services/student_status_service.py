from __future__ import annotations

import logging
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
    LEAD_FUNNEL_STAGE_NAMES,
    STAGE_COUNSELLING_FINISHED,
    STAGE_LEAD_ENGAGEMENT,
    STAGE_LEAD_NEW,
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
    get_status_definition_by_name,
    resolve_status_id_by_name,
)
from app.services.status_transition_service import (
    TransitionTypeLiteral,
    build_express_transition_comment,
    can_transition_to,
    get_valid_transitions,
    is_terminal_status,
)
from app.services.system_log_service import log_system_event

logger = logging.getLogger(__name__)

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


def _status_history_has_stage(db: Session, student_id: int, stage_name: str) -> bool:
    from app.models.status_definition import StatusDefinition

    return (
        db.query(StatusHistory.id)
        .join(StatusDefinition, StatusDefinition.id == StatusHistory.status_id)
        .filter(
            StatusHistory.student_id == student_id,
            StatusDefinition.stage_name == stage_name,
        )
        .first()
        is not None
    )


def resolve_effective_lead_status_id(db: Session, lead: Lead) -> int | None:
    """Current pipeline status from the lead row, or the latest status_history row."""
    if lead.status_definition_id is not None:
        return lead.status_definition_id

    latest = (
        db.query(StatusHistory.status_id)
        .filter(StatusHistory.student_id == lead.id)
        .order_by(StatusHistory.created_at.desc(), StatusHistory.id.desc())
        .first()
    )
    return int(latest[0]) if latest else None


def sync_lead_pipeline_status_id(db: Session, lead: Lead) -> bool:
    """
    Align leads.status_definition_id with journey history when the FK was never set.
    """
    if lead.status_definition_id is not None:
        return False

    effective = resolve_effective_lead_status_id(db, lead)
    if effective is None:
        return False

    lead.status_definition_id = effective
    lead.status_entered_at = lead.status_entered_at or datetime.utcnow()
    lead.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return True


def _infer_funnel_history_time(db: Session, lead: Lead, stage_name: str) -> datetime:
    from app.models.message import Message

    if stage_name == STAGE_LEAD_NEW:
        return lead.created_at or datetime.utcnow()

    if stage_name == STAGE_LEAD_OUTREACH:
        advisor_msg = (
            db.query(Message.created_at)
            .filter(Message.lead_id == lead.id, Message.sender == "advisor")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        if advisor_msg and advisor_msg[0]:
            return advisor_msg[0]
        return lead.status_entered_at or lead.updated_at or datetime.utcnow()

    if stage_name == STAGE_LEAD_ENGAGEMENT:
        candidate_msg = (
            db.query(Message.created_at)
            .filter(Message.lead_id == lead.id, Message.sender == "candidate")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        if candidate_msg and candidate_msg[0]:
            return candidate_msg[0]
        return lead.status_entered_at or lead.updated_at or datetime.utcnow()

    return lead.status_entered_at or lead.updated_at or datetime.utcnow()


def ensure_funnel_journey_history(db: Session, lead: Lead, *, source: str) -> bool:
    """
    Backfill Lead funnel rows in status_history from WhatsApp activity when missing.

    Repairs staging leads where outreach ran but pipeline transitions were blocked.
    """
    from app.models.message import Message
    from app.models.status_definition import StatusDefinition
    from app.services.status_definitions_seed import ensure_status_definition_funnel_links

    ensure_status_definition_funnel_links(db)

    stages_to_ensure: list[str] = [STAGE_LEAD_NEW]
    has_advisor = (
        db.query(Message.id)
        .filter(Message.lead_id == lead.id, Message.sender == "advisor")
        .first()
        is not None
    )
    has_candidate = (
        db.query(Message.id)
        .filter(Message.lead_id == lead.id, Message.sender == "candidate")
        .first()
        is not None
    )
    if has_advisor:
        stages_to_ensure.append(STAGE_LEAD_OUTREACH)
    if has_candidate:
        stages_to_ensure.append(STAGE_LEAD_ENGAGEMENT)

    effective = resolve_effective_lead_status_id(db, lead)
    if effective is not None:
        effective_def = db.query(StatusDefinition).filter(StatusDefinition.id == effective).first()
        if effective_def and effective_def.stage_name in LEAD_FUNNEL_STAGE_NAMES:
            idx = LEAD_FUNNEL_STAGE_NAMES.index(effective_def.stage_name)
            for stage_name in LEAD_FUNNEL_STAGE_NAMES[: idx + 1]:
                if stage_name not in stages_to_ensure:
                    stages_to_ensure.append(stage_name)

    changed = False
    ordered = [name for name in LEAD_FUNNEL_STAGE_NAMES if name in stages_to_ensure]
    for stage_name in ordered:
        if _status_history_has_stage(db, lead.id, stage_name):
            continue
        definition = get_status_definition_by_name(db, stage_name)
        if definition is None:
            continue
        comments = {
            STAGE_LEAD_NEW: "Lead record created.",
            STAGE_LEAD_OUTREACH: f"WhatsApp outreach recorded ({source}).",
            STAGE_LEAD_ENGAGEMENT: "Student replied on WhatsApp.",
        }.get(stage_name, f"Pipeline stage recorded ({source}).")
        record_status_history(
            db,
            student_id=lead.id,
            status_id=definition.id,
            changed_by_type="system",
            comments=comments,
            created_at=_infer_funnel_history_time(db, lead, stage_name),
        )
        changed = True

    if changed:
        for stage_name in reversed(ordered):
            if _status_history_has_stage(db, lead.id, stage_name):
                definition = get_status_definition_by_name(db, stage_name)
                if definition is not None:
                    lead.status_definition_id = definition.id
                    lead.status_entered_at = _infer_funnel_history_time(db, lead, stage_name)
                break
        lead.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(lead)
    return changed


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
    transition_type: TransitionTypeLiteral | None = None,
    acting_user: User | None = None,
    commit: bool = True,
) -> dict:
    """Central entry point for pipeline status changes + history logging."""
    lead = db.query(Lead).filter(Lead.id == student_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Student not found.")

    assert_single_active_pipeline_status(lead)
    _validate_before_update(db, student_id)

    sync_lead_pipeline_status_id(db, lead)
    db.refresh(lead)

    current_status_id = resolve_effective_lead_status_id(db, lead)
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
        transition_type=transition_type,
        acting_user=acting_user,
    )
    if not transition.allowed:
        if "Unauthorized Attempt" in transition.reason:
            log_system_event(
                db,
                level="warning",
                source="status_transition",
                message=transition.reason,
                context={
                    "current_status_id": current_status_id,
                    "requested_status_id": status_id,
                    "transition_type": transition_type or transition.transition_type,
                    "changed_by_user_id": changed_by_user_id,
                },
                student_id=student_id,
                commit=commit,
            )
            if changed_by_type == "admin":
                raise HTTPException(status_code=403, detail=transition.reason)
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

    resolved_transition_type = transition.transition_type or transition_type
    if resolved_transition_type == "express" and current_status_id is not None:
        comments = build_express_transition_comment(
            db,
            from_status_id=current_status_id,
            to_status_id=status_id,
            user_comment=comments,
        )

    sanitized_comments = input_sanitizer(comments) if comments else None
    if transition.requires_override_comment and not (sanitized_comments or "").strip():
        detail = "A comment is required for this lifecycle transition."
        if resolved_transition_type == "backward":
            detail = "A comment is required when reverting to a previous pipeline stage."
        elif resolved_transition_type == "relaunch":
            detail = "A comment is required when relaunching a closed prospect."
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
                "transition_type": resolved_transition_type,
            },
            student_id=student_id,
            commit=commit,
        )
        return {"changed": False, "blocked": True, "student_id": student_id, "reason": detail}

    if transition.is_override and sanitized_comments:
        prefix_map = {
            "express": "[Express]",
            "backward": "[Revert]",
            "relaunch": "[Relaunch]",
        }
        prefix = prefix_map.get(resolved_transition_type or "", "[Override]")
        if not sanitized_comments.startswith("Express jump performed:") and not sanitized_comments.startswith(prefix):
            sanitized_comments = f"{prefix} {sanitized_comments}"
    elif transition.is_override and sanitized_comments and resolved_transition_type is None:
        if not sanitized_comments.startswith("[Override]"):
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


def _lead_new_history_exists(db: Session, student_id: int) -> bool:
    from app.models.status_definition import StatusDefinition

    return (
        db.query(StatusHistory.id)
        .join(StatusDefinition, StatusDefinition.id == StatusHistory.status_id)
        .filter(
            StatusHistory.student_id == student_id,
            StatusDefinition.stage_name == STAGE_LEAD_NEW,
        )
        .first()
        is not None
    )


def _resolve_lead_new_definition(db: Session):
    from app.models.status_definition import StatusDefinition

    row = db.query(StatusDefinition).filter(StatusDefinition.id == STATUS_LEAD_NEW).first()
    if row:
        return row
    return get_status_definition_by_name(db, STAGE_LEAD_NEW)


def _baseline_lead_new_journey_item(lead: Lead, definition) -> dict:
    baseline_time = lead.created_at or lead.status_entered_at or datetime.utcnow()
    return {
        "id": 0,
        "status_id": definition.id if definition is not None else STATUS_LEAD_NEW,
        "stage_name": definition.stage_name if definition is not None else STAGE_LEAD_NEW,
        "category": definition.category if definition is not None else "Lead",
        "description": (
            definition.description
            if definition is not None
            else "Initial inquiry received, pending first contact."
        ),
        "changed_by_type": ChangedByType.SYSTEM.value,
        "changed_by_user_id": None,
        "changed_by_label": "System",
        "comments": "Lead record created.",
        "created_at": baseline_time,
    }


def ensure_lead_new_journey_baseline(db: Session, lead: Lead, *, source: str) -> bool:
    """
    Persist Lead: New in status_history when missing.

    Does not change lead.status_definition_id when the lead has already moved forward
    in the pipeline — only backfills the first journey row for View Journey.
    """
    if _lead_new_history_exists(db, lead.id):
        if lead.status_definition_id is None:
            definition = _resolve_lead_new_definition(db)
            if definition is not None:
                lead.status_definition_id = definition.id
                lead.status_entered_at = lead.status_entered_at or lead.created_at or datetime.utcnow()
                lead.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(lead)
        return False

    definition = _resolve_lead_new_definition(db)
    if definition is None:
        log_system_event(
            db,
            level="error",
            source=AUTOMATION_SOURCE,
            message="Cannot record Lead: New — status_definitions row is missing.",
            context={"handler": source, "student_id": lead.id},
            student_id=lead.id,
            commit=True,
        )
        return False

    baseline_time = lead.created_at or datetime.utcnow()
    record_status_history(
        db,
        student_id=lead.id,
        status_id=definition.id,
        changed_by_type="system",
        comments="Lead record created.",
        created_at=baseline_time,
    )
    if lead.status_definition_id is None:
        lead.status_definition_id = definition.id
        lead.status_entered_at = baseline_time
        lead.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(lead)
    return True


def get_student_journey(db: Session, student_id: int) -> list[dict]:
    from app.models.status_definition import StatusDefinition
    from app.services.status_definitions_seed import seed_status_definitions_if_empty

    lead = db.query(Lead).filter(Lead.id == student_id).first()
    if not lead:
        return []

    seed_status_definitions_if_empty(db)
    from app.services.status_definitions_seed import ensure_status_definition_funnel_links

    ensure_status_definition_funnel_links(db)

    try:
        ensure_lead_new_journey_baseline(db, lead, source="journey view")
        sync_lead_pipeline_status_id(db, lead)
        ensure_funnel_journey_history(db, lead, source="journey view")
        db.refresh(lead)
    except Exception:
        log_system_event(
            db,
            level="error",
            source=AUTOMATION_SOURCE,
            message="Failed to persist Lead: New baseline while loading journey.",
            context={"student_id": student_id},
            student_id=student_id,
            commit=True,
        )

    rows = (
        db.query(StatusHistory, StatusDefinition, User)
        .join(StatusDefinition, StatusDefinition.id == StatusHistory.status_id)
        .outerjoin(User, User.id == StatusHistory.changed_by_user_id)
        .filter(StatusHistory.student_id == student_id)
        .order_by(StatusHistory.created_at.asc(), StatusHistory.id.asc())
        .all()
    )
    items = [
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

    if not any(item["status_id"] == STATUS_LEAD_NEW or item["stage_name"] == STAGE_LEAD_NEW for item in items):
        definition = _resolve_lead_new_definition(db)
        items.insert(0, _baseline_lead_new_journey_item(lead, definition))

    return items


def ensure_lead_new_status(db: Session, lead: Lead, *, source: str) -> bool:
    """Record Lead: New when the lead has no pipeline status yet (idempotent)."""
    return ensure_lead_new_journey_baseline(db, lead, source=source)


def on_lead_created(db: Session, lead: Lead, *, source: str) -> None:
    ensure_lead_new_journey_baseline(db, lead, source=source)


def on_whatsapp_outreach(db: Session, lead: Lead, *, source: str) -> dict:
    sync_lead_pipeline_status_id(db, lead)
    db.refresh(lead)
    outreach_status_id = resolve_status_id_by_name(
        db,
        STAGE_LEAD_OUTREACH,
        fallback=STATUS_LEAD_OUTREACH,
    )
    if outreach_status_id is None:
        logger.error("Lead %s outreach status missing from status_definitions.", lead.id)
        return {"changed": False, "blocked": True, "reason": "Lead: Outreach definition missing."}

    result = try_automated_status_transition(
        db,
        lead,
        status_id=outreach_status_id,
        source=source,
        comments=f"WhatsApp outreach triggered ({source}).",
        commit=True,
    )
    if not result.get("changed") and result.get("blocked"):
        logger.warning(
            "Lead %s outreach status not updated (%s): %s",
            lead.id,
            source,
            result.get("reason"),
        )
    return result


def on_whatsapp_inbound(db: Session, lead: Lead) -> dict:
    sync_lead_pipeline_status_id(db, lead)
    db.refresh(lead)
    engagement_status_id = resolve_status_id_by_name(
        db,
        STAGE_LEAD_ENGAGEMENT,
        fallback=STATUS_LEAD_ENGAGEMENT,
    )
    if engagement_status_id is None:
        logger.error("Lead %s engagement status missing from status_definitions.", lead.id)
        return {"changed": False, "blocked": True, "reason": "Lead: Engagement definition missing."}

    result = try_automated_status_transition(
        db,
        lead,
        status_id=engagement_status_id,
        source="whatsapp_inbound",
        comments="Student replied on WhatsApp.",
        commit=True,
    )
    if not result.get("changed") and result.get("blocked"):
        logger.warning(
            "Lead %s engagement status not updated: %s",
            lead.id,
            result.get("reason"),
        )
    return result


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
