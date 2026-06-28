from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.education_degree import EducationDegree
from app.schemas.offline_lead import OfflineLeadEducation
from app.services.gpa_cgpa_scores import apply_gpa_cgpa_fields

DEFAULT_EDUCATION_DEGREES: list[dict[str, str | int | bool]] = [
    {"code": "HIGH_SCHOOL_DIPLOMA_GED", "label": "High School Diploma / GED", "sort_order": 1},
    {"code": "ASSOCIATE_DEGREE", "label": "Associate Degree (AA/AS)", "sort_order": 2},
    {"code": "BACHELORS_DEGREE", "label": "Bachelor's Degree (BA/BS/B.Tech)", "sort_order": 3},
    {"code": "MASTERS_DEGREE", "label": "Master's Degree (MA/MS/MBA/M.Tech)", "sort_order": 4},
    {"code": "DOCTORATE", "label": "Doctorate (PhD/EdD)", "sort_order": 5},
    {"code": "PROFESSIONAL_DEGREE", "label": "Professional Degree (JD/MD)", "sort_order": 6},
    {
        "code": "BACHELORS_3Y_INTERNATIONAL",
        "label": "Bachelor's (3-Year International)",
        "sort_order": 7,
    },
    {
        "code": "BACHELORS_4Y_INTERNATIONAL",
        "label": "Bachelor's (4-Year International)",
        "sort_order": 8,
    },
    {"code": "POST_GRADUATE_DIPLOMA", "label": "Post-Graduate Diploma (PGD)", "sort_order": 9},
    {"code": "INTEGRATED_MASTERS", "label": "Integrated Master's", "sort_order": 10},
    {"code": "STEM_DESIGNATED", "label": "STEM-Designated Degree", "sort_order": 11},
    {"code": "BOOTCAMP_GRADUATE", "label": "Bootcamp Graduate", "sort_order": 12},
    {
        "code": "PROFESSIONAL_CERTIFICATION_ONLY",
        "label": "Professional Certification Only",
        "sort_order": 13,
    },
    {"code": "SOME_COLLEGE_NO_DEGREE", "label": "Some College (No Degree)", "sort_order": 14},
    {"code": "OTHER", "label": "Other", "sort_order": 99, "is_other": True},
]


def seed_education_degrees(db: Session) -> None:
    for item in DEFAULT_EDUCATION_DEGREES:
        existing = db.query(EducationDegree).filter(EducationDegree.code == item["code"]).first()
        if existing:
            existing.label = str(item["label"])
            existing.sort_order = int(item["sort_order"])
            existing.is_other = bool(item.get("is_other", False))
            existing.is_active = True
            continue
        db.add(
            EducationDegree(
                code=str(item["code"]),
                label=str(item["label"]),
                sort_order=int(item["sort_order"]),
                is_other=bool(item.get("is_other", False)),
                is_active=True,
            )
        )
    db.commit()


def list_active_education_degrees(db: Session) -> list[EducationDegree]:
    return (
        db.query(EducationDegree)
        .filter(EducationDegree.is_active.is_(True))
        .order_by(EducationDegree.sort_order.asc(), EducationDegree.label.asc())
        .all()
    )


def get_education_degree_by_code(db: Session, code: str) -> EducationDegree | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(EducationDegree)
        .filter(EducationDegree.code == normalized, EducationDegree.is_active.is_(True))
        .first()
    )


def resolve_education_payload(
    db: Session, education: OfflineLeadEducation | None
) -> dict[str, str | int] | None:
    if not education:
        return None

    payload: dict[str, str | int] = {}
    degree_code = (education.degree_code or "").strip().upper() or None
    custom_degree = (education.degree or "").strip() or None
    major = (education.major or "").strip() or None

    if not degree_code:
        raise HTTPException(status_code=400, detail="Degree is required.")

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
