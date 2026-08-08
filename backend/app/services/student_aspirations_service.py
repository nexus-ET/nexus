from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.lead import Lead
from app.models.students_master import StudentsMaster
from app.models.user import User
from app.schemas.student_aspirations import (
    StudentAspirationsData,
    StudentAspirationsSaveRequest,
    TargetCountrySelection,
    migrate_legacy_aspirations_data,
)
from app.services.students_master_service import get_students_master_by_lead

def categorize_education_degrees(degrees: list) -> dict[str, list[dict[str, str]]]:
    university_college: list[dict[str, str]] = []
    pre_college: list[dict[str, str]] = []
    for degree in degrees:
        item = {"code": degree.code, "label": degree.label}
        level_id = getattr(degree, "level_id", None) or (
            getattr(degree, "level", None).id if getattr(degree, "level", None) else None
        )
        if level_id == 1:
            pre_college.append(item)
        elif not getattr(degree, "is_other", False):
            university_college.append(item)
    return {
        "university_college": university_college,
        "pre_college": pre_college,
    }


def _serialize_aspirations(record: StudentsMaster | None, *, booking_id: int | None = None) -> dict:
    if record is None:
        return {
            "students_master_id": None,
            "booking_id": booking_id,
            "aspirations": StudentAspirationsData(),
            "saved_at": None,
        }
    raw = record.aspirations_data if isinstance(record.aspirations_data, dict) else {}
    return {
        "students_master_id": record.id,
        "booking_id": booking_id,
        "aspirations": StudentAspirationsData.model_validate(migrate_legacy_aspirations_data(raw)),
        "saved_at": record.updated_at,
    }


def find_students_master_for_booking(db: Session, booking, lead: Lead | None) -> StudentsMaster | None:
    if lead:
        record = get_students_master_by_lead(db, lead.id)
        if record:
            return record

    email = (getattr(booking, "candidate_email", None) or "").strip().lower()
    if email:
        return (
            db.query(StudentsMaster)
            .filter(func.lower(StudentsMaster.email) == email)
            .order_by(StudentsMaster.updated_at.desc())
            .first()
        )
    return None


def resolve_students_master_for_booking(
    db: Session,
    booking,
    lead: Lead | None,
    *,
    updated_by_user_id: int | None = None,
) -> StudentsMaster:
    record = find_students_master_for_booking(db, booking, lead)
    if record is not None:
        if updated_by_user_id is not None:
            record.updated_by_user_id = updated_by_user_id
        if not record.booking_id:
            record.booking_id = booking.id
        return record

    candidate_name = (getattr(booking, "candidate_name", None) or "").strip()
    name_parts = candidate_name.split() if candidate_name else []
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[-1] if len(name_parts) > 1 else None

    record = StudentsMaster(
        lead_id=lead.id if lead else None,
        booking_id=booking.id,
        email=getattr(booking, "candidate_email", None),
        phone_number=getattr(booking, "candidate_phone", None),
        first_name=first_name,
        last_name=last_name,
        updated_by_user_id=updated_by_user_id,
    )
    db.add(record)
    db.flush()
    return record


def _apply_aspirations_payload(payload: StudentAspirationsSaveRequest) -> StudentAspirationsData:
    aspirations = payload.aspirations
    if not aspirations.funding_sources:
        raise HTTPException(status_code=400, detail="Primary funding source is required.")
    complete_funding = [item for item in aspirations.funding_sources if item.coverage]
    if not complete_funding:
        raise HTTPException(
            status_code=400,
            detail="Select Full, Partial, or Not Required for at least one primary funding source.",
        )
    aspirations = aspirations.model_copy(
        update={"funding_sources": complete_funding},
    )
    if not aspirations.english_tests:
        raise HTTPException(
            status_code=400,
            detail="Select at least one English language proficiency option.",
        )
    if not aspirations.aptitude_tests:
        raise HTTPException(
            status_code=400,
            detail="Select at least one aptitude test option.",
        )
    if "OTHER" in aspirations.intake_seasons and not (aspirations.intake_season_other or "").strip():
        raise HTTPException(status_code=400, detail="Please enter a value for Others intake.")
    if "OTHER" not in aspirations.intake_seasons:
        aspirations = aspirations.model_copy(update={"intake_season_other": None})
    if "OTHER" in aspirations.why_study_abroad and not (aspirations.why_study_abroad_other or "").strip():
        raise HTTPException(status_code=400, detail="Please enter a value for Others — why study abroad.")
    if "OTHER" not in aspirations.why_study_abroad:
        aspirations = aspirations.model_copy(update={"why_study_abroad_other": None})

    post_study_goals = list(aspirations.post_study_goals or [])
    if not post_study_goals and aspirations.post_study_goal:
        post_study_goals = [aspirations.post_study_goal]
    if "OTHER" in post_study_goals and not (aspirations.post_study_goal_other or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter your desired career goals for Others.",
        )
    if "OTHER" not in post_study_goals:
        aspirations = aspirations.model_copy(
            update={
                "post_study_goals": post_study_goals,
                "post_study_goal": post_study_goals[0] if post_study_goals else None,
                "post_study_goal_other": None,
            }
        )
    else:
        aspirations = aspirations.model_copy(
            update={
                "post_study_goals": post_study_goals,
                "post_study_goal": post_study_goals[0] if post_study_goals else None,
                "post_study_goal_other": (aspirations.post_study_goal_other or "").strip(),
            }
        )

    if "OTHER" in aspirations.study_countries_iso2 and not (
        aspirations.study_countries_other or ""
    ).strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter a value for Others — countries you wish to study.",
        )
    if "OTHER" not in aspirations.study_countries_iso2:
        aspirations = aspirations.model_copy(update={"study_countries_other": None})
    if "OTHER" in aspirations.programs and not (aspirations.programs_other or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter a value for Others — programs you wish to study.",
        )
    if "OTHER" not in aspirations.programs:
        aspirations = aspirations.model_copy(update={"programs_other": None})

    target_countries = list(aspirations.target_countries or [])
    if target_countries:
        synced_iso2 = [item.iso2 for item in target_countries if item.iso2]
        aspirations = aspirations.model_copy(
            update={
                "target_countries": target_countries,
                "study_countries_iso2": synced_iso2,
            }
        )
    elif aspirations.study_countries_iso2:
        aspirations = aspirations.model_copy(
            update={
                "target_countries": [
                    TargetCountrySelection(
                        iso2=iso2,
                        priority="TOP_CHOICE" if index == 0 else "ALTERNATIVE",
                    )
                    for index, iso2 in enumerate(aspirations.study_countries_iso2)
                ]
            }
        )

    return aspirations


def find_students_master_for_user(db: Session, user: User) -> StudentsMaster | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None

    lead = db.query(Lead).filter(func.lower(Lead.email) == email).first()
    record: StudentsMaster | None = None
    if lead:
        record = get_students_master_by_lead(db, lead.id)

    if record is None:
        record = (
            db.query(StudentsMaster)
            .filter(func.lower(StudentsMaster.email) == email)
            .order_by(StudentsMaster.updated_at.desc())
            .first()
        )
    return record


def resolve_students_master_for_user(db: Session, user: User) -> StudentsMaster:
    record = find_students_master_for_user(db, user)
    if record is not None:
        return record

    email = (user.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="User email is required to save aspirations.")

    lead = db.query(Lead).filter(func.lower(Lead.email) == email).first()
    record = StudentsMaster(
        lead_id=lead.id if lead else None,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone_number=user.phone_number,
    )
    db.add(record)
    db.flush()
    return record


def get_user_aspirations(db: Session, user: User) -> dict:
    record = find_students_master_for_user(db, user)
    return _serialize_aspirations(record)


def save_user_aspirations(
    db: Session,
    user: User,
    payload: StudentAspirationsSaveRequest,
) -> dict:
    aspirations = _apply_aspirations_payload(payload)
    record = resolve_students_master_for_user(db, user)
    record.aspirations_data = aspirations.model_dump(mode="json")
    flag_modified(record, "aspirations_data")
    record.updated_by_user_id = user.id
    db.commit()
    db.refresh(record)
    return _serialize_aspirations(record)


def get_booking_aspirations(db: Session, booking, lead: Lead | None) -> dict:
    record = find_students_master_for_booking(db, booking, lead)
    return _serialize_aspirations(record, booking_id=booking.id)


def save_booking_aspirations(
    db: Session,
    booking,
    lead: Lead | None,
    user_id: int,
    payload: StudentAspirationsSaveRequest,
) -> dict:
    aspirations = _apply_aspirations_payload(payload)
    record = resolve_students_master_for_booking(
        db,
        booking,
        lead,
        updated_by_user_id=user_id,
    )
    record.aspirations_data = aspirations.model_dump(mode="json")
    flag_modified(record, "aspirations_data")
    db.commit()
    db.refresh(record)
    return _serialize_aspirations(record, booking_id=booking.id)
