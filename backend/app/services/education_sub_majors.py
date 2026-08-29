from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.level import Level
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.schemas.education_sub_major import (
    EducationSubMajorCreate,
    EducationSubMajorRead,
    EducationSubMajorUpdate,
    SubMajorLevelProgramCount,
)
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name


def _program_counts_by_level_for_sub_majors(
    db: Session, sub_major_ids: list[int]
) -> dict[int, list[SubMajorLevelProgramCount]]:
    if not sub_major_ids:
        return {}

    rows = (
        db.query(
            ProgramEducationMajorMapping.education_sub_major_id,
            Level.id,
            Level.name,
            func.count(func.distinct(Program.id)),
        )
        .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
        .join(Level, Level.id == Program.level_id)
        .filter(ProgramEducationMajorMapping.education_sub_major_id.in_(sub_major_ids))
        .filter(Program.is_active.is_(True))
        .group_by(
            ProgramEducationMajorMapping.education_sub_major_id,
            Level.id,
            Level.name,
        )
        .order_by(Level.id.asc())
        .all()
    )

    grouped: dict[int, list[SubMajorLevelProgramCount]] = defaultdict(list)
    for sub_major_id, level_id, level_name, program_count in rows:
        if program_count <= 0:
            continue
        grouped[int(sub_major_id)].append(
            SubMajorLevelProgramCount(
                level_id=int(level_id),
                level_name=level_name,
                count=int(program_count),
            )
        )
    return grouped


def education_sub_major_to_read(
    record: EducationSubMajor,
    *,
    programs_by_level: list[SubMajorLevelProgramCount] | None = None,
) -> EducationSubMajorRead:
    major = record.major
    return EducationSubMajorRead(
        id=record.id,
        name=record.name,
        sub_major_description=record.sub_major_description,
        major_id=record.major_id,
        major_label=major.label if major else None,
        major_color=major.color if major else None,
        programs_by_level=programs_by_level if programs_by_level is not None else [],
    )


def education_sub_major_read(
    db: Session, record: EducationSubMajor
) -> EducationSubMajorRead:
    counts = _program_counts_by_level_for_sub_majors(db, [record.id]).get(record.id, [])
    return education_sub_major_to_read(record, programs_by_level=counts)


def _get_catalog_major(db: Session, major_id: int) -> EducationMajor:
    major = (
        db.query(EducationMajor)
        .filter(
            EducationMajor.id == major_id,
            EducationMajor.program_id.is_(None),
        )
        .first()
    )
    if not major:
        raise HTTPException(status_code=400, detail="Invalid parent major.")
    return major


def _name_exists(
    db: Session,
    *,
    major_id: int,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    if not normalized_display_name(name):
        return False
    query = filter_by_display_name(
        db.query(EducationSubMajor).filter(EducationSubMajor.major_id == major_id),
        EducationSubMajor.name,
        name,
        exclude_id=exclude_id,
        id_column=EducationSubMajor.id,
    )
    return query.first() is not None


def list_education_sub_majors_read(
    db: Session,
    *,
    query: str | None = None,
    major_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationSubMajorRead], int]:
    q = db.query(EducationSubMajor).options(joinedload(EducationSubMajor.major))
    if major_id is not None:
        q = q.filter(EducationSubMajor.major_id == major_id)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.join(EducationMajor, EducationMajor.id == EducationSubMajor.major_id).filter(
            or_(
                EducationSubMajor.name.ilike(pattern),
                EducationMajor.label.ilike(pattern),
                EducationSubMajor.sub_major_description.ilike(pattern),
            )
        )

    total = q.order_by(None).count()

    sort_map = {
        "name": EducationSubMajor.name,
        "id": EducationSubMajor.id,
        "major": EducationMajor.label,
    }
    if sort_by == "major":
        if query is None or not query.strip():
            q = q.join(EducationMajor, EducationMajor.id == EducationSubMajor.major_id)
        sort_column = EducationMajor.label
    else:
        sort_column = sort_map.get(sort_by, EducationSubMajor.name)

    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, EducationSubMajor.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts_by_sub = _program_counts_by_level_for_sub_majors(
        db, [row.id for row in rows]
    )
    return [
        education_sub_major_to_read(
            row,
            programs_by_level=counts_by_sub.get(row.id, []),
        )
        for row in rows
    ], total


def get_education_sub_major(db: Session, sub_major_id: int) -> EducationSubMajor | None:
    return (
        db.query(EducationSubMajor)
        .options(joinedload(EducationSubMajor.major))
        .filter(EducationSubMajor.id == sub_major_id)
        .first()
    )


def create_education_sub_major(
    db: Session, payload: EducationSubMajorCreate
) -> EducationSubMajorRead:
    _get_catalog_major(db, payload.major_id)
    if _name_exists(db, major_id=payload.major_id, name=payload.name):
        raise HTTPException(
            status_code=409,
            detail="A sub-major with this name already exists for the selected major.",
        )
    record = EducationSubMajor(
        name=payload.name.strip(),
        major_id=payload.major_id,
        sub_major_description=(payload.sub_major_description or "").strip() or None,
    )
    db.add(record)
    try:
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A sub-major with this name already exists for the selected major.",
        ) from None
    db.refresh(record)
    loaded = get_education_sub_major(db, record.id)
    return education_sub_major_read(db, loaded or record)


def update_education_sub_major(
    db: Session, sub_major_id: int, payload: EducationSubMajorUpdate
) -> EducationSubMajorRead:
    record = get_education_sub_major(db, sub_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Sub-major not found.")
    data = payload.model_dump(exclude_unset=True)
    next_major_id = data.get("major_id", record.major_id)
    next_name = (
        data["name"].strip()
        if "name" in data and data["name"] is not None
        else record.name
    )
    if next_major_id != record.major_id:
        _get_catalog_major(db, next_major_id)
    if _name_exists(
        db,
        major_id=next_major_id,
        name=next_name,
        exclude_id=sub_major_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="A sub-major with this name already exists for the selected major.",
        )
    if "name" in data and data["name"] is not None:
        record.name = data["name"].strip()
    if "major_id" in data and data["major_id"] is not None:
        record.major_id = data["major_id"]
    if "sub_major_description" in data:
        record.sub_major_description = (
            (data["sub_major_description"] or "").strip() or None
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A sub-major with this name already exists for the selected major.",
        ) from None
    db.refresh(record)
    loaded = get_education_sub_major(db, record.id)
    return education_sub_major_read(db, loaded or record)


def delete_education_sub_major(db: Session, sub_major_id: int) -> None:
    record = get_education_sub_major(db, sub_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Sub-major not found.")
    try:
        db.delete(record)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete this sub-major because other records still reference it.",
        ) from None
