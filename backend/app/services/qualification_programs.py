from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping


def list_active_qualification_programs(
    db: Session,
    *,
    level_id: int | None = None,
) -> list[Program]:
    q = (
        db.query(Program)
        .options(
            joinedload(Program.level),
            joinedload(Program.education_major_mappings).joinedload(
                ProgramEducationMajorMapping.education_major
            ),
        )
        .filter(Program.is_active.is_(True))
        .order_by(Program.sort_order.asc(), Program.name.asc())
    )
    if level_id is not None:
        q = q.filter(Program.level_id == level_id)
    return q.all()


def get_qualification_program_by_code(db: Session, code: str) -> Program | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(Program)
        .options(joinedload(Program.level))
        .filter(Program.code == normalized, Program.is_active.is_(True))
        .first()
    )


def require_qualification_program(
    db: Session,
    code: str | None,
    *,
    level_id: int | None = None,
) -> Program:
    normalized = (code or "").strip().upper() or None
    if not normalized:
        raise HTTPException(status_code=400, detail="Program is required.")
    record = get_qualification_program_by_code(db, normalized)
    if not record:
        raise HTTPException(status_code=400, detail="Select a valid program.")
    if level_id is not None and record.level_id != level_id:
        raise HTTPException(
            status_code=400,
            detail="Selected program does not belong to the chosen level.",
        )
    return record
