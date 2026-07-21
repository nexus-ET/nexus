from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.education_course import EducationCourse
from app.models.education_degree import EducationDegree
from app.models.education_major_level import EducationMajorLevel
from app.models.level import Level
from app.models.program import Program
from app.schemas.level import LevelCreate, LevelUpdate
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name


def get_level_by_name(db: Session, name: str, *, exclude_id: int | None = None) -> Level | None:
    normalized = normalized_display_name(name)
    if not normalized:
        return None
    query = filter_by_display_name(db.query(Level), Level.name, name, exclude_id=exclude_id, id_column=Level.id)
    return query.first()


def list_levels(db: Session, *, query: str | None = None) -> list[Level]:
    q = db.query(Level).order_by(Level.id.asc())
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            Level.code.ilike(pattern)
            | Level.name.ilike(pattern)
            | Level.description.ilike(pattern)
        )
    return q.all()


def get_level(db: Session, level_id: int) -> Level | None:
    return db.query(Level).filter(Level.id == level_id).first()


def get_level_by_code(db: Session, code: str) -> Level | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return db.query(Level).filter(Level.code == normalized).first()


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def create_level(db: Session, payload: LevelCreate) -> Level:
    code = _normalize_code(payload.code)
    if get_level_by_code(db, code):
        raise HTTPException(status_code=409, detail="Level code already exists.")
    if get_level_by_name(db, payload.name):
        raise HTTPException(status_code=409, detail="A level with this name already exists.")
    next_id = (db.query(func.max(Level.id)).scalar() or 0) + 1
    record = Level(
        id=next_id,
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_level(db: Session, level_id: int, payload: LevelUpdate) -> Level:
    record = get_level(db, level_id)
    if not record:
        raise HTTPException(status_code=404, detail="Level not found.")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] is not None:
        code = _normalize_code(data["code"])
        conflict = (
            db.query(Level)
            .filter(Level.code == code, Level.id != level_id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Level code already exists.")
        record.code = code
    if "name" in data and data["name"] is not None:
        next_name = data["name"].strip()
        if get_level_by_name(db, next_name, exclude_id=level_id):
            raise HTTPException(status_code=409, detail="A level with this name already exists.")
        record.name = next_name
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    db.commit()
    db.refresh(record)
    return record


def delete_level(db: Session, level_id: int) -> None:
    record = get_level(db, level_id)
    if not record:
        raise HTTPException(status_code=404, detail="Level not found.")

    program_count = db.query(Program).filter(Program.level_id == level_id).count()
    education_count = (
        db.query(EducationDegree).filter(EducationDegree.level_id == level_id).count()
    )
    course_count = (
        db.query(EducationCourse).filter(EducationCourse.level_id == level_id).count()
    )
    major_link_count = (
        db.query(EducationMajorLevel)
        .filter(EducationMajorLevel.level_id == level_id)
        .count()
    )
    if program_count or education_count or course_count or major_link_count:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete level while programs, majors, courses, or education degrees "
                "still reference it. Reassign those records first."
            ),
        )

    db.delete(record)
    db.commit()


def seed_levels(db: Session) -> None:
    """Disabled — levels are managed via Admin UI / migrations, not startup seeds."""
    return
