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
) -> dict[str, object]:
    from app.models.education_major import EducationMajor
    from app.models.program_education_major_mapping import ProgramEducationMajorMapping
    from app.services.levels import get_level
    from app.services.qualification_programs import get_qualification_program_by_code

    iso2s = [
        (item or "").strip().upper()
        for item in (getattr(payload, "target_destination_iso2s", None) or [])
        if (item or "").strip()
    ]
    # Backward-compatible single destination payloads.
    if not iso2s:
        legacy = (getattr(payload, "target_destination_iso2", None) or "").strip().upper()
        if legacy:
            iso2s = [legacy]

    if not iso2s:
        raise HTTPException(status_code=400, detail="Target destination is required.")
    if len(iso2s) > 6:
        raise HTTPException(status_code=400, detail="Select up to 6 target destinations.")

    destination_names: list[str] = []
    for iso2 in iso2s:
        country = get_country_by_iso2(db, iso2)
        if not country:
            raise HTTPException(
                status_code=400,
                detail=f"Select a valid target destination country ({iso2}).",
            )
        destination_names.append(country.name)

    level_id = getattr(payload, "target_level_id", None)
    if not level_id:
        raise HTTPException(status_code=400, detail="Target level is required.")
    level = get_level(db, int(level_id))
    if not level:
        raise HTTPException(status_code=400, detail="Select a valid target level.")

    major_ids = [
        int(item)
        for item in (getattr(payload, "target_major_ids", None) or [])
        if item is not None
    ]
    if not major_ids:
        raise HTTPException(status_code=400, detail="Target major is required.")
    if len(major_ids) > 3:
        raise HTTPException(status_code=400, detail="Select up to 3 target majors.")

    majors = (
        db.query(EducationMajor)
        .filter(
            EducationMajor.id.in_(major_ids),
            EducationMajor.is_active.is_(True),
            EducationMajor.program_id.is_(None),
        )
        .all()
    )
    majors_by_id = {major.id: major for major in majors}
    if len(majors_by_id) != len(set(major_ids)):
        raise HTTPException(status_code=400, detail="Select valid target majors.")

    mapped_major_ids = {
        row[0]
        for row in (
            db.query(ProgramEducationMajorMapping.education_major_id)
            .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
            .filter(
                Program.level_id == level.id,
                Program.is_active.is_(True),
                ProgramEducationMajorMapping.education_major_id.in_(major_ids),
            )
            .all()
        )
    }
    if mapped_major_ids != set(major_ids):
        raise HTTPException(
            status_code=400,
            detail="Selected majors must belong to the chosen target level.",
        )

    program_codes = [
        (item or "").strip().upper()
        for item in (getattr(payload, "target_program_codes", None) or [])
        if (item or "").strip()
    ]
    if not program_codes:
        raise HTTPException(status_code=400, detail="Target program is required.")

    resolved_programs: list[Program] = []
    for code in program_codes:
        program = get_qualification_program_by_code(db, code)
        if not program or program.level_id != level.id:
            raise HTTPException(
                status_code=400,
                detail=f"Select a valid target program for the chosen level ({code}).",
            )
        linked = (
            db.query(ProgramEducationMajorMapping.id)
            .filter(
                ProgramEducationMajorMapping.program_id == program.id,
                ProgramEducationMajorMapping.education_major_id.in_(major_ids),
            )
            .first()
        )
        if not linked:
            raise HTTPException(
                status_code=400,
                detail=f"Program {code} is not linked to the selected majors.",
            )
        resolved_programs.append(program)

    major_labels = [majors_by_id[major_id].label for major_id in major_ids]
    program_names = [program.name for program in resolved_programs]
    program_codes_out = [program.code for program in resolved_programs]
    destination_label = ", ".join(destination_names)
    programs_label = ", ".join(program_names)

    return {
        "target_destination_iso2s": iso2s,
        "target_destinations": destination_names,
        "target_destination_iso2": iso2s[0],
        "target_destination": destination_label,
        "target_level_id": level.id,
        "target_level_name": level.name,
        "target_major_ids": major_ids,
        "target_majors": major_labels,
        "target_program_codes": program_codes_out,
        "target_programs": program_names,
        "target_program_code": program_codes_out[0] if program_codes_out else None,
        "target_program": programs_label,
        "target_course_code": None,
        "target_course": None,
    }
