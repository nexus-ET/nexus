from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.admission_history import AdmissionHistory
from app.models.candidate_task import CandidateTask
from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead
from app.models.user import User
from app.services.security_service import input_sanitizer

COMPLETED_STATUS = "COMPLETED"
SCHEDULED_STATUS = "SCHEDULED"
STALLED_STAGE_THRESHOLD_DAYS = 14
DOC_REMINDER_DAYS = 5
AWAITING_DOCS_STAGE = "AWAITING_DOCS"
COUNSELLING_STAGE = "COUNSELLING"
APPLIED_STAGE = "APPLIED"

PIPELINE_STAGES: list[dict[str, str]] = [
    {"key": "COUNSELLING", "label": "Counselling", "category": "Acquisition"},
    {"key": "AWAITING_DOCS", "label": "Awaiting Docs", "category": "Logistics"},
    {"key": "APPLIED", "label": "Applied", "category": "Closure"},
    {"key": "UNDER_REVIEW", "label": "Under Review", "category": "Closure"},
    {"key": "OFFERED", "label": "Offered", "category": "Closure"},
    {"key": "ENROLLED", "label": "Enrolled", "category": "Closure"},
    {"key": "ARCHIVED", "label": "Archived", "category": "Archive"},
]

STAGE_CATEGORY_BY_KEY = {item["key"]: item["category"] for item in PIPELINE_STAGES}
STAGE_LABEL_BY_KEY = {item["key"]: item["label"] for item in PIPELINE_STAGES}


def resolve_admission_stage_meta(stage_key: str | None) -> tuple[str | None, str | None, str | None]:
    """Return (stage_key, stage_label, category) for admission pipeline badges."""
    if not stage_key:
        return None, None, None
    normalized = stage_key.strip().upper()
    label = STAGE_LABEL_BY_KEY.get(normalized, normalized.replace("_", " ").title())
    category = STAGE_CATEGORY_BY_KEY.get(normalized, "Acquisition")
    return normalized, label, category

OUTCOME_CONFIG: dict[str, dict] = {
    "PROCEED_TO_APPLICATION": {
        "label": "Proceed to Application",
        "default_next_stage": APPLIED_STAGE,
        "action_items": [
            "Send application checklist",
            "Confirm program shortlist",
            "Schedule follow-up in 7 days",
        ],
    },
    "MISSING_DOCS": {
        "label": "Missing Documents",
        "default_next_stage": AWAITING_DOCS_STAGE,
        "action_items": [
            "Request passport copy",
            "Request academic transcripts",
            "Send document upload guide",
        ],
    },
    "NEEDS_FOLLOW_UP": {
        "label": "Needs Follow-up",
        "default_next_stage": COUNSELLING_STAGE,
        "action_items": [
            "Schedule follow-up counselling session",
            "Send summary email to candidate",
        ],
    },
    "NOT_PROCEEDING": {
        "label": "Not Proceeding",
        "default_next_stage": "ARCHIVED",
        "action_items": [
            "Send closure email",
            "Archive candidate record",
        ],
    },
    "DEFERRED_INTAKE": {
        "label": "Deferred Intake",
        "default_next_stage": COUNSELLING_STAGE,
        "action_items": [
            "Confirm deferred intake term",
            "Set reminder for next intake window",
        ],
    },
}


def get_pipeline_config() -> dict:
    outcomes = [
        {
            "key": key,
            "label": value["label"],
            "default_next_stage": value["default_next_stage"],
            "action_items": value["action_items"],
        }
        for key, value in OUTCOME_CONFIG.items()
    ]
    return {"stages": PIPELINE_STAGES, "outcomes": outcomes}


def _format_admin_name(user: User | None) -> str:
    if not user:
        return "Counsellor"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email


def move_candidate(
    db: Session,
    *,
    candidate_id: int,
    stage: str,
    counsellor_id: int | None = None,
    booking_id: int | None = None,
    outcome_key: str | None = None,
    notes: str | None = None,
) -> Lead:
    lead = db.query(Lead).filter(Lead.id == candidate_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    normalized_stage = stage.strip().upper()
    valid_stages = {item["key"] for item in PIPELINE_STAGES}
    if normalized_stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline stage: {stage}")

    previous_stage = getattr(lead, "admission_stage", None) or COUNSELLING_STAGE
    now = datetime.utcnow()

    lead.admission_stage = normalized_stage
    lead.admission_stage_entered_at = now
    lead.updated_at = now

    db.add(
        AdmissionHistory(
            lead_id=lead.id,
            booking_id=booking_id,
            counsellor_id=counsellor_id,
            from_stage=previous_stage,
            to_stage=normalized_stage,
            outcome_key=outcome_key,
            notes=notes,
        )
    )
    db.flush()
    return lead


def complete_session(
    db: Session,
    *,
    booking_id: int,
    counsellor: User,
    outcome_key: str,
    next_stage: str,
    notes: str | None,
    action_items: list[str],
) -> dict:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id)
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="Cancelled bookings cannot be completed.")
    if booking.status == COMPLETED_STATUS:
        raise HTTPException(status_code=400, detail="Booking is already completed.")
    if booking.status != SCHEDULED_STATUS:
        raise HTTPException(status_code=400, detail="Only scheduled sessions can be wrapped up.")

    normalized_outcome = outcome_key.strip().upper()
    if normalized_outcome not in OUTCOME_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid outcome_key: {outcome_key}")

    sanitized_notes = input_sanitizer(notes) if notes else None
    cleaned_items = [
        input_sanitizer(item).strip()
        for item in action_items
        if input_sanitizer(item).strip()
    ]

    now = datetime.utcnow()
    booking.status = COMPLETED_STATUS
    booking.outcome_key = normalized_outcome
    booking.wrap_up_notes = sanitized_notes
    booking.completed_at = now
    booking.updated_at = now

    lead = None
    if booking.lead_id:
        lead = move_candidate(
            db,
            candidate_id=booking.lead_id,
            stage=next_stage,
            counsellor_id=counsellor.id,
            booking_id=booking.id,
            outcome_key=normalized_outcome,
            notes=sanitized_notes,
        )

    created_tasks: list[CandidateTask] = []
    if booking.lead_id and cleaned_items:
        for item in cleaned_items:
            task = CandidateTask(
                lead_id=booking.lead_id,
                booking_id=booking.id,
                created_by_user_id=counsellor.id,
                title=item,
                status="pending",
            )
            db.add(task)
            created_tasks.append(task)

    db.commit()
    db.refresh(booking)

    return {
        "booking_id": booking.id,
        "status": booking.status,
        "outcome_key": booking.outcome_key,
        "next_stage": next_stage.strip().upper(),
        "candidate_id": booking.lead_id,
        "tasks_created": len(created_tasks),
        "completed_at": booking.completed_at,
    }


def get_pipeline_analytics(db: Session) -> dict:
    counsellor_rows = (
        db.query(
            User.id,
            User.first_name,
            User.last_name,
            User.email,
            func.count(AdmissionHistory.id).label("moved_count"),
        )
        .join(AdmissionHistory, AdmissionHistory.counsellor_id == User.id)
        .filter(AdmissionHistory.to_stage == APPLIED_STAGE)
        .group_by(User.id, User.first_name, User.last_name, User.email)
        .all()
    )

    counselling_moves = (
        db.query(func.count(AdmissionHistory.id))
        .filter(AdmissionHistory.from_stage == COUNSELLING_STAGE)
        .scalar()
        or 0
    )

    conversion_by_counsellor = []
    for row in counsellor_rows:
        counsellor_counselling = (
            db.query(func.count(AdmissionHistory.id))
            .filter(
                AdmissionHistory.counsellor_id == row.id,
                AdmissionHistory.from_stage == COUNSELLING_STAGE,
            )
            .scalar()
            or 0
        )
        applied_count = int(row.moved_count or 0)
        rate = round((applied_count / counsellor_counselling) * 100, 1) if counsellor_counselling else 0.0
        name_parts = [((row.first_name or "").strip()), ((row.last_name or "").strip())]
        counsellor_name = " ".join(part for part in name_parts if part) or row.email
        conversion_by_counsellor.append(
            {
                "counsellor_id": row.id,
                "counsellor_name": counsellor_name,
                "counselling_sessions": counsellor_counselling,
                "moved_to_applied": applied_count,
                "conversion_rate": rate,
            }
        )

    now = datetime.utcnow()
    stalled_threshold = now - timedelta(days=STALLED_STAGE_THRESHOLD_DAYS)
    stalled_candidates = (
        db.query(Lead)
        .filter(
            Lead.admission_stage == COUNSELLING_STAGE,
            Lead.admission_stage_entered_at.isnot(None),
            Lead.admission_stage_entered_at <= stalled_threshold,
        )
        .order_by(Lead.admission_stage_entered_at.asc())
        .limit(25)
        .all()
    )

    avg_days_in_stage: dict[str, float] = {}
    for stage in [COUNSELLING_STAGE, AWAITING_DOCS_STAGE, APPLIED_STAGE]:
        leads = (
            db.query(Lead)
            .filter(Lead.admission_stage == stage, Lead.admission_stage_entered_at.isnot(None))
            .all()
        )
        if not leads:
            avg_days_in_stage[stage] = 0.0
            continue
        total_days = sum((now - lead.admission_stage_entered_at).days for lead in leads)
        avg_days_in_stage[stage] = round(total_days / len(leads), 1)

    outcome_rows = (
        db.query(CounsellingBooking.outcome_key, func.count(CounsellingBooking.id))
        .filter(
            CounsellingBooking.status == COMPLETED_STATUS,
            CounsellingBooking.outcome_key.isnot(None),
        )
        .group_by(CounsellingBooking.outcome_key)
        .all()
    )
    outcome_frequency = [
        {
            "outcome_key": row[0],
            "label": OUTCOME_CONFIG.get(row[0], {}).get("label", row[0]),
            "count": int(row[1]),
        }
        for row in outcome_rows
    ]
    outcome_frequency.sort(key=lambda item: item["count"], reverse=True)

    doc_reminder_threshold = now - timedelta(days=DOC_REMINDER_DAYS)
    awaiting_docs_stalled = (
        db.query(Lead)
        .filter(
            Lead.admission_stage == AWAITING_DOCS_STAGE,
            Lead.documents_submitted_at.is_(None),
            Lead.admission_stage_entered_at.isnot(None),
            Lead.admission_stage_entered_at <= doc_reminder_threshold,
        )
        .count()
    )

    return {
        "conversion_by_counsellor": conversion_by_counsellor,
        "overall_counselling_moves": counselling_moves,
        "average_days_in_stage": avg_days_in_stage,
        "stalled_candidates": [
            {
                "lead_id": lead.id,
                "full_name": lead.full_name,
                "days_in_stage": (now - lead.admission_stage_entered_at).days
                if lead.admission_stage_entered_at
                else None,
                "admission_stage": lead.admission_stage,
            }
            for lead in stalled_candidates
        ],
        "outcome_frequency": outcome_frequency,
        "awaiting_docs_reminder_pending": awaiting_docs_stalled,
    }


def process_stalled_document_reminders(db: Session) -> int:
    """Send friendly WhatsApp reminders for candidates awaiting docs > 5 days."""
    from app.services.notification_service import NotificationService

    now = datetime.utcnow()
    threshold = now - timedelta(days=DOC_REMINDER_DAYS)
    leads = (
        db.query(Lead)
        .filter(
            Lead.admission_stage == AWAITING_DOCS_STAGE,
            Lead.documents_submitted_at.is_(None),
            Lead.admission_stage_entered_at.isnot(None),
            Lead.admission_stage_entered_at <= threshold,
            Lead.phone_number.isnot(None),
        )
        .all()
    )

    if not leads:
        return 0

    service = NotificationService(db)
    sent_count = 0
    for lead in leads:
        already_sent = (
            db.query(AdmissionHistory.id)
            .filter(
                AdmissionHistory.lead_id == lead.id,
                AdmissionHistory.outcome_key == "DOC_REMINDER_SENT",
            )
            .first()
        )
        if already_sent:
            continue

        first_name = (lead.full_name or "there").split()[0]
        message = (
            f"Hi {first_name}, friendly reminder from Edutrust Admissions — "
            "we're still waiting on your documents. Reply here if you need help uploading them."
        )
        import asyncio

        delivered = asyncio.run(
            service.send_friendly_document_reminder(
                lead_id=lead.id,
                phone_number=lead.phone_number,
                candidate_name=lead.full_name or "Candidate",
                message=message,
            )
        )
        if delivered:
            db.add(
                AdmissionHistory(
                    lead_id=lead.id,
                    counsellor_id=None,
                    from_stage=AWAITING_DOCS_STAGE,
                    to_stage=AWAITING_DOCS_STAGE,
                    outcome_key="DOC_REMINDER_SENT",
                    notes="Automated friendly document reminder sent.",
                )
            )
            sent_count += 1

    if sent_count:
        db.commit()
    return sent_count
