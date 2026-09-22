from __future__ import annotations

import re
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.education_super_major import EducationSuperMajor
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.target_course import TargetCourse
from app.schemas.education_super_major import (
    EducationSuperMajorCreate,
    EducationSuperMajorRead,
    EducationSuperMajorUpdate,
)
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name


class SuperMajorDependentCounts(TypedDict):
    majors: int
    sub_majors: int
    program_mappings: int
    programs: int
    target_courses: int


def _slugify_code(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip().upper())
    return re.sub(r"_+", "_", cleaned).strip("_")


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def _name_exists(
    db: Session,
    *,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    if not normalized_display_name(name):
        return False
    query = filter_by_display_name(
        db.query(EducationSuperMajor),
        EducationSuperMajor.name,
        name,
        exclude_id=exclude_id,
        id_column=EducationSuperMajor.id,
    )
    return query.first() is not None


def _resolve_code(
    db: Session,
    *,
    code: str | None,
    name: str,
    exclude_id: int | None = None,
) -> str:
    candidate = _normalize_code(code) if code and str(code).strip() else _slugify_code(name)
    if not candidate:
        raise HTTPException(status_code=400, detail="Super-major code is required.")
    query = db.query(EducationSuperMajor).filter(EducationSuperMajor.code == candidate)
    if exclude_id is not None:
        query = query.filter(EducationSuperMajor.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Super-major code already exists.")
    return candidate


def _major_counts(db: Session, super_major_ids: list[int]) -> dict[int, int]:
    if not super_major_ids:
        return {}
    rows = (
        db.query(EducationMajor.super_major_id, func.count(EducationMajor.id))
        .filter(
            EducationMajor.super_major_id.in_(super_major_ids),
            EducationMajor.program_id.is_(None),
        )
        .group_by(EducationMajor.super_major_id)
        .all()
    )
    return {int(sid): int(count) for sid, count in rows}


def education_super_major_to_read(
    record: EducationSuperMajor,
    *,
    major_count: int = 0,
) -> EducationSuperMajorRead:
    return EducationSuperMajorRead(
        id=record.id,
        name=record.name,
        code=record.code,
        description=record.description,
        sort_order=record.sort_order,
        is_active=record.is_active,
        major_count=major_count,
    )


def education_super_major_read(
    db: Session, record: EducationSuperMajor
) -> EducationSuperMajorRead:
    count = _major_counts(db, [record.id]).get(record.id, 0)
    return education_super_major_to_read(record, major_count=count)


def list_education_super_majors_read(
    db: Session,
    *,
    query: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "sort_order",
    sort_dir: str = "asc",
) -> tuple[list[EducationSuperMajorRead], int]:
    q = db.query(EducationSuperMajor)
    if active_only:
        q = q.filter(EducationSuperMajor.is_active.is_(True))
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                EducationSuperMajor.name.ilike(pattern),
                EducationSuperMajor.code.ilike(pattern),
                EducationSuperMajor.description.ilike(pattern),
            )
        )

    total = q.order_by(None).count()

    sort_map = {
        "name": EducationSuperMajor.name,
        "code": EducationSuperMajor.code,
        "sort_order": EducationSuperMajor.sort_order,
        "id": EducationSuperMajor.id,
    }
    sort_column = sort_map.get(sort_by, EducationSuperMajor.sort_order)
    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, EducationSuperMajor.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = _major_counts(db, [row.id for row in rows])
    return [
        education_super_major_to_read(row, major_count=counts.get(row.id, 0))
        for row in rows
    ], total


def get_education_super_major(
    db: Session, super_major_id: int
) -> EducationSuperMajor | None:
    return (
        db.query(EducationSuperMajor)
        .filter(EducationSuperMajor.id == super_major_id)
        .first()
    )


def create_education_super_major(
    db: Session, payload: EducationSuperMajorCreate
) -> EducationSuperMajorRead:
    if _name_exists(db, name=payload.name):
        raise HTTPException(
            status_code=409,
            detail="A super-major with this name already exists.",
        )
    code = _resolve_code(db, code=payload.code, name=payload.name)
    record = EducationSuperMajor(
        name=payload.name.strip(),
        code=code,
        description=(payload.description or "").strip() or None,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(record)
    try:
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A super-major with this name or code already exists.",
        ) from None
    db.refresh(record)
    from app.services.taxonomy_embeddings import schedule_super_major_embedding

    schedule_super_major_embedding(record.id)
    return education_super_major_to_read(record, major_count=0)


def update_education_super_major(
    db: Session, super_major_id: int, payload: EducationSuperMajorUpdate
) -> EducationSuperMajorRead:
    record = get_education_super_major(db, super_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Super-major not found.")
    data = payload.model_dump(exclude_unset=True)
    next_name = (
        data["name"].strip()
        if "name" in data and data["name"] is not None
        else record.name
    )
    if _name_exists(db, name=next_name, exclude_id=super_major_id):
        raise HTTPException(
            status_code=409,
            detail="A super-major with this name already exists.",
        )
    if "name" in data and data["name"] is not None:
        record.name = data["name"].strip()
    if "code" in data:
        if data["code"] and str(data["code"]).strip():
            record.code = _resolve_code(
                db,
                code=str(data["code"]),
                name=next_name,
                exclude_id=super_major_id,
            )
        else:
            raise HTTPException(status_code=400, detail="Super-major code is required.")
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A super-major with this name or code already exists.",
        ) from None
    db.refresh(record)
    from app.services.taxonomy_embeddings import schedule_super_major_embedding

    schedule_super_major_embedding(record.id)
    count = _major_counts(db, [record.id]).get(record.id, 0)
    return education_super_major_to_read(record, major_count=count)


def count_super_major_dependents(
    db: Session, super_major_id: int
) -> SuperMajorDependentCounts:
    """Counts taxonomy/program dependents reachable through this super-major."""
    major_ids = [
        int(row[0])
        for row in db.query(EducationMajor.id)
        .filter(EducationMajor.super_major_id == super_major_id)
        .all()
    ]
    if not major_ids:
        return {
            "majors": 0,
            "sub_majors": 0,
            "program_mappings": 0,
            "programs": 0,
            "target_courses": 0,
        }

    sub_majors = (
        db.query(func.count(EducationSubMajor.id))
        .filter(EducationSubMajor.major_id.in_(major_ids))
        .scalar()
        or 0
    )
    program_mappings = (
        db.query(func.count(ProgramEducationMajorMapping.id))
        .filter(ProgramEducationMajorMapping.education_major_id.in_(major_ids))
        .scalar()
        or 0
    )
    programs = (
        db.query(func.count(func.distinct(ProgramEducationMajorMapping.program_id)))
        .filter(ProgramEducationMajorMapping.education_major_id.in_(major_ids))
        .scalar()
        or 0
    )
    target_courses = (
        db.query(func.count(TargetCourse.id))
        .filter(TargetCourse.education_major_id.in_(major_ids))
        .scalar()
        or 0
    )
    return {
        "majors": len(major_ids),
        "sub_majors": int(sub_majors),
        "program_mappings": int(program_mappings),
        "programs": int(programs),
        "target_courses": int(target_courses),
    }


def format_super_major_delete_block_detail(
    counts: SuperMajorDependentCounts,
) -> str | None:
    """Return a 409 detail when the super still has children/programs; else None."""
    majors = counts["majors"]
    program_mappings = counts["program_mappings"]
    target_courses = counts["target_courses"]
    if majors == 0 and program_mappings == 0 and target_courses == 0:
        return None

    parts = [
        f"{majors} major{'s' if majors != 1 else ''}",
        f"{counts['sub_majors']} sub-major{'s' if counts['sub_majors'] != 1 else ''}",
        (
            f"{counts['programs']} program{'s' if counts['programs'] != 1 else ''} "
            f"({program_mappings} mapping{'s' if program_mappings != 1 else ''})"
        ),
    ]
    if target_courses:
        parts.append(
            f"{target_courses} target course{'s' if target_courses != 1 else ''}"
        )
    return (
        "Cannot delete this super-major because it still has "
        + ", ".join(parts[:-1])
        + (f", and {parts[-1]}" if len(parts) > 1 else parts[0])
        + ". Remap or remove those majors, sub-majors, and program mappings first."
    )


def ensure_super_major_deletable(db: Session, super_major_id: int) -> None:
    """Raise 409 if this super-major still has majors or reachable program links."""
    detail = format_super_major_delete_block_detail(
        count_super_major_dependents(db, super_major_id)
    )
    if detail:
        raise HTTPException(status_code=409, detail=detail)


def delete_education_super_major(db: Session, super_major_id: int) -> None:
    record = get_education_super_major(db, super_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Super-major not found.")
    ensure_super_major_deletable(db, super_major_id)
    db.delete(record)
    db.commit()
