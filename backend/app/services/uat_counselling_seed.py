"""Ensure UAT lead has an assigned counselling booking and profile data for Playwright."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead
from app.models.students_master import StudentsMaster
from app.models.user import User
from app.services.counselling_service import (
    SCHEDULED_STATUS,
    assign_booking,
    create_staff_booking,
)
from app.utils.timezone import office_now

DEFAULT_LEAD_ID = 27
DEFAULT_ADMIN_EMAIL = "ishq@edutrust.in"

DEFAULT_ASPIRATIONS: dict[str, Any] = {
    "study_countries_iso2": ["CA", "US"],
    "country_priorities": [
        {"iso2": "CA", "priority": "TOP_CHOICE"},
        {"iso2": "US", "priority": "ALTERNATIVE"},
    ],
    "programs": ["COMPUTER_SCIENCE"],
    "discipline_university_college": ["ENGINEERING"],
    "institution_type": ["ANY"],
    "global_ranking": ["TOP_500_BROAD_ACADEMIC"],
    "budget": "MID_RANGE",
    "intake_years": [2026, 2027],
    "intake_seasons": ["JUL_AUG_SEP_OCT_AUTUMN"],
    "english_tests": ["IELTS"],
    "aptitude_tests": ["NOT_REQUIRED_TEST_OPTIONAL"],
}


def _resolve_admin(db: Session, admin_email: str) -> User:
    admin = db.query(User).filter(User.email == admin_email).first()
    if not admin:
        raise ValueError(f"Admin user {admin_email!r} not found")
    return admin


def _candidate_name(db: Session, lead: Lead, master: StudentsMaster | None) -> str:
    if master and (master.first_name or master.last_name):
        parts = [master.first_name or "", master.last_name or ""]
        return " ".join(p for p in parts if p).strip()
    return (lead.full_name or "UAT Student").strip() or "UAT Student"


def _ensure_students_master(
    db: Session,
    *,
    lead: Lead,
    booking: CounsellingBooking,
) -> StudentsMaster:
    master = db.query(StudentsMaster).filter(StudentsMaster.lead_id == lead.id).first()
    if not master:
        master = StudentsMaster(lead_id=lead.id)
        db.add(master)
        db.flush()

    if not master.first_name:
        master.first_name = "Ishan"
    if not master.last_name:
        master.last_name = "Ahmed"
    if not master.email:
        master.email = lead.email
    master.booking_id = booking.id
    if not isinstance(master.aspirations_data, dict) or not master.aspirations_data.get(
        "study_countries_iso2"
    ):
        master.aspirations_data = dict(DEFAULT_ASPIRATIONS)
    db.flush()
    return master


def _pick_future_slot(db: Session, admin_id: int) -> datetime:
    from app.services.counselling_service import _iter_day_slot_times, _normalize_time

    now = office_now(db)
    for day_offset in range(1, 30):
        day = (now + timedelta(days=day_offset)).date()
        slots = list(_iter_day_slot_times(db, day))
        for slot in slots:
            normalized = _normalize_time(slot)
            if normalized <= now:
                continue
            conflict = (
                db.query(CounsellingBooking.id)
                .filter(
                    CounsellingBooking.admin_id == admin_id,
                    CounsellingBooking.status == SCHEDULED_STATUS,
                    CounsellingBooking.scheduled_time == normalized,
                )
                .first()
            )
            if conflict:
                continue
            return normalized
    raise ValueError("No available counselling slot found in the next 30 days")


def ensure_uat_counselling_booking(
    db: Session,
    *,
    lead_id: int = DEFAULT_LEAD_ID,
    admin_email: str = DEFAULT_ADMIN_EMAIL,
) -> dict[str, Any]:
    """Assign or create a SCHEDULED counselling booking visible to the UAT admin."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise ValueError(f"Lead {lead_id} not found")

    admin = _resolve_admin(db, admin_email)
    master = db.query(StudentsMaster).filter(StudentsMaster.lead_id == lead_id).first()
    candidate_name = _candidate_name(db, lead, master)

    pending = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead_id,
            CounsellingBooking.admin_id.is_(None),
        )
        .order_by(CounsellingBooking.id.desc())
        .first()
    )
    if pending is not None:
        booking = assign_booking(db, pending.id, admin.id)
        action = "assigned_pending"
    else:
        assigned = (
            db.query(CounsellingBooking)
            .filter(
                CounsellingBooking.lead_id == lead_id,
                CounsellingBooking.admin_id == admin.id,
                CounsellingBooking.status == SCHEDULED_STATUS,
            )
            .order_by(CounsellingBooking.scheduled_time.desc(), CounsellingBooking.id.desc())
            .first()
        )
        if assigned is not None:
            booking = assigned
            action = "reused_scheduled"
        else:
            slot = _pick_future_slot(db, admin.id)
            booking = create_staff_booking(
                db,
                scheduled_time=slot,
                admin_id=admin.id,
                candidate_name=candidate_name,
                candidate_email=lead.email,
                candidate_phone=lead.phone_number,
                lead_id=lead.id,
                session_purpose="General Counselling",
                notes="Purpose: General Counselling",
            )
            action = "created_scheduled"

    master = _ensure_students_master(db, lead=lead, booking=booking)
    db.commit()
    db.refresh(booking)

    return {
        "action": action,
        "lead_id": lead_id,
        "booking_id": booking.id,
        "booking_status": booking.status,
        "admin_id": booking.admin_id,
        "admin_email": admin.email,
        "scheduled_time": booking.scheduled_time.isoformat() if booking.scheduled_time else None,
        "students_master_id": master.id,
        "candidate_name": booking.candidate_name,
    }
