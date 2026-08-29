from __future__ import annotations

import uuid

from fastapi import HTTPException
from collections import defaultdict

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.education_major import EducationMajor
from app.models.education_major_level import EducationMajorLevel
from app.models.education_sub_major import EducationSubMajor
from app.models.education_super_major import EducationSuperMajor
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


def _get_super_major(db: Session, super_major_id: int) -> EducationSuperMajor:
    record = (
        db.query(EducationSuperMajor)
        .filter(EducationSuperMajor.id == super_major_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="Invalid super-major.")
    return record


def _major_label_exists(
    db: Session,
    *,
    program_id: int | None,
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


def _get_program(db: Session, program_id: int) -> Program:
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


def _sub_major_counts_for_majors(db: Session, major_ids: list[int]) -> dict[int, int]:
    if not major_ids:
        return {}
    rows = (
        db.query(EducationSubMajor.major_id, func.count(EducationSubMajor.id))
        .filter(EducationSubMajor.major_id.in_(major_ids))
        .group_by(EducationSubMajor.major_id)
        .all()
    )
    return {int(major_id): int(count) for major_id, count in rows}


def education_major_to_read(
    db: Session,
    record: EducationMajor,
    *,
    level_program_counts: list[MajorLevelProgramCount] | None = None,
    sub_major_count: int | None = None,
) -> EducationMajorRead:
    level_ids, level_names = _level_details_for_major(db, record.id)
    if level_program_counts is None:
        level_program_counts = _program_counts_by_level_for_major(db, record.id)
    if sub_major_count is None:
        sub_major_count = _sub_major_counts_for_majors(db, [record.id]).get(record.id, 0)
    program = record.program
    if record.program_id and not program:
        program = _get_program(db, record.program_id)
    super_major = record.super_major
    return EducationMajorRead(
        id=record.id,
        code=record.code,
        label=record.label,
        major_description=record.major_description,
        sub_majors_key_fields=record.sub_majors_key_fields,
        program_id=record.program_id,
        program_name=program.name if program else None,
        super_major_id=record.super_major_id,
        super_major_name=super_major.name if super_major else None,
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
        sub_major_count=sub_major_count,
    )


def seed_education_majors(db: Session) -> None:
    """Disabled — majors are managed only via Academia Hub UI, not startup seeds."""
    return


def list_education_majors(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: int | None = None,
    super_major_id: int | None = None,
    catalog_only: bool = True,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationMajor], int]:
    q = db.query(EducationMajor).options(
        joinedload(EducationMajor.program).joinedload(Program.level),
        joinedload(EducationMajor.super_major),
    )
    if active_only:
        q = q.filter(EducationMajor.is_active.is_(True))
    if catalog_only and program_id is None:
        q = q.filter(EducationMajor.program_id.is_(None))
    if program_id is not None:
        q = q.filter(EducationMajor.program_id == program_id)
    if super_major_id is not None:
        q = q.filter(EducationMajor.super_major_id == super_major_id)
    if level_id is not None:
        q = q.join(Program, Program.id == EducationMajor.program_id).filter(
            Program.level_id == level_id
        )
    if query:
        pattern = f"%{query.strip()}%"
        q = q.outerjoin(
            EducationSuperMajor,
            EducationSuperMajor.id == EducationMajor.super_major_id,
        ).filter(
            or_(
                EducationMajor.label.ilike(pattern),
                EducationMajor.code.ilike(pattern),
                EducationMajor.major_description.ilike(pattern),
                EducationMajor.sub_majors_key_fields.ilike(pattern),
                EducationSuperMajor.name.ilike(pattern),
            )
        )

    total = q.order_by(None).count()

    sort_map = {
        "name": EducationMajor.label,
        "code": EducationMajor.code,
        "sort_order": EducationMajor.sort_order,
        "id": EducationMajor.id,
        "super_major": EducationSuperMajor.name,
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
    elif sort_by == "super_major":
        if query is None or not query.strip():
            q = q.outerjoin(
                EducationSuperMajor,
                EducationSuperMajor.id == EducationMajor.super_major_id,
            )
        sort_column = EducationSuperMajor.name
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
    program_id: int | None = None,
    super_major_id: int | None = None,
    active_only: bool = True,
) -> list[EducationMajor]:
    rows, _ = list_education_majors(
        db,
        query=query,
        level_id=level_id,
        program_id=program_id,
        super_major_id=super_major_id,
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
    program_id: int | None = None,
    super_major_id: int | None = None,
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
        super_major_id=super_major_id,
        catalog_only=catalog_only,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    major_ids = [row.id for row in rows]
    counts_by_major = _program_counts_by_level_for_majors(db, major_ids)
    sub_counts = _sub_major_counts_for_majors(db, major_ids)
    return [
        education_major_to_read(
            db,
            row,
            level_program_counts=counts_by_major.get(row.id, []),
            sub_major_count=sub_counts.get(row.id, 0),
        )
        for row in rows
    ], total


def list_education_majors_read_all(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    program_id: int | None = None,
    super_major_id: int | None = None,
    active_only: bool = True,
) -> list[EducationMajorRead]:
    rows = list_education_majors_all(
        db,
        query=query,
        level_id=level_id,
        program_id=program_id,
        super_major_id=super_major_id,
        active_only=active_only,
    )
    major_ids = [row.id for row in rows]
    counts_by_major = _program_counts_by_level_for_majors(db, major_ids)
    sub_counts = _sub_major_counts_for_majors(db, major_ids)
    return [
        education_major_to_read(
            db,
            row,
            level_program_counts=counts_by_major.get(row.id, []),
            sub_major_count=sub_counts.get(row.id, 0),
        )
        for row in rows
    ]


def list_active_education_majors(db: Session) -> list[EducationMajorRead]:
    return list_education_majors_read_all(db, active_only=True)


def get_education_major(db: Session, major_id: int) -> EducationMajor | None:
    return (
        db.query(EducationMajor)
        .options(
            joinedload(EducationMajor.program).joinedload(Program.level),
            joinedload(EducationMajor.super_major),
        )
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
    super_major_id = None
    if payload.super_major_id is not None:
        _get_super_major(db, payload.super_major_id)
        super_major_id = payload.super_major_id
    record = EducationMajor(
        code=code,
        label=payload.label.strip(),
        major_description=(payload.major_description or "").strip() or None,
        sub_majors_key_fields=(payload.sub_majors_key_fields or "").strip() or None,
        program_id=None,
        super_major_id=super_major_id,
        sort_order=payload.sort_order,
        is_other=payload.is_other,
        is_active=payload.is_active,
        color=assign_major_color(db, label=payload.label.strip()),
    )
    db.add(record)
    db.flush()
    db.commit()
    db.refresh(record)
    loaded = get_education_major(db, record.id)
    return education_major_to_read(db, loaded or record)


def update_education_major(
    db: Session, major_id: int, payload: EducationMajorUpdate
) -> EducationMajorRead:
    record = get_education_major(db, major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Major not found.")
    data = payload.model_dump(exclude_unset=True)
    data.pop("program_id", None)
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
    if "major_description" in data:
        record.major_description = (data["major_description"] or "").strip() or None
    if "sub_majors_key_fields" in data:
        record.sub_majors_key_fields = (
            (data["sub_majors_key_fields"] or "").strip() or None
        )
    if "super_major_id" in data:
        if data["super_major_id"] is None:
            record.super_major_id = None
        else:
            _get_super_major(db, data["super_major_id"])
            record.super_major_id = data["super_major_id"]
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    if "is_other" in data and data["is_other"] is not None:
        record.is_other = data["is_other"]
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    ensure_major_color(db, record)
    db.commit()
    db.refresh(record)
    loaded = get_education_major(db, record.id)
    return education_major_to_read(db, loaded or record)


def delete_education_major(db: Session, major_id: int) -> None:
    from app.models.education_sub_major import EducationSubMajor

    record = get_education_major(db, major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Major not found.")
    sub_count = (
        db.query(EducationSubMajor)
        .filter(EducationSubMajor.major_id == major_id)
        .count()
    )
    if sub_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete this major because "
                f"{sub_count} sub-major{'s' if sub_count != 1 else ''} still reference it."
            ),
        )
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
