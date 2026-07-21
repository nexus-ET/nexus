from __future__ import annotations

import uuid

from fastapi import HTTPException
from collections import defaultdict

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.education_major import EducationMajor
from app.models.education_major_level import EducationMajorLevel
from app.models.level import Level
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.schemas.education_major import (
    EducationMajorCreate,
    EducationMajorRead,
    EducationMajorUpdate,
    MajorLevelProgramCount,
)
from app.services.major_colors import assign_major_color, ensure_major_color
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def _major_label_exists(
    db: Session,
    *,
    program_id: uuid.UUID | None,
    label: str,
    exclude_id: int | None = None,
) -> bool:
    if not normalized_display_name(label):
        return False
    program_filter = (
        EducationMajor.program_id == program_id
        if program_id is not None
        else EducationMajor.program_id.is_(None)
    )
    query = filter_by_display_name(
        db.query(EducationMajor).filter(program_filter),
        EducationMajor.label,
        label,
        exclude_id=exclude_id,
        id_column=EducationMajor.id,
    )
    return query.first() is not None


def _resolve_major_code(db: Session, code: str | None) -> str | None:
    if not code or not code.strip():
        return None
    normalized = _normalize_code(code)
    existing = db.query(EducationMajor).filter(EducationMajor.code == normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="Major code already exists.")
    return normalized


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


def _sync_education_major_levels_from_program(
    db: Session, major_id: int, program: Program
) -> None:
    db.query(EducationMajorLevel).filter(
        EducationMajorLevel.education_major_id == major_id
    ).delete(synchronize_session=False)
    db.add(
        EducationMajorLevel(education_major_id=major_id, level_id=program.level_id)
    )


def _level_details_for_major(db: Session, major_id: int) -> tuple[list[int], list[str]]:
    rows = (
        db.query(Level.id, Level.name)
        .join(EducationMajorLevel, EducationMajorLevel.level_id == Level.id)
        .filter(EducationMajorLevel.education_major_id == major_id)
        .order_by(Level.id.asc())
        .all()
    )
    return [row.id for row in rows], [row.name for row in rows]


def _program_counts_by_level_for_major(
    db: Session, major_id: int
) -> list[MajorLevelProgramCount]:
    return _program_counts_by_level_for_majors(db, [major_id]).get(major_id, [])


def _program_counts_by_level_for_majors(
    db: Session, major_ids: list[int]
) -> dict[int, list[MajorLevelProgramCount]]:
    if not major_ids:
        return {}

    rows = (
        db.query(
            ProgramEducationMajorMapping.education_major_id,
            Level.id,
            Level.name,
            func.count(ProgramEducationMajorMapping.program_id),
        )
        .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
        .join(Level, Level.id == Program.level_id)
        .filter(ProgramEducationMajorMapping.education_major_id.in_(major_ids))
        .filter(Program.is_active.is_(True))
        .group_by(
            ProgramEducationMajorMapping.education_major_id,
            Level.id,
            Level.name,
        )
        .order_by(Level.id.asc())
        .all()
    )

    grouped: dict[int, list[MajorLevelProgramCount]] = defaultdict(list)
    for major_id, level_id, level_name, program_count in rows:
        grouped[major_id].append(
            MajorLevelProgramCount(
                level_id=level_id,
                level_name=level_name,
                program_count=program_count,
            )
        )
    return grouped


def education_major_to_read(
    db: Session,
    record: EducationMajor,
    *,
    level_program_counts: list[MajorLevelProgramCount] | None = None,
) -> EducationMajorRead:
    level_ids, level_names = _level_details_for_major(db, record.id)
    if level_program_counts is None:
        level_program_counts = _program_counts_by_level_for_major(db, record.id)
    program = record.program
    if record.program_id and not program:
        program = _get_program(db, record.program_id)
    return EducationMajorRead(
        id=record.id,
        code=record.code,
        label=record.label,
        description=record.description,
        program_id=record.program_id,
        program_name=program.name if program else None,
        level_id=program.level_id if program else (level_ids[0] if level_ids else None),
        level_name=program.level.name if program and program.level else (
            level_names[0] if level_names else None
        ),
        is_other=record.is_other,
        sort_order=record.sort_order,
        is_active=record.is_active,
        color=record.color,
        level_ids=level_ids,
        level_names=level_names,
        level_program_counts=level_program_counts,
    )


def seed_education_majors(db: Session) -> None:
    """Disabled — majors are managed only via Academia Hub UI, not startup seeds."""
    return


def list_education_majors(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: uuid.UUID | None = None,
    catalog_only: bool = True,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationMajor], int]:
    q = db.query(EducationMajor).options(
        joinedload(EducationMajor.program).joinedload(Program.level)
    )
    if active_only:
        q = q.filter(EducationMajor.is_active.is_(True))
    if catalog_only and program_id is None:
        q = q.filter(EducationMajor.program_id.is_(None))
    if program_id is not None:
        q = q.filter(EducationMajor.program_id == program_id)
    if level_id is not None:
        q = q.join(Program, Program.id == EducationMajor.program_id).filter(
            Program.level_id == level_id
        )
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(EducationMajor.label.ilike(pattern), EducationMajor.code.ilike(pattern))
        )

    total = q.order_by(None).count()

    sort_map = {
        "name": EducationMajor.label,
        "code": EducationMajor.code,
        "sort_order": EducationMajor.sort_order,
        "id": EducationMajor.id,
    }
    if sort_by == "program":
        if level_id is None:
            q = q.join(Program, Program.id == EducationMajor.program_id)
        sort_column = Program.name
    elif sort_by == "level":
        if level_id is None:
            q = q.join(Program, Program.id == EducationMajor.program_id)
        q = q.join(Level, Level.id == Program.level_id)
        sort_column = Level.name
    else:
        sort_column = sort_map.get(sort_by, EducationMajor.label)

    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, EducationMajor.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def list_education_majors_all(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> list[EducationMajor]:
    rows, _ = list_education_majors(
        db,
        query=query,
        level_id=level_id,
        program_id=program_id,
        active_only=active_only,
        page=1,
        page_size=10_000,
    )
    return rows


def list_education_majors_read(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: uuid.UUID | None = None,
    catalog_only: bool = True,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationMajorRead], int]:
    rows, total = list_education_majors(
        db,
        query=query,
        level_id=level_id,
        program_id=program_id,
        catalog_only=catalog_only,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    major_ids = [row.id for row in rows]
    counts_by_major = _program_counts_by_level_for_majors(db, major_ids)
    return [
        education_major_to_read(
            db,
            row,
            level_program_counts=counts_by_major.get(row.id, []),
        )
        for row in rows
    ], total


def list_education_majors_read_all(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> list[EducationMajorRead]:
    rows = list_education_majors_all(
        db,
        query=query,
        level_id=level_id,
        program_id=program_id,
        active_only=active_only,
    )
    major_ids = [row.id for row in rows]
    counts_by_major = _program_counts_by_level_for_majors(db, major_ids)
    return [
        education_major_to_read(
            db,
            row,
            level_program_counts=counts_by_major.get(row.id, []),
        )
        for row in rows
    ]


def list_active_education_majors(db: Session) -> list[EducationMajorRead]:
    return list_education_majors_read_all(db, active_only=True)


def get_education_major(db: Session, major_id: int) -> EducationMajor | None:
    return (
        db.query(EducationMajor)
        .options(joinedload(EducationMajor.program).joinedload(Program.level))
        .filter(EducationMajor.id == major_id)
        .first()
    )


def create_education_major(db: Session, payload: EducationMajorCreate) -> EducationMajorRead:
    if _major_label_exists(db, program_id=None, label=payload.label):
        raise HTTPException(
            status_code=409,
            detail="A major with this name already exists.",
        )
    code = _resolve_major_code(db, payload.code)
    record = EducationMajor(
        code=code,
        label=payload.label.strip(),
        description=(payload.description or "").strip() or None,
        program_id=None,
        sort_order=payload.sort_order,
        is_other=payload.is_other,
        is_active=payload.is_active,
        color=assign_major_color(db, label=payload.label.strip()),
    )
    db.add(record)
    db.flush()
    db.commit()
    db.refresh(record)
    return education_major_to_read(db, record)


def update_education_major(
    db: Session, major_id: int, payload: EducationMajorUpdate
) -> EducationMajorRead:
    record = get_education_major(db, major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Major not found.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("program_id", None)
    next_program_id = record.program_id
    next_label = data["label"].strip() if "label" in data and data["label"] is not None else record.label
    if _major_label_exists(
        db,
        program_id=None,
        label=next_label,
        exclude_id=major_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="A major with this name already exists.",
        )
    if "code" in data:
        if data["code"] and str(data["code"]).strip():
            code = _normalize_code(str(data["code"]))
            conflict = (
                db.query(EducationMajor)
                .filter(EducationMajor.code == code, EducationMajor.id != major_id)
                .first()
            )
            if conflict:
                raise HTTPException(status_code=409, detail="Major code already exists.")
            record.code = code
        else:
            record.code = None
    if "label" in data and data["label"] is not None:
        record.label = data["label"].strip()
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    if "is_other" in data and data["is_other"] is not None:
        record.is_other = data["is_other"]
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    ensure_major_color(db, record)
    db.commit()
    db.refresh(record)
    return education_major_to_read(db, record)


def delete_education_major(db: Session, major_id: int) -> None:
    record = get_education_major(db, major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Major not found.")
    db.delete(record)
    db.commit()


def get_education_major_by_code(db: Session, code: str) -> EducationMajor | None:
    normalized = _normalize_code(code)
    if not normalized:
        return None
    return (
        db.query(EducationMajor)
        .filter(EducationMajor.code == normalized, EducationMajor.is_active.is_(True))
        .first()
    )


def get_education_major_by_label(db: Session, label: str) -> EducationMajor | None:
    normalized = (label or "").strip()
    if not normalized:
        return None
    return (
        db.query(EducationMajor)
        .filter(EducationMajor.label == normalized, EducationMajor.is_active.is_(True))
        .first()
    )


def get_level_ids_for_major(db: Session, major_id: int) -> list[int]:
    level_ids, _ = _level_details_for_major(db, major_id)
    return level_ids
