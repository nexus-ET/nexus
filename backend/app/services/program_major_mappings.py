from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.education_major import EducationMajor
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.schemas.program_major_mapping import ProgramMajorMappingRead
from app.services.education_majors import get_education_major


def _get_program(db: Session, program_id: uuid.UUID) -> Program:
    program = (
        db.query(Program)
        .options(joinedload(Program.level))
        .filter(Program.id == program_id)
        .first()
    )
    if not program:
        raise HTTPException(status_code=400, detail="Invalid program.")
    return program


def mapping_to_read(mapping: ProgramEducationMajorMapping) -> ProgramMajorMappingRead:
    major = mapping.education_major
    program = mapping.program
    level = program.level if program else None
    return ProgramMajorMappingRead(
        id=mapping.id,
        program_id=mapping.program_id,
        education_major_id=mapping.education_major_id,
        major_label=major.label if major else "",
        major_code=major.code if major else None,
        major_color=major.color if major else None,
        program_name=program.name if program else None,
        level_id=level.id if level else None,
        level_name=level.name if level else None,
    )


def list_program_major_mappings_read(db: Session) -> list[ProgramMajorMappingRead]:
    rows = (
        db.query(ProgramEducationMajorMapping)
        .options(
            joinedload(ProgramEducationMajorMapping.education_major),
            joinedload(ProgramEducationMajorMapping.program).joinedload(Program.level),
        )
        .order_by(ProgramEducationMajorMapping.id.asc())
        .all()
    )
    return [mapping_to_read(row) for row in rows]


def get_program_major_mappings(
    db: Session, program_id: uuid.UUID
) -> list[ProgramEducationMajorMapping]:
    return (
        db.query(ProgramEducationMajorMapping)
        .options(joinedload(ProgramEducationMajorMapping.education_major))
        .filter(ProgramEducationMajorMapping.program_id == program_id)
        .order_by(ProgramEducationMajorMapping.id.asc())
        .all()
    )


def get_program_major_mapping(
    db: Session, program_id: uuid.UUID, major_id: int
) -> ProgramEducationMajorMapping | None:
    return (
        db.query(ProgramEducationMajorMapping)
        .options(joinedload(ProgramEducationMajorMapping.education_major))
        .filter(
            ProgramEducationMajorMapping.program_id == program_id,
            ProgramEducationMajorMapping.education_major_id == major_id,
        )
        .first()
    )


def bulk_assign_major_to_programs(
    db: Session,
    *,
    major_id: int,
    program_ids: list[uuid.UUID],
) -> dict[str, int | list[uuid.UUID]]:
    catalog_major = get_education_major(db, major_id)
    if not catalog_major:
        raise HTTPException(status_code=404, detail="Major not found.")
    if catalog_major.program_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Only catalog majors can be assigned. Create majors from the Majors page.",
        )
    if not catalog_major.is_active:
        raise HTTPException(status_code=400, detail="Inactive majors cannot be assigned.")

    assigned = 0
    skipped = 0
    touched: list[uuid.UUID] = []
    seen_programs: set[uuid.UUID] = set()

    for program_id in program_ids:
        if program_id in seen_programs:
            continue
        seen_programs.add(program_id)
        _get_program(db, program_id)

        existing = get_program_major_mapping(db, program_id, major_id)
        if existing:
            skipped += 1
            continue

        db.add(
            ProgramEducationMajorMapping(
                program_id=program_id,
                education_major_id=major_id,
            )
        )
        assigned += 1
        touched.append(program_id)

    db.commit()
    return {
        "assigned": assigned,
        "overwritten": 0,
        "skipped": skipped,
        "program_ids": touched,
    }
