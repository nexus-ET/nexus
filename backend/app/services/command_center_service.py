from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.candidate_task import CandidateTask
from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead
from app.models.security_audit_run import SecurityAuditRun
from app.models.team_chat_message import TeamChatMessage
from app.models.user import User
from app.utils.timezone import utc_now
from app.services.pipeline_service import (
    AWAITING_DOCS_STAGE,
    COUNSELLING_STAGE,
    PIPELINE_STAGES,
    STALLED_STAGE_THRESHOLD_DAYS,
    get_pipeline_analytics,
    move_candidate,
)


def get_operational_pulse(db: Session) -> dict:
    analytics = get_pipeline_analytics(db)
    pending_review = (
        db.query(Lead)
        .filter(Lead.admission_stage.in_([COUNSELLING_STAGE, AWAITING_DOCS_STAGE]))
        .count()
    )
    open_tasks = db.query(CandidateTask).filter(CandidateTask.status == "pending").count()
    scheduled_sessions = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.status == "SCHEDULED")
        .count()
    )
    latest_audit = (
        db.query(SecurityAuditRun)
        .order_by(SecurityAuditRun.started_at.desc(), SecurityAuditRun.id.desc())
        .first()
    )
    return {
        "pending_review": pending_review,
        "stalled_candidates": len(analytics["stalled_candidates"]),
        "open_tasks": open_tasks,
        "scheduled_sessions": scheduled_sessions,
        "awaiting_docs_reminders": analytics["awaiting_docs_reminder_pending"],
        "security_status": latest_audit.status if latest_audit else "unknown",
        "security_healthy": latest_audit is None or latest_audit.status == "pass",
        "security_run_id": latest_audit.id if latest_audit else None,
        "security_checked_at": latest_audit.completed_at if latest_audit else None,
    }


def get_pipeline_board(db: Session, admin_id: int | None = None) -> dict:
    query = db.query(Lead).order_by(Lead.updated_at.desc())
    if admin_id is not None:
        query = query.filter(Lead.assigned_advisor_id == admin_id)
    leads = query.limit(200).all()
    lead_ids = [lead.id for lead in leads]
    booking_by_lead: dict[int, int] = {}
    if lead_ids:
        scheduled_bookings = (
            db.query(CounsellingBooking)
            .filter(
                CounsellingBooking.lead_id.in_(lead_ids),
                CounsellingBooking.status == "SCHEDULED",
            )
            .order_by(CounsellingBooking.scheduled_time.desc())
            .all()
        )
        for booking in scheduled_bookings:
            if booking.lead_id is not None and booking.lead_id not in booking_by_lead:
                booking_by_lead[booking.lead_id] = booking.id

    columns: dict[str, list[dict]] = {stage["key"]: [] for stage in PIPELINE_STAGES}
    now = utc_now()
    stalled_threshold = now - timedelta(days=STALLED_STAGE_THRESHOLD_DAYS)

    for lead in leads:
        stage = lead.admission_stage or COUNSELLING_STAGE
        if stage not in columns:
            stage = COUNSELLING_STAGE
        is_stalled = (
            stage == COUNSELLING_STAGE
            and lead.admission_stage_entered_at is not None
            and lead.admission_stage_entered_at <= stalled_threshold
        )
        columns[stage].append(
            {
                "lead_id": lead.id,
                "full_name": lead.full_name,
                "email": lead.email,
                "phone_number": lead.phone_number,
                "admission_stage": stage,
                "assigned_advisor_id": lead.assigned_advisor_id,
                "is_stalled": is_stalled,
                "latest_booking_id": booking_by_lead.get(lead.id),
                "updated_at": lead.updated_at,
            }
        )

    return {"stages": PIPELINE_STAGES, "columns": columns}


def list_open_tasks(db: Session, limit: int = 50) -> list[dict]:
    rows = (
        db.query(CandidateTask, Lead)
        .join(Lead, Lead.id == CandidateTask.lead_id)
        .filter(CandidateTask.status == "pending")
        .order_by(CandidateTask.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": task.id,
            "lead_id": task.lead_id,
            "booking_id": task.booking_id,
            "title": task.title,
            "status": task.status,
            "candidate_name": lead.full_name,
            "created_at": task.created_at,
        }
        for task, lead in rows
    ]


def assign_lead_to_admin(db: Session, *, lead_id: int, admin_id: int) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    lead.assigned_advisor_id = admin_id
    if not lead.admission_stage:
        lead.admission_stage = COUNSELLING_STAGE
        lead.admission_stage_entered_at = utc_now()
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)
    return lead


def move_pipeline_candidate(
    db: Session,
    *,
    lead_id: int,
    stage: str,
    counsellor_id: int,
) -> Lead:
    return move_candidate(
        db,
        candidate_id=lead_id,
        stage=stage,
        counsellor_id=counsellor_id,
    )


def serialize_team_message(row: TeamChatMessage, sender: User | None = None) -> dict:
    name = ""
    if sender:
        first = (sender.first_name or "").strip()
        last = (sender.last_name or "").strip()
        name = f"{first} {last}".strip() or sender.email
    return {
        "id": row.id,
        "sender_user_id": row.sender_user_id,
        "sender_name": name,
        "text": row.text,
        "lead_id": row.lead_id,
        "media_url": row.media_url,
        "file_name": row.file_name,
        "message_type": row.message_type,
        "delivery_status": row.delivery_status,
        "read_at": row.read_at,
        "created_at": row.created_at,
    }


def list_team_messages(db: Session, limit: int = 100) -> list[dict]:
    rows = (
        db.query(TeamChatMessage, User)
        .join(User, User.id == TeamChatMessage.sender_user_id)
        .order_by(TeamChatMessage.created_at.desc(), TeamChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [serialize_team_message(message, sender) for message, sender in reversed(rows)]


def create_team_message(
    db: Session,
    *,
    sender_user_id: int,
    text: str,
    lead_id: int | None = None,
    message_type: str = "text",
    media_url: str | None = None,
    file_name: str | None = None,
) -> dict:
    message = TeamChatMessage(
        sender_user_id=sender_user_id,
        text=text.strip(),
        lead_id=lead_id,
        message_type=message_type,
        media_url=media_url,
        file_name=file_name,
        delivery_status="sent",
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    sender = db.query(User).filter(User.id == sender_user_id).first()
    payload = serialize_team_message(message, sender)
    message.delivery_status = "delivered"
    db.commit()
    payload["delivery_status"] = "delivered"
    return payload


def mark_messages_read(db: Session, *, reader_user_id: int, up_to_message_id: int) -> int:
    rows = (
        db.query(TeamChatMessage)
        .filter(
            TeamChatMessage.id <= up_to_message_id,
            TeamChatMessage.sender_user_id != reader_user_id,
            TeamChatMessage.read_at.is_(None),
        )
        .all()
    )
    now = utc_now()
    for row in rows:
        row.read_at = now
        row.delivery_status = "read"
    if rows:
        db.commit()
    return len(rows)
