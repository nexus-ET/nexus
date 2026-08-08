from __future__ import annotations

from datetime import datetime, timezone
from app.utils.timezone import utc_now

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.candidate_education import CandidateEducation
from app.models.lead import Lead
from app.models.students_master import StudentsMaster
from app.schemas.candidate_education import (
    CandidateEducationInput,
    CandidateEducationOut,
    CandidateEducationsResponse,
)
from app.schemas.offline_lead import OfflineLeadEducation
from app.services.education_degrees import get_education_degree_by_code, resolve_education_payload
from app.services.full_time_study_years import (
    get_full_time_study_year_by_code,
    require_full_time_study_years,
)
from app.services.gpa_cgpa_scores import apply_gpa_cgpa_fields, get_gpa_cgpa_score_by_code
from app.services.qualification_programs import get_qualification_program_by_code
from app.services.students_master_service import get_students_master_by_lead


def _education_query(db: Session, *, lead_id: int | None, booking_id: int):
    if lead_id is not None:
        return db.query(CandidateEducation).filter(CandidateEducation.lead_id == lead_id)
    return db.query(CandidateEducation).filter(CandidateEducation.booking_id == booking_id)


def _resolve_program_or_degree(db: Session, code: str | None):
    if not code:
        return None, None
    program = get_qualification_program_by_code(db, code)
    if program:
        return program, None
    return None, get_education_degree_by_code(db, code)


def _serialize_education(db: Session, record: CandidateEducation) -> CandidateEducationOut:
    degree_label = None
    level_id = None
    program, degree = _resolve_program_or_degree(db, record.degree_code)
    if program:
        degree_label = program.name
        level_id = program.level_id
    elif degree:
        degree_label = record.degree_other if degree.is_other else degree.label
        level_id = degree.level_id

    gpa_label = None
    if record.gpa_cgpa_code:
        score = get_gpa_cgpa_score_by_code(db, record.gpa_cgpa_code)
        if score:
            gpa_label = record.gpa_cgpa_other if score.is_other else score.label

    study_years_label = None
    if record.full_time_study_years:
        study_year = get_full_time_study_year_by_code(
            db,
            record.full_time_study_years,
            level_id=level_id,
        )
        if study_year:
            study_years_label = study_year.label

    return CandidateEducationOut(
        id=record.id,
        degree_code=record.degree_code,
        degree_label=degree_label,
        degree_other=record.degree_other,
        full_time_study_years=record.full_time_study_years,
        full_time_study_years_label=study_years_label,
        major=record.major,
        university_name=record.university_name,
        university_affiliation=record.university_affiliation,
        graduation_month=record.graduation_month,
        graduation_year=record.graduation_year,
        gpa_cgpa_code=record.gpa_cgpa_code,
        gpa_cgpa_label=gpa_label,
        gpa_cgpa_other=record.gpa_cgpa_other,
        sort_order=record.sort_order,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _legacy_education_from_master(db: Session, master: StudentsMaster | None) -> CandidateEducation | None:
    if master is None or not master.degree_code:
        return None

    return CandidateEducation(
        lead_id=master.lead_id,
        booking_id=master.booking_id,
        degree_code=master.degree_code,
        degree_other=master.degree_other,
        major=master.major,
        university_name=master.university,
        university_affiliation=None,
        graduation_month=None,
        graduation_year=master.graduation_year,
        gpa_cgpa_code=master.gpa_cgpa_code,
        gpa_cgpa_other=master.gpa_cgpa_other,
        sort_order=0,
    )


def _maybe_migrate_legacy_education(
    db: Session,
    *,
    lead_id: int | None,
    booking_id: int,
) -> None:
    if _education_query(db, lead_id=lead_id, booking_id=booking_id).count() > 0:
        return

    master = get_students_master_by_lead(db, lead_id) if lead_id else None
    legacy = _legacy_education_from_master(db, master)
    if legacy is None:
        return

    db.add(legacy)
    db.commit()


def _education_degree_sort_key(db: Session, record: CandidateEducation) -> tuple[int, int, int, int]:
    program, degree = _resolve_program_or_degree(db, record.degree_code)
    if program:
        sort_order = int(program.sort_order or 0)
    elif degree:
        sort_order = int(degree.sort_order or 0)
    else:
        sort_order = 999
    return (
        sort_order,
        -(record.graduation_year or 0),
        -(record.graduation_month or 0),
        record.id,
    )


def get_candidate_educations(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
) -> CandidateEducationsResponse:
    lead_id = lead.id if lead else None
    _maybe_migrate_legacy_education(db, lead_id=lead_id, booking_id=booking_id)

    records = _education_query(db, lead_id=lead_id, booking_id=booking_id).all()
    records.sort(key=lambda record: _education_degree_sort_key(db, record))
    saved_at = max((record.updated_at for record in records), default=None)

    return CandidateEducationsResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        educations=[_serialize_education(db, record) for record in records],
        saved_at=saved_at,
    )


def _get_owned_education(
    db: Session,
    *,
    education_id: int,
    lead_id: int | None,
    booking_id: int,
) -> CandidateEducation:
    record = db.query(CandidateEducation).filter(CandidateEducation.id == education_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Education record not found.")

    if lead_id is not None:
        if record.lead_id != lead_id:
            raise HTTPException(status_code=404, detail="Education record not found.")
    elif record.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Education record not found.")

    return record


def _validate_education_input(db: Session, payload: CandidateEducationInput) -> dict:
    if not payload.degree_code:
        raise HTTPException(status_code=400, detail="Current program is required.")
    if not payload.major:
        raise HTTPException(status_code=400, detail="Current major is required.")
    if not payload.university_name:
        raise HTTPException(status_code=400, detail="University name is required.")
    if payload.graduation_year is None:
        raise HTTPException(status_code=400, detail="Graduation year is required.")
    if payload.graduation_month is None:
        raise HTTPException(status_code=400, detail="Graduation month is required.")
    if not payload.gpa_cgpa_code:
        raise HTTPException(status_code=400, detail="GPA/CGPA score is required.")

    program, degree = _resolve_program_or_degree(db, payload.degree_code)
    if not program and not degree:
        raise HTTPException(status_code=400, detail="Select a valid program.")

    level_id = program.level_id if program else (degree.level_id if degree else None)
    study_year = require_full_time_study_years(
        db,
        payload.full_time_study_years,
        level_id=level_id,
    )
    study_years = study_year.code

    if program:
        edu_payload = OfflineLeadEducation(
            program_code=payload.degree_code,
            major=payload.major,
            university=payload.university_name,
            graduation_year=payload.graduation_year,
            gpa_cgpa_code=payload.gpa_cgpa_code,
            gpa_cgpa=payload.gpa_cgpa_other,
            full_time_study_years=study_years,
            level_id=level_id,
        )
    else:
        edu_payload = OfflineLeadEducation(
            degree_code=payload.degree_code,
            degree=payload.degree_other,
            major=payload.major,
            university=payload.university_name,
            graduation_year=payload.graduation_year,
            gpa_cgpa_code=payload.gpa_cgpa_code,
            gpa_cgpa=payload.gpa_cgpa_other,
            full_time_study_years=study_years,
            level_id=level_id,
        )

    resolved_edu = resolve_education_payload(db, edu_payload) or {}
    gpa_fields = apply_gpa_cgpa_fields(db, edu_payload, {})

    if degree and degree.is_other and not payload.degree_other:
        raise HTTPException(status_code=400, detail="Please enter the program.")

    gpa_score = get_gpa_cgpa_score_by_code(db, payload.gpa_cgpa_code)
    if gpa_score and gpa_score.is_other and not payload.gpa_cgpa_other:
        raise HTTPException(status_code=400, detail="Please enter the GPA/CGPA score.")

    return {
        "degree_code": resolved_edu.get("program_code") or resolved_edu.get("degree_code"),
        "degree_other": payload.degree_other if degree and degree.is_other else None,
        "full_time_study_years": study_years,
        "major": resolved_edu.get("major"),
        "university_name": (payload.university_name or "").strip() or None,
        "university_affiliation": (payload.university_affiliation or "").strip() or None,
        "graduation_month": payload.graduation_month,
        "graduation_year": resolved_edu.get("graduation_year"),
        "gpa_cgpa_code": gpa_fields.get("gpa_cgpa_code"),
        "gpa_cgpa_other": gpa_fields.get("gpa_cgpa_other"),
    }


def create_candidate_education(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: CandidateEducationInput,
) -> CandidateEducationsResponse:
    lead_id = lead.id if lead else None
    fields = _validate_education_input(db, payload)
    existing_count = _education_query(db, lead_id=lead_id, booking_id=booking_id).count()

    record = CandidateEducation(
        lead_id=lead_id,
        booking_id=booking_id,
        sort_order=existing_count,
        **fields,
    )
    db.add(record)
    db.commit()
    return get_candidate_educations(db, booking_id=booking_id, lead=lead)


def update_candidate_education(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    education_id: int,
    payload: CandidateEducationInput,
) -> CandidateEducationsResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_education(
        db,
        education_id=education_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )
    fields = _validate_education_input(db, payload)

    record.degree_code = fields["degree_code"]
    record.degree_other = fields["degree_other"]
    record.full_time_study_years = fields["full_time_study_years"]
    record.major = fields["major"]
    record.university_name = fields["university_name"]
    record.university_affiliation = fields["university_affiliation"]
    record.graduation_month = fields["graduation_month"]
    record.graduation_year = fields["graduation_year"]
    record.gpa_cgpa_code = fields["gpa_cgpa_code"]
    record.gpa_cgpa_other = fields["gpa_cgpa_other"]
    record.updated_at = utc_now()
    db.commit()
    return get_candidate_educations(db, booking_id=booking_id, lead=lead)


def delete_candidate_education(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    education_id: int,
) -> CandidateEducationsResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_education(
        db,
        education_id=education_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )
    db.delete(record)
    db.commit()
    return get_candidate_educations(db, booking_id=booking_id, lead=lead)
