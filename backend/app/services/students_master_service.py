from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.students_master import StudentsMaster
from app.schemas.offline_lead import OfflineLeadEducation
from app.schemas.students_master import StudentMasterSaveRequest
from app.services.countries import get_country_by_iso2
from app.services.education_degrees import resolve_education_payload
from app.services.gpa_cgpa_scores import apply_gpa_cgpa_fields


def _normalize_iso2(value: str | None) -> str | None:
    token = (value or "").strip().upper()
    return token or None


def _normalize_phone_local(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits or None


def _format_phone(db: Session, iso2: str | None, local: str | None) -> str | None:
    normalized_iso2 = _normalize_iso2(iso2)
    normalized_local = _normalize_phone_local(local)
    if not normalized_local:
        return None
    if not normalized_iso2:
        return normalized_local
    country = get_country_by_iso2(db, normalized_iso2)
    if not country:
        raise HTTPException(status_code=400, detail="Select a valid phone country code.")
    return f"+{country.dial_code}{normalized_local}"


def _require_text(value: str | None, label: str) -> None:
    if not (value or "").strip():
        raise HTTPException(status_code=400, detail=f"{label} is required.")


def _require_max_length(value: str | None, label: str, max_length: int) -> None:
    if value is not None and len(value) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be {max_length} characters or fewer.",
        )


_PROFILE_NAME_MAX = 50
_PROFILE_EMAIL_MAX = 50
_PROFILE_ADDRESS_MAX = 50
_PROFILE_CITY_STATE_MAX = 50
_PROFILE_ZIPCODE_MAX = 7


def _validate_students_master_payload(
    db: Session,
    payload: StudentMasterSaveRequest,
) -> None:
    scope = payload.save_scope

    if scope in {"profile", "full"}:
        _require_text(payload.first_name, "First name")
        _require_text(payload.last_name, "Last name")
        if not payload.date_of_birth:
            raise HTTPException(status_code=400, detail="Date of birth is required.")
        if payload.gender not in {"MALE", "FEMALE"}:
            raise HTTPException(status_code=400, detail="Gender is required.")
        if payload.marital_status not in {"SINGLE", "MARRIED"}:
            raise HTTPException(status_code=400, detail="Status is required.")
        _require_text(payload.email, "Email")
        _require_text(payload.phone_country_iso2, "Primary phone country code")

        phone_local = _normalize_phone_local(payload.phone_local)
        if not phone_local or len(phone_local) != 10:
            raise HTTPException(
                status_code=400,
                detail="Primary phone number must be exactly 10 digits.",
            )

        loc = payload.location
        _require_text(loc.address1, "Address 1")
        _require_text(loc.address2, "Address 2")
        _require_text(loc.city, "City")
        _require_text(loc.state, "State")
        _require_text(loc.country_iso2, "Country")
        _require_text(loc.zipcode, "Zipcode")

        _require_max_length(payload.first_name, "First name", _PROFILE_NAME_MAX)
        _require_max_length(payload.middle_name, "Middle name", _PROFILE_NAME_MAX)
        _require_max_length(payload.last_name, "Last name", _PROFILE_NAME_MAX)
        _require_max_length(payload.email, "Email", _PROFILE_EMAIL_MAX)
        _require_max_length(loc.address1, "Address 1", _PROFILE_ADDRESS_MAX)
        _require_max_length(loc.address2, "Address 2", _PROFILE_ADDRESS_MAX)
        _require_max_length(loc.address3, "Address 3", _PROFILE_ADDRESS_MAX)
        _require_max_length(loc.city, "City", _PROFILE_CITY_STATE_MAX)
        _require_max_length(loc.state, "State", _PROFILE_CITY_STATE_MAX)
        _require_max_length(loc.zipcode, "Zipcode", _PROFILE_ZIPCODE_MAX)

    if scope in {"academia", "full"}:
        edu = payload.education
        _require_text(edu.degree_code, "Current degree")
        _require_text(edu.major, "Current major")
        _require_text(edu.university, "University name")
        if edu.graduation_year is None:
            raise HTTPException(status_code=400, detail="Graduation year is required.")
        _require_text(edu.gpa_cgpa_code, "GPA/CGPA score")


def get_students_master_by_lead(db: Session, lead_id: int | None) -> StudentsMaster | None:
    if not lead_id:
        return None
    return db.query(StudentsMaster).filter(StudentsMaster.lead_id == lead_id).first()


def students_master_to_profile_dict(db: Session, record: StudentsMaster) -> dict[str, Any]:
    location_country = None
    if record.country_iso2:
        country = get_country_by_iso2(db, record.country_iso2)
        location_country = country.name if country else record.country_iso2

    target_destination = None
    if record.target_destination_iso2:
        country = get_country_by_iso2(db, record.target_destination_iso2)
        target_destination = country.name if country else record.target_destination_iso2

    degree_label = None
    gpa_label = None
    if record.degree_code:
        from app.services.education_degrees import get_education_degree_by_code

        degree = get_education_degree_by_code(db, record.degree_code)
        if degree:
            degree_label = record.degree_other if degree.is_other else degree.label
    if record.gpa_cgpa_code:
        from app.services.gpa_cgpa_scores import get_gpa_cgpa_score_by_code

        score = get_gpa_cgpa_score_by_code(db, record.gpa_cgpa_code)
        if score:
            gpa_label = record.gpa_cgpa_other if score.is_other else score.label

    target_program = None
    target_course = None
    if record.target_program_code:
        from app.services.target_programs import get_target_program_by_code

        program = get_target_program_by_code(db, record.target_program_code)
        target_program = program.label if program else record.target_program_code
    if record.target_course_code:
        from app.services.target_programs import get_target_course_by_code

        course = get_target_course_by_code(db, record.target_course_code)
        target_course = course.label if course else record.target_course_code

    return {
        "lead_id": record.lead_id,
        "first_name": record.first_name,
        "middle_name": record.middle_name,
        "last_name": record.last_name,
        "date_of_birth": record.date_of_birth.isoformat() if record.date_of_birth else None,
        "gender": record.gender,
        "marital_status": record.marital_status,
        "email": record.email,
        "phone_country_iso2": record.phone_country_iso2,
        "phone_local": record.phone_local,
        "phone_number": record.phone_number,
        "phone_country_iso2_secondary": record.phone_country_iso2_secondary,
        "phone_local_secondary": record.phone_local_secondary,
        "phone_number_secondary": record.phone_number_secondary,
        "location": {
            "address1": record.address1,
            "address2": record.address2,
            "address3": record.address3,
            "city": record.city,
            "state": record.state,
            "country_iso2": record.country_iso2,
            "country": location_country,
            "zipcode": record.zipcode,
        },
        "education": {
            "degree_code": record.degree_code,
            "degree": degree_label,
            "degree_other": record.degree_other,
            "major": record.major,
            "university": record.university,
            "graduation_year": record.graduation_year,
            "gpa_cgpa_code": record.gpa_cgpa_code,
            "gpa_cgpa": gpa_label,
            "gpa_cgpa_other": record.gpa_cgpa_other,
        },
        "study_interest": {
            "target_destination_iso2": record.target_destination_iso2,
            "target_destination": target_destination,
            "target_program_code": record.target_program_code,
            "target_program": target_program,
            "target_course_code": record.target_course_code,
            "target_course": target_course,
        },
        "aptitude_scores": {
            "english_test_scores": record.english_test_scores,
            "gre_score": record.gre_score,
            "gmat_score": record.gmat_score,
        },
        "students_master_id": record.id,
        "saved_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def merge_profile_with_students_master(
    db: Session,
    profile: dict[str, Any],
    record: StudentsMaster | None,
) -> dict[str, Any]:
    if not record:
        return profile
    saved = students_master_to_profile_dict(db, record)
    merged = {
        **profile,
        **{
            k: v
            for k, v in saved.items()
            if k not in {"location", "education", "study_interest", "aptitude_scores"}
        },
    }
    merged["location"] = {**profile.get("location", {}), **saved.get("location", {})}
    merged["education"] = {**profile.get("education", {}), **saved.get("education", {})}
    merged["study_interest"] = {**profile.get("study_interest", {}), **saved.get("study_interest", {})}
    merged["aptitude_scores"] = {**profile.get("aptitude_scores", {}), **saved.get("aptitude_scores", {})}
    merged["students_master_id"] = saved.get("students_master_id")
    merged["saved_at"] = saved.get("saved_at")
    return merged


def upsert_students_master(
    db: Session,
    *,
    lead: Lead | None,
    booking_id: int,
    user_id: int,
    payload: StudentMasterSaveRequest,
) -> StudentsMaster:
    _validate_students_master_payload(db, payload)

    lead_id = lead.id if lead else None
    record = get_students_master_by_lead(db, lead_id) if lead_id else None
    if record is None:
        record = StudentsMaster(lead_id=lead_id)
        db.add(record)

    record.booking_id = booking_id
    record.updated_by_user_id = user_id
    record.lead_id = lead_id

    scope = payload.save_scope

    if scope in {"profile", "full"}:
        record.first_name = (payload.first_name or "").strip() or None
        record.middle_name = (payload.middle_name or "").strip() or None
        record.last_name = (payload.last_name or "").strip() or None
        record.date_of_birth = payload.date_of_birth
        record.gender = payload.gender
        record.marital_status = payload.marital_status
        record.email = (payload.email or "").strip() or None

        record.phone_country_iso2 = _normalize_iso2(payload.phone_country_iso2)
        record.phone_local = _normalize_phone_local(payload.phone_local)
        record.phone_number = _format_phone(db, record.phone_country_iso2, record.phone_local)
        record.phone_country_iso2_secondary = _normalize_iso2(payload.phone_country_iso2_secondary)
        record.phone_local_secondary = _normalize_phone_local(payload.phone_local_secondary)
        record.phone_number_secondary = _format_phone(
            db,
            record.phone_country_iso2_secondary,
            record.phone_local_secondary,
        )

        loc = payload.location
        record.address1 = (loc.address1 or "").strip() or None
        record.address2 = (loc.address2 or "").strip() or None
        record.address3 = (loc.address3 or "").strip() or None
        record.city = (loc.city or "").strip() or None
        record.state = (loc.state or "").strip() or None
        record.country_iso2 = _normalize_iso2(loc.country_iso2)
        record.zipcode = (loc.zipcode or "").strip() or None
        if record.country_iso2 and not get_country_by_iso2(db, record.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")

    if scope in {"academia", "full"}:
        edu_payload = OfflineLeadEducation(
            degree_code=payload.education.degree_code,
            degree_other=payload.education.degree_other,
            major=payload.education.major,
            university=payload.education.university,
            graduation_year=payload.education.graduation_year,
            gpa_cgpa_code=payload.education.gpa_cgpa_code,
            gpa_cgpa=payload.education.gpa_cgpa_other,
            gpa_cgpa_other=payload.education.gpa_cgpa_other,
        )
        resolved_edu = resolve_education_payload(db, edu_payload) or {}
        record.degree_code = resolved_edu.get("degree_code")
        record.degree_other = resolved_edu.get("degree_other")
        record.major = resolved_edu.get("major")
        record.university = resolved_edu.get("university")
        record.graduation_year = resolved_edu.get("graduation_year")
        gpa_fields = apply_gpa_cgpa_fields(db, edu_payload, {})
        record.gpa_cgpa_code = gpa_fields.get("gpa_cgpa_code")
        record.gpa_cgpa_other = gpa_fields.get("gpa_cgpa_other")

    db.commit()
    db.refresh(record)
    return record
