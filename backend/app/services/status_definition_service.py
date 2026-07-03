from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead
from app.models.status_definition import StatusDefinition
from app.models.status_history import StatusHistory
from app.models.user import User

# Canonical stage IDs (status_definitions v2)
STATUS_LEAD_NEW = 1
STATUS_LEAD_OUTREACH = 2
STATUS_LEAD_ENGAGEMENT = 3
STATUS_LEAD_SESSION_BOOKED = 4
STATUS_LEAD_SESSION_RESCHEDULED = 5
STATUS_LEAD_SESSION_CANCELLED = 6
STATUS_LEAD_CANCELLED_NO_ANSWER = 7
STATUS_LEAD_CANCELLED_NOT_INTERESTED = 8
STATUS_LEAD_DEFERRED = 9
STATUS_COUNSELLING_SCHEDULED = 10
STATUS_COUNSELLING_FINISHED = 11
STATUS_PROSPECT_ENROLLED = 37
STATUS_PROSPECT_CANCELLED = 38
STATUS_PROSPECT_RELAUNCH = 39

STAGE_LEAD_OUTREACH = "Lead: Outreach"
STAGE_LEAD_NEW = "Lead: New"
STAGE_COUNSELLING_SCHEDULED = "Counselling: Scheduled"
STAGE_COUNSELLING_FINISHED = "Counselling: Finished"
STAGE_LEAD_SESSION_BOOKED = "Lead: Session Booked"

TERMINAL_STATUS_IDS = frozenset({7, 8, 9, 14, 15, 22, 29, 37, 38, 39})

LEGACY_ADMISSION_STAGE_MAP: dict[str, int] = {
    "COUNSELLING": STATUS_COUNSELLING_SCHEDULED,
    "AWAITING_DOCS": 16,
    "APPLIED": 18,
    "UNDER_REVIEW": 19,
    "OFFERED": 21,
    "ENROLLED": STATUS_PROSPECT_ENROLLED,
    "ARCHIVED": STATUS_PROSPECT_CANCELLED,
}


def serialize_status_definition(row: StatusDefinition) -> dict:
    return {
        "id": row.id,
        "stage_name": row.stage_name,
        "category": row.category,
        "description": row.description,
        "next_stage_id": row.next_stage_id,
        "is_terminal": row.next_stage_id is None,
    }


def list_status_definitions(db: Session) -> list[dict]:
    from app.services.status_definitions_seed import seed_status_definitions_if_empty

    seed_status_definitions_if_empty(db)
    rows = db.query(StatusDefinition).order_by(StatusDefinition.id.asc()).all()
    return [serialize_status_definition(row) for row in rows]


def get_status_definition(db: Session, status_definition_id: int) -> StatusDefinition:
    row = db.query(StatusDefinition).filter(StatusDefinition.id == status_definition_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Status definition not found.")
    return row


def get_status_definition_by_name(db: Session, stage_name: str) -> StatusDefinition | None:
    return (
        db.query(StatusDefinition)
        .filter(StatusDefinition.stage_name == stage_name)
        .first()
    )


def resolve_lead_status_meta(
    db: Session,
    lead: Lead | None,
    *,
    booking_status: str | None = None,
) -> tuple[int | None, str | None, str | None]:
    if lead and lead.status_definition_id:
        row = db.query(StatusDefinition).filter(StatusDefinition.id == lead.status_definition_id).first()
        if row:
            return row.id, row.stage_name, row.category

    if lead and lead.admission_stage:
        mapped_id = LEGACY_ADMISSION_STAGE_MAP.get((lead.admission_stage or "").strip().upper())
        if mapped_id:
            row = db.query(StatusDefinition).filter(StatusDefinition.id == mapped_id).first()
            if row:
                return row.id, row.stage_name, row.category

    normalized_booking = (booking_status or "").strip().upper()
    if normalized_booking == "COMPLETED":
        row = get_status_definition_by_name(db, STAGE_COUNSELLING_FINISHED)
        if row:
            return row.id, row.stage_name, row.category
    if normalized_booking == "SCHEDULED":
        row = get_status_definition_by_name(db, STAGE_COUNSELLING_SCHEDULED)
        if row:
            return row.id, row.stage_name, row.category

    row = db.query(StatusDefinition).filter(StatusDefinition.id == STATUS_LEAD_NEW).first()
    if row:
        return row.id, row.stage_name, row.category
    return None, None, None


def get_lead_status_history(db: Session, lead_id: int) -> list[dict]:
    from app.models.status_history import ChangedByType
    from app.services.student_status_service import _format_user_name

    rows = (
        db.query(StatusHistory, StatusDefinition, User)
        .join(StatusDefinition, StatusDefinition.id == StatusHistory.status_id)
        .outerjoin(User, User.id == StatusHistory.changed_by_user_id)
        .filter(StatusHistory.student_id == lead_id)
        .order_by(StatusHistory.created_at.asc(), StatusHistory.id.asc())
        .all()
    )
    return [
        {
            "id": history.id,
            "status_definition_id": definition.id,
            "status_id": definition.id,
            "stage_name": definition.stage_name,
            "category": definition.category,
            "entered_at": history.created_at,
            "notes": history.comments,
            "comments": history.comments,
            "changed_by_type": (
                history.changed_by_type.value
                if hasattr(history.changed_by_type, "value")
                else str(history.changed_by_type)
            ),
            "changed_by_user_id": history.changed_by_user_id,
            "changed_by_label": (
                _format_user_name(user)
                if (
                    history.changed_by_type.value
                    if hasattr(history.changed_by_type, "value")
                    else str(history.changed_by_type)
                )
                == "admin"
                else "System"
            ),
        }
        for history, definition, user in rows
    ]


def record_lead_status_history(
    db: Session,
    *,
    lead_id: int,
    status_definition_id: int,
    counsellor_id: int | None = None,
    booking_id: int | None = None,
    notes: str | None = None,
    created_at: datetime | None = None,
) -> StatusHistory:
    from app.services.student_status_service import record_status_history

    return record_status_history(
        db,
        student_id=lead_id,
        status_id=status_definition_id,
        changed_by_type="admin" if counsellor_id else "system",
        changed_by_user_id=counsellor_id,
        comments=notes,
        booking_id=booking_id,
        created_at=created_at,
    )


def apply_lead_status(
    db: Session,
    *,
    lead: Lead,
    status_definition_id: int,
    counsellor_id: int | None = None,
    booking_id: int | None = None,
    notes: str | None = None,
    booking: CounsellingBooking | None = None,
) -> dict:
    from app.services.student_status_service import update_student_status

    result = update_student_status(
        db,
        student_id=lead.id,
        status_id=status_definition_id,
        changed_by_type="admin",
        changed_by_user_id=counsellor_id,
        comments=notes,
        booking_id=booking_id,
        booking=booking,
        skip_if_unchanged=True,
        allow_override=True,
        commit=True,
    )
    return {
        "lead_id": result["student_id"],
        "previous_status_definition_id": result.get("previous_status_id"),
        "status_definition_id": result["status_id"],
        "stage_name": result["stage_name"],
        "history_id": result["history_id"],
        "trigger_outreach": result.get("trigger_outreach", False),
        "booking_id": result.get("booking_id"),
        "booking_status": result.get("booking_status"),
    }
