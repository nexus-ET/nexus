from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.target_course import TargetCourse
from app.models.target_program import TargetProgram
from app.services.academic_programs import MAJOR_DEFAULT_PROGRAM_CODE, get_academic_program_by_code
from app.models.program import Program
from app.schemas.offline_lead import OfflineLeadCreate
from app.services.countries import get_country_by_iso2

DEFAULT_TARGET_PROGRAMS: list[dict[str, str | int | list[dict[str, str | int]]]] = [
    {
        "code": "BUSINESS_MANAGEMENT",
        "label": "Business & Management",
        "default_program_code": "BBA",
        "sort_order": 1,
        "courses": [
            {"code": "MBA", "label": "MBA", "sort_order": 1},
            {"code": "BBA", "label": "BBA", "sort_order": 2},
            {"code": "MSC_FINANCE", "label": "MSc Finance", "sort_order": 3},
            {"code": "MSC_MARKETING", "label": "MSc Marketing", "sort_order": 4},
            {"code": "MSC_INTERNATIONAL_BUSINESS", "label": "MSc International Business", "sort_order": 5},
            {"code": "MSC_ACCOUNTING", "label": "MSc Accounting", "sort_order": 6},
        ],
    },
    {
        "code": "NURSING_MIDWIFERY",
        "label": "Nursing & Midwifery",
        "default_program_code": "BSN",
        "sort_order": 2,
        "courses": [
            {"code": "BSC_NURSING", "label": "BSc Nursing", "sort_order": 1},
            {"code": "MSC_NURSING", "label": "MSc Nursing", "sort_order": 2},
            {"code": "PGD_NURSING", "label": "Postgraduate Diploma in Nursing", "sort_order": 3},
            {"code": "MIDWIFERY", "label": "Midwifery", "sort_order": 4},
        ],
    },
    {
        "code": "ALLIED_HEALTH",
        "label": "Allied Health",
        "default_program_code": "BSC",
        "sort_order": 3,
        "courses": [
            {"code": "BSC_PHYSIOTHERAPY", "label": "BSc Physiotherapy", "sort_order": 1},
            {"code": "MSC_OCCUPATIONAL_THERAPY", "label": "MSc Occupational Therapy", "sort_order": 2},
            {"code": "BSC_RADIOGRAPHY", "label": "BSc Radiography", "sort_order": 3},
            {"code": "MSC_PUBLIC_HEALTH", "label": "MSc Public Health", "sort_order": 4},
        ],
    },
    {
        "code": "MEDICINE_DENTISTRY",
        "label": "Medicine & Dentistry",
        "default_program_code": "MBBS",
        "sort_order": 4,
        "courses": [
            {"code": "MBBS", "label": "MBBS", "sort_order": 1},
            {"code": "BDS", "label": "BDS", "sort_order": 2},
            {"code": "MD", "label": "MD", "sort_order": 3},
            {"code": "MDS", "label": "MDS", "sort_order": 4},
        ],
    },
    {
        "code": "MEDICAL_SCIENCES",
        "label": "Medical Sciences",
        "default_program_code": "MSC",
        "sort_order": 5,
        "courses": [
            {"code": "MSC_BIOMEDICAL_SCIENCE", "label": "MSc Biomedical Science", "sort_order": 1},
            {"code": "MSC_PHARMACOLOGY", "label": "MSc Pharmacology", "sort_order": 2},
            {"code": "MSC_CLINICAL_RESEARCH", "label": "MSc Clinical Research", "sort_order": 3},
            {"code": "MSC_MEDICAL_LABORATORY", "label": "MSc Medical Laboratory Science", "sort_order": 4},
        ],
    },
    {
        "code": "ENGINEERING_TECHNOLOGY",
        "label": "Engineering & Technology",
        "default_program_code": "BENG",
        "sort_order": 6,
        "courses": [
            {"code": "BENG_MECHANICAL", "label": "BEng Mechanical Engineering", "sort_order": 1},
            {"code": "MENG_CIVIL", "label": "MEng Civil Engineering", "sort_order": 2},
            {"code": "MSC_ELECTRICAL", "label": "MSc Electrical Engineering", "sort_order": 3},
            {"code": "BENG_AEROSPACE", "label": "BEng Aerospace Engineering", "sort_order": 4},
            {"code": "MSC_CHEMICAL", "label": "MSc Chemical Engineering", "sort_order": 5},
        ],
    },
    {
        "code": "COMPUTER_SCIENCE_IT",
        "label": "Computer Science & IT",
        "default_program_code": "BSC",
        "sort_order": 7,
        "courses": [
            {"code": "BSC_COMPUTER_SCIENCE", "label": "BSc Computer Science", "sort_order": 1},
            {"code": "MSC_DATA_SCIENCE", "label": "MSc Data Science", "sort_order": 2},
            {"code": "MSC_ARTIFICIAL_INTELLIGENCE", "label": "MSc Artificial Intelligence", "sort_order": 3},
            {"code": "MSC_CYBER_SECURITY", "label": "MSc Cyber Security", "sort_order": 4},
            {"code": "BSC_INFORMATION_TECHNOLOGY", "label": "BSc Information Technology", "sort_order": 5},
        ],
    },
    {
        "code": "HUMANITIES_SOCIAL_SCIENCES",
        "label": "Humanities & Social Sciences",
        "default_program_code": "BA",
        "sort_order": 8,
        "courses": [
            {"code": "MA_INTERNATIONAL_RELATIONS", "label": "MA International Relations", "sort_order": 1},
            {"code": "BA_PSYCHOLOGY", "label": "BA Psychology", "sort_order": 2},
            {"code": "MSC_SOCIOLOGY", "label": "MSc Sociology", "sort_order": 3},
            {"code": "MA_EDUCATION", "label": "MA Education", "sort_order": 4},
        ],
    },
    {
        "code": "LAW_LEGAL_STUDIES",
        "label": "Law & Legal Studies",
        "default_program_code": "LLB",
        "sort_order": 9,
        "courses": [
            {"code": "LLB", "label": "LLB", "sort_order": 1},
            {"code": "LLM", "label": "LLM", "sort_order": 2},
            {"code": "JD", "label": "JD", "sort_order": 3},
        ],
    },
    {
        "code": "NATURAL_SCIENCES",
        "label": "Natural Sciences",
        "default_program_code": "BSC",
        "sort_order": 10,
        "courses": [
            {"code": "BSC_BIOLOGY", "label": "BSc Biology", "sort_order": 1},
            {"code": "MSC_CHEMISTRY", "label": "MSc Chemistry", "sort_order": 2},
            {"code": "BSC_PHYSICS", "label": "BSc Physics", "sort_order": 3},
            {"code": "MSC_ENVIRONMENTAL_SCIENCE", "label": "MSc Environmental Science", "sort_order": 4},
        ],
    },
]


def seed_target_programs(db: Session) -> None:
    """Disabled — target programs/courses are managed via Admin UI / migrations, not startup seeds."""
    return


def list_active_target_programs(db: Session) -> list[TargetProgram]:
    return (
        db.query(TargetProgram)
        .filter(TargetProgram.is_active.is_(True))
        .order_by(TargetProgram.sort_order.asc(), TargetProgram.label.asc())
        .all()
    )


def get_target_program_by_code(db: Session, code: str) -> TargetProgram | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(TargetProgram)
        .filter(TargetProgram.code == normalized, TargetProgram.is_active.is_(True))
        .first()
    )


def list_active_target_courses(db: Session, program_code: str) -> list[TargetCourse]:
    program = get_target_program_by_code(db, program_code)
    if not program:
        return []
    return (
        db.query(TargetCourse)
        .filter(TargetCourse.program_id == program.id, TargetCourse.is_active.is_(True))
        .order_by(TargetCourse.sort_order.asc(), TargetCourse.label.asc())
        .all()
    )


def get_target_course_by_code(db: Session, code: str) -> TargetCourse | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(TargetCourse)
        .filter(TargetCourse.code == normalized, TargetCourse.is_active.is_(True))
        .first()
    )


def resolve_study_interest_fields(
    db: Session, payload: OfflineLeadCreate
) -> dict[str, str]:
    destination_iso2 = (payload.target_destination_iso2 or "").strip().upper() or None
    program_code = (payload.target_program_code or "").strip().upper() or None
    course_code = (payload.target_course_code or "").strip().upper() or None

    if not destination_iso2:
        raise HTTPException(status_code=400, detail="Target destination is required.")

    country = get_country_by_iso2(db, destination_iso2)
    if not country:
        raise HTTPException(status_code=400, detail="Select a valid target destination country.")

    if not program_code:
        raise HTTPException(status_code=400, detail="Target program is required.")

    program = get_target_program_by_code(db, program_code)
    if not program:
        raise HTTPException(status_code=400, detail="Select a valid target program.")

    if not course_code:
        raise HTTPException(status_code=400, detail="Target course is required.")

    course = get_target_course_by_code(db, course_code)
    if not course or course.program_id != program.id:
        raise HTTPException(status_code=400, detail="Select a valid target course.")

    return {
        "target_destination_iso2": country.iso2,
        "target_destination": country.name,
        "target_program_code": program.code,
        "target_program": program.label,
        "target_course_code": course.code,
        "target_course": course.label,
    }
