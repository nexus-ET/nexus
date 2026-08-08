from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.education_degree import EducationDegree
from app.schemas.offline_lead import OfflineLeadEducation
from app.services.levels import get_level
from app.services.full_time_study_years import require_full_time_study_years
from app.services.gpa_cgpa_scores import apply_gpa_cgpa_fields
from app.services.qualification_programs import require_qualification_program

LEVEL_CODE_TO_ID = {
    "ENTRY": 1,
    "FOUNDATIONAL": 1,
    "UNDERGRAD": 2,
    "GRADUATE": 3,
    "DOCTORAL": 4,
    "CERT": 4,
}

DEFAULT_EDUCATION_DEGREES: list[dict[str, str | int | bool]] = [
    {"code": "SECONDARY_SCHOOL", "label": "Secondary (Grade 9–10)", "sort_order": 1, "course_level": "ENTRY"},
    {"code": "SENIOR_SECONDARY", "label": "Senior Secondary (Grade 11–12)", "sort_order": 2, "course_level": "UNDERGRAD"},
    {"code": "HIGH_SCHOOL_DIPLOMA_GED", "label": "High School Diploma / GED", "sort_order": 3, "course_level": "UNDERGRAD"},
    {"code": "SOME_COLLEGE_NO_DEGREE", "label": "Some College (No Degree)", "sort_order": 4, "course_level": "GRADUATE"},
    {"code": "ASSOCIATE_DEGREE", "label": "Associate Degree (AA/AS)", "sort_order": 5, "course_level": "DOCTORAL"},
    {
        "code": "BACHELORS_3Y_INTERNATIONAL",
        "label": "Bachelor's (3-Year International)",
        "sort_order": 6,
        "course_level": "UNDERGRAD",
    },
    {
        "code": "BACHELORS_4Y_INTERNATIONAL",
        "label": "Bachelor's (4-Year International)",
        "sort_order": 7,
        "course_level": "UNDERGRAD",
    },
    {"code": "BACHELORS_DEGREE", "label": "Bachelor's Degree (BA/BS/B.Tech)", "sort_order": 8, "course_level": "UNDERGRAD"},
    {"code": "INTEGRATED_MASTERS", "label": "Integrated Master's", "sort_order": 9, "course_level": "GRADUATE"},
    {"code": "MASTERS_DEGREE", "label": "Master's Degree (MA/MS/MBA/M.Tech)", "sort_order": 10, "course_level": "GRADUATE"},
    {"code": "POST_GRADUATE_DIPLOMA", "label": "Post-Graduate Diploma (PGD)", "sort_order": 11, "course_level": "UNDERGRAD"},
    {"code": "PROFESSIONAL_DEGREE", "label": "Professional Degree (JD/MD)", "sort_order": 12, "course_level": "CERT"},
    {"code": "DOCTORATE", "label": "Doctorate (PhD/EdD)", "sort_order": 13, "course_level": "CERT"},
    {"code": "STEM_DESIGNATED", "label": "STEM-Designated Degree", "sort_order": 14, "course_level": "ENTRY"},
    {"code": "BOOTCAMP_GRADUATE", "label": "Bootcamp Graduate", "sort_order": 15, "course_level": "ENTRY"},
    {
        "code": "PROFESSIONAL_CERTIFICATION_ONLY",
        "label": "Professional Certification Only",
        "sort_order": 16,
        "course_level": "ENTRY",
    },
    {"code": "OTHER", "label": "Other", "sort_order": 99, "is_other": True, "course_level": "ENTRY"},
]


def _resolve_level_id(db: Session, level_code: str) -> int:
    level_id = LEVEL_CODE_TO_ID.get((level_code or "").strip().upper())
    if level_id is None or not get_level(db, level_id):
        raise RuntimeError(f"Level '{level_code}' is not seeded.")
    return level_id


def seed_education_degrees(db: Session) -> None:
    """Disabled — education degrees are managed via Admin UI / migrations, not startup seeds."""
    return


def list_active_education_degrees(
    db: Session,
    *,
    level_id: int | None = None,
    level_code: str | None = None,
) -> list[EducationDegree]:
    q = (
        db.query(EducationDegree)
        .options(joinedload(EducationDegree.level))
        .filter(EducationDegree.is_active.is_(True))
        .order_by(EducationDegree.sort_order.asc(), EducationDegree.label.asc())
    )
    if level_id is not None:
        q = q.filter(EducationDegree.level_id == level_id)
    elif level_code:
        level_id = LEVEL_CODE_TO_ID.get(level_code.strip().upper())
        if level_id is not None:
            q = q.filter(EducationDegree.level_id == level_id)
        else:
            return []
    return q.all()


def get_education_degree_by_code(db: Session, code: str) -> EducationDegree | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(EducationDegree)
        .options(joinedload(EducationDegree.level))
        .filter(EducationDegree.code == normalized, EducationDegree.is_active.is_(True))
        .first()
    )


def resolve_education_payload(
    db: Session, education: OfflineLeadEducation | None
) -> dict[str, str | int] | None:
    if not education:
        return None

    payload: dict[str, str | int] = {}
    program_code = (education.program_code or "").strip().upper() or None
    degree_code = (education.degree_code or "").strip().upper() or None
    custom_degree = (education.degree or "").strip() or None
    major = (education.major or "").strip() or None
    level_id = education.level_id

    # Offline lead forms now use Levels → Programs. Candidate education still
    # posts degree_code; accept either path.
    if program_code:
        program = require_qualification_program(db, program_code, level_id=level_id)
        payload["program"] = program.name
        payload["program_code"] = program.code
        payload["level_id"] = program.level_id
        # Keep degree_* populated for list/table compatibility with older UI columns.
        payload["degree"] = program.name
        payload["degree_code"] = program.code
    elif degree_code:
        record = get_education_degree_by_code(db, degree_code)
        if not record:
            raise HTTPException(status_code=400, detail="Select a valid education degree.")
        if record.is_other:
            if not custom_degree:
                raise HTTPException(
                    status_code=400,
                    detail="Please enter the degree when Other is selected.",
                )
            payload["degree"] = custom_degree
        else:
            payload["degree"] = record.label
        payload["degree_code"] = record.code
        if record.level_id:
            payload["level_id"] = record.level_id
    else:
        raise HTTPException(status_code=400, detail="Program is required.")

    # Offline leads (program_code) always require study years. Counselling educations
    # also send the field. Legacy students_master degree-only saves may omit it.
    if program_code or education.full_time_study_years:
        resolved_level_id = payload.get("level_id")
        if resolved_level_id is None and level_id is not None:
            resolved_level_id = level_id
        study_year = require_full_time_study_years(
            db,
            education.full_time_study_years,
            level_id=int(resolved_level_id) if resolved_level_id is not None else None,
        )
        payload["full_time_study_years"] = study_year.code
        if study_year.level_id and "level_id" not in payload:
            payload["level_id"] = study_year.level_id

    if not major:
        raise HTTPException(status_code=400, detail="Major is required.")
    payload["major"] = major

    if not education.university or not education.university.strip():
        raise HTTPException(status_code=400, detail="University is required.")
    payload["university"] = education.university.strip()

    if education.graduation_year is None:
        raise HTTPException(status_code=400, detail="Graduation year is required.")
    payload["graduation_year"] = education.graduation_year

    score_code = (education.gpa_cgpa_code or "").strip().upper() or None
    if not score_code:
        raise HTTPException(status_code=400, detail="GPA/CGPA is required.")

    payload = apply_gpa_cgpa_fields(db, education, payload)
    return payload or None
