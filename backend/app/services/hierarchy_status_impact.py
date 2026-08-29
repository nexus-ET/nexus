from __future__ import annotations

import uuid
from enum import Enum

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.education_course import EducationCourse
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_major import EducationMajor
from app.models.level import Level
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.services.education_courses import get_education_course
from app.services.education_majors import get_education_major
from app.services.levels import get_level


def _courses_for_major_query(db: Session, major_id: int):
    return (
        db.query(EducationCourse.id)
        .join(
            CourseEducationMajorMapping,
            CourseEducationMajorMapping.course_id == EducationCourse.id,
        )
        .filter(CourseEducationMajorMapping.education_major_id == major_id)
    )


def _courses_for_program_query(db: Session, program_id: int):
    return (
        db.query(EducationCourse.id)
        .join(
            CourseEducationMajorMapping,
            CourseEducationMajorMapping.course_id == EducationCourse.id,
        )
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.education_major_id
            == CourseEducationMajorMapping.education_major_id,
        )
        .filter(ProgramEducationMajorMapping.program_id == program_id)
        .distinct()
    )


def _courses_for_level_query(db: Session, level_id: int):
    return (
        db.query(EducationCourse.id)
        .join(
            CourseEducationMajorMapping,
            CourseEducationMajorMapping.course_id == EducationCourse.id,
        )
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.education_major_id
            == CourseEducationMajorMapping.education_major_id,
        )
        .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
        .filter(Program.level_id == level_id)
        .distinct()
    )


class HierarchyEntityType(str, Enum):
    level = "level"
    major = "major"
    program = "program"
    course = "course"


class HierarchyStatusImpactRead(BaseModel):
    entity_type: HierarchyEntityType
    entity_id: str
    entity_name: str
    current_is_active: bool
    proposed_is_active: bool
    majors: int = 0
    programs: int = 0
    courses: int = 0
    message: str = Field(default="")


def _build_message(
    *,
    entity_label: str,
    proposed_is_active: bool,
    majors: int,
    programs: int,
    courses: int,
) -> str:
    if proposed_is_active:
        parts: list[str] = []
        if programs:
            parts.append(f"{programs} inactive program{'s' if programs != 1 else ''}")
        if majors:
            parts.append(f"{majors} inactive major{'s' if majors != 1 else ''}")
        if courses:
            parts.append(f"{courses} inactive course{'s' if courses != 1 else ''}")
        if not parts:
            return (
                f"Reactivating this {entity_label} will not automatically change any child items."
            )
        joined = ", ".join(parts[:-1]) + (
            f", and {parts[-1]}" if len(parts) > 1 else parts[0]
        )
        return (
            f"Reactivating this {entity_label} will not automatically reactivate {joined} "
            "below it. Review child items separately if needed."
        )

    parts = []
    if programs:
        parts.append(f"{programs} active program{'s' if programs != 1 else ''}")
    if majors:
        parts.append(f"{majors} active major{'s' if majors != 1 else ''}")
    if courses:
        parts.append(f"{courses} active course{'s' if courses != 1 else ''}")
    if not parts:
        return (
            f"Marking this {entity_label} inactive affects only this record. "
            "No active child items are linked below it."
        )
    joined = ", ".join(parts[:-1]) + (f", and {parts[-1]}" if len(parts) > 1 else parts[0])
    return (
        f"Marking this {entity_label} inactive may hide it from selection flows. "
        f"{joined} linked below it will be impacted and may become harder to reach through this branch."
    )


def _level_impact(
    db: Session, level_id: int, proposed_is_active: bool
) -> tuple[str, bool, int, int, int]:
    record = get_level(db, level_id)
    if not record:
        raise HTTPException(status_code=404, detail="Level not found.")
    active_only = not proposed_is_active

    program_q = db.query(Program.id).filter(Program.level_id == level_id)
    if active_only:
        program_q = program_q.filter(Program.is_active.is_(True))
    programs = program_q.count()

    major_q = (
        db.query(ProgramEducationMajorMapping.education_major_id)
        .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
        .join(EducationMajor, EducationMajor.id == ProgramEducationMajorMapping.education_major_id)
        .filter(Program.level_id == level_id)
    )
    if active_only:
        major_q = major_q.filter(EducationMajor.is_active.is_(True))
    majors = major_q.distinct().count()

    course_q = _courses_for_level_query(db, level_id)
    if active_only:
        course_q = course_q.filter(EducationCourse.is_active.is_(True))
    courses = course_q.count()

    if proposed_is_active:
        programs = (
            db.query(Program.id)
            .filter(Program.level_id == level_id, Program.is_active.is_(False))
            .count()
        )
        majors = (
            db.query(ProgramEducationMajorMapping.education_major_id)
            .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
            .join(
                EducationMajor,
                EducationMajor.id == ProgramEducationMajorMapping.education_major_id,
            )
            .filter(Program.level_id == level_id, EducationMajor.is_active.is_(False))
            .distinct()
            .count()
        )
        courses = (
            _courses_for_level_query(db, level_id)
            .filter(EducationCourse.is_active.is_(False))
            .count()
        )

    return record.name, record.is_active, majors, programs, courses


def _major_impact(
    db: Session, major_id: int, proposed_is_active: bool
) -> tuple[str, bool, int, int, int]:
    record = get_education_major(db, major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Major not found.")
    if proposed_is_active:
        courses = (
            _courses_for_major_query(db, major_id)
            .filter(EducationCourse.is_active.is_(False))
            .count()
        )
        return record.label, record.is_active, 0, 0, courses

    courses = (
        _courses_for_major_query(db, major_id)
        .filter(EducationCourse.is_active.is_(True))
        .count()
    )
    return record.label, record.is_active, 0, 0, courses


def _program_impact(
    db: Session, program_id: int, proposed_is_active: bool
) -> tuple[str, bool, int, int, int]:
    record = db.query(Program).filter(Program.id == program_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Program not found.")
    if proposed_is_active:
        majors = (
            db.query(ProgramEducationMajorMapping.id)
            .join(
                EducationMajor,
                EducationMajor.id == ProgramEducationMajorMapping.education_major_id,
            )
            .filter(
                ProgramEducationMajorMapping.program_id == program_id,
                EducationMajor.is_active.is_(False),
            )
            .count()
        )
        courses = (
            _courses_for_program_query(db, program_id)
            .filter(EducationCourse.is_active.is_(False))
            .count()
        )
        return record.name, record.is_active, majors, 0, courses

    majors = (
        db.query(ProgramEducationMajorMapping.id)
        .join(
            EducationMajor,
            EducationMajor.id == ProgramEducationMajorMapping.education_major_id,
        )
        .filter(
            ProgramEducationMajorMapping.program_id == program_id,
            EducationMajor.is_active.is_(True),
        )
        .count()
    )
    courses = (
        _courses_for_program_query(db, program_id)
        .filter(EducationCourse.is_active.is_(True))
        .count()
    )
    return record.name, record.is_active, majors, 0, courses


def _course_impact(db: Session, course_id: int, proposed_is_active: bool) -> tuple[str, bool, int, int, int]:
    record = get_education_course(db, course_id)
    return record.label, record.is_active, 0, 0, 0


def get_hierarchy_status_impact(
    db: Session,
    *,
    entity_type: HierarchyEntityType,
    entity_id: str,
    proposed_is_active: bool,
) -> HierarchyStatusImpactRead:
    if entity_type == HierarchyEntityType.level:
        name, current, majors, programs, courses = _level_impact(
            db, int(entity_id), proposed_is_active
        )
        label = "level"
    elif entity_type == HierarchyEntityType.major:
        name, current, majors, programs, courses = _major_impact(
            db, int(entity_id), proposed_is_active
        )
        label = "major"
    elif entity_type == HierarchyEntityType.program:
        name, current, majors, programs, courses = _program_impact(
            db, uuid.UUID(entity_id), proposed_is_active
        )
        label = "program"
    elif entity_type == HierarchyEntityType.course:
        name, current, majors, programs, courses = _course_impact(
            db, int(entity_id), proposed_is_active
        )
        label = "course"
    else:
        raise HTTPException(status_code=400, detail="Unsupported entity type.")

    if current == proposed_is_active:
        return HierarchyStatusImpactRead(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=name,
            current_is_active=current,
            proposed_is_active=proposed_is_active,
            majors=majors,
            programs=programs,
            courses=courses,
            message="No status change.",
        )

    return HierarchyStatusImpactRead(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=name,
        current_is_active=current,
        proposed_is_active=proposed_is_active,
        majors=majors,
        programs=programs,
        courses=courses,
        message=_build_message(
            entity_label=label,
            proposed_is_active=proposed_is_active,
            majors=majors,
            programs=programs,
            courses=courses,
        ),
    )
