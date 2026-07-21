from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.education_major import EducationMajor
from app.models.program import Program
from app.models.target_course import TargetCourse
from app.models.target_program import TargetProgram
from app.services.education_majors import get_education_major_by_code
from app.services.education_majors import get_education_major_by_code

# Framework discipline umbrellas (target_programs) mapped to catalog majors.
TARGET_PROGRAM_MAJOR_CODE_MAP: dict[str, str] = {
    "COMPUTER_SCIENCE_IT": "COMPUTER_SCIENCE",
    "NATURAL_SCIENCES": "BIOTECHNOLOGY",
    "ALLIED_HEALTH": "MEDICINE",
    "HUMANITIES_SOCIAL_SCIENCES": "PSYCHOLOGY",
    "MEDICINE_DENTISTRY": "MEDICINE",
    "BUSINESS_MANAGEMENT": "BUSINESS_ADMINISTRATION",
    "MEDICAL_SCIENCES": "MEDICINE",
    "NURSING_MIDWIFERY": "MEDICINE",
    "ENGINEERING_TECHNOLOGY": "ENGINEERING",
    "LAW_LEGAL_STUDIES": "LAW",
}


def resolve_education_major_for_target_program(
    db: Session, target_program: TargetProgram | None
) -> EducationMajor | None:
    if not target_program:
        return None

    mapped_code = TARGET_PROGRAM_MAJOR_CODE_MAP.get(target_program.code.upper())
    if mapped_code:
        major = get_education_major_by_code(db, mapped_code)
        if major:
            return major

    major = get_education_major_by_code(db, target_program.code)
    if major:
        return major

    label = (target_program.label or "").strip()
    if label:
        return (
            db.query(EducationMajor)
            .filter(EducationMajor.label.ilike(label), EducationMajor.is_active.is_(True))
            .first()
        )
    return None


def resolve_education_major_id_for_target_program_id(
    db: Session, target_program_id: int | None
) -> int | None:
    if not target_program_id:
        return None
    target_program = db.query(TargetProgram).filter(TargetProgram.id == target_program_id).first()
    major = resolve_education_major_for_target_program(db, target_program)
    return major.id if major else None


def resolve_education_major_id_for_course(db: Session, course: TargetCourse) -> int | None:
    if course.education_major_id:
        return course.education_major_id
    return resolve_education_major_id_for_target_program_id(db, course.program_id)


def backfill_target_course_education_majors(db: Session) -> int:
    """Persist education_major_id on legacy courses linked via target_programs."""
    updated = 0
    courses = (
        db.query(TargetCourse)
        .filter(TargetCourse.education_major_id.is_(None))
        .all()
    )
    for course in courses:
        major_id = resolve_education_major_id_for_target_program_id(db, course.program_id)
        if not major_id:
            continue
        course.education_major_id = major_id
        updated += 1
    if updated:
        db.commit()
    return updated


def backfill_target_course_qualification_programs(db: Session) -> int:
    """Persist qualification_program_id on legacy courses linked via target_programs."""
    updated = 0
    courses = (
        db.query(TargetCourse)
        .filter(TargetCourse.qualification_program_id.is_(None))
        .all()
    )
    for course in courses:
        target_program = (
            db.query(TargetProgram).filter(TargetProgram.id == course.program_id).first()
        )
        if not target_program or not target_program.program_id:
            continue
        course.qualification_program_id = target_program.program_id
        if not course.education_major_id:
            major = (
                db.query(EducationMajor)
                .filter(EducationMajor.program_id == target_program.program_id)
                .order_by(EducationMajor.sort_order.asc(), EducationMajor.id.asc())
                .first()
            )
            if major:
                course.education_major_id = major.id
        updated += 1
    if updated:
        db.commit()
    return updated
