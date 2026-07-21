from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session, joinedload

from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_course import EducationCourse
from app.models.education_major import EducationMajor
from app.models.program import Program
from app.schemas.academia_hub import CourseAdminCreate, CourseAdminUpdate
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name


def _search_pattern(query: str) -> str:
    return f"%{query.strip()}%"


def _validate_major_for_course(db: Session, education_major_id: int) -> EducationMajor:
    major = (
        db.query(EducationMajor)
        .filter(
            EducationMajor.id == education_major_id,
            EducationMajor.is_active.is_(True),
            EducationMajor.program_id.is_(None),
        )
        .first()
    )
    if not major:
        raise HTTPException(status_code=400, detail="Invalid or inactive catalog major.")
    return major


def _validate_majors_for_course(db: Session, major_ids: list[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(int(major_id) for major_id in major_ids if major_id))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="Select at least one major.")
    for major_id in unique_ids:
        _validate_major_for_course(db, major_id)
    return unique_ids


def _course_major_ids(db: Session, course_id: int) -> list[int]:
    rows = (
        db.query(CourseEducationMajorMapping.education_major_id)
        .filter(CourseEducationMajorMapping.course_id == course_id)
        .order_by(CourseEducationMajorMapping.id.asc())
        .all()
    )
    return [row.education_major_id for row in rows]


def _replace_course_major_mappings(
    db: Session, course: EducationCourse, major_ids: list[int]
) -> list[int]:
    """Replace major links for a course without NULLing FKs (uses delete-orphan)."""
    unique_ids = _validate_majors_for_course(db, major_ids)
    # Clear via relationship so SQLAlchemy issues DELETEs, not UPDATE course_id=NULL.
    course.education_major_mappings.clear()
    db.flush()
    for major_id in unique_ids:
        course.education_major_mappings.append(
            CourseEducationMajorMapping(education_major_id=major_id)
        )
    db.flush()
    return unique_ids


def _course_label_exists(
    db: Session,
    *,
    major_ids: list[int],
    label: str,
    exclude_id: int | None = None,
) -> bool:
    if not normalized_display_name(label) or not major_ids:
        return False
    # Conflict if another course already owns this label on any of the target majors
    # (via mapping rows or the legacy primary education_major_id column).
    query = db.query(EducationCourse).filter(
        or_(
            EducationCourse.education_major_id.in_(major_ids),
            exists().where(
                CourseEducationMajorMapping.course_id == EducationCourse.id,
                CourseEducationMajorMapping.education_major_id.in_(major_ids),
            ),
        )
    )
    query = filter_by_display_name(
        query,
        EducationCourse.label,
        label,
        exclude_id=exclude_id,
        id_column=EducationCourse.id,
    )
    return query.first() is not None


def _courses_query(
    db: Session,
    *,
    query: str | None = None,
    major_id: int | None = None,
    degree_id: uuid.UUID | None = None,
    level_id: int | None = None,
):
    q = db.query(EducationCourse)
    if major_id is not None:
        q = q.filter(
            or_(
                EducationCourse.education_major_id == major_id,
                exists().where(
                    CourseEducationMajorMapping.course_id == EducationCourse.id,
                    CourseEducationMajorMapping.education_major_id == major_id,
                ),
            )
        )
    if degree_id is not None:
        q = q.filter(EducationCourse.program_id == degree_id)
    if level_id is not None:
        q = q.filter(EducationCourse.level_id == level_id)
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                EducationCourse.label.ilike(pattern),
                EducationCourse.code.ilike(pattern),
                EducationCourse.course_level.ilike(pattern),
            )
        )
    return q


def _course_query_options(q):
    return q.options(
        joinedload(EducationCourse.level),
        joinedload(EducationCourse.education_major).joinedload(EducationMajor.program),
        joinedload(EducationCourse.program).joinedload(Program.level),
        joinedload(EducationCourse.education_major_mappings).joinedload(
            CourseEducationMajorMapping.education_major
        ),
    )


def get_education_course(db: Session, course_id: int) -> EducationCourse:
    record = (
        _course_query_options(db.query(EducationCourse))
        .filter(EducationCourse.id == course_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Course not found.")
    return record


def list_education_courses_admin(
    db: Session,
    *,
    query: str | None = None,
    major_id: int | None = None,
    degree_id: uuid.UUID | None = None,
    level_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationCourse], int]:
    q = _courses_query(
        db,
        query=query,
        major_id=major_id,
        degree_id=degree_id,
        level_id=level_id,
    )
    total = q.order_by(None).count()

    sort_map = {
        "name": EducationCourse.label,
        "code": EducationCourse.code,
        "level": EducationCourse.course_level,
        "id": EducationCourse.id,
        "sort_order": EducationCourse.sort_order,
    }
    sort_column = sort_map.get(sort_by, EducationCourse.label)
    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        _course_query_options(q)
        .order_by(ordered, EducationCourse.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def list_education_courses_by_program(
    db: Session,
    *,
    program_id: uuid.UUID,
    query: str | None = None,
) -> list[EducationCourse]:
    q = _courses_query(db, query=query, degree_id=program_id)
    return (
        _course_query_options(q)
        .order_by(EducationCourse.sort_order.asc(), EducationCourse.label.asc())
        .all()
    )


def create_education_course(db: Session, payload: CourseAdminCreate) -> EducationCourse:
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Course name is required to create a course.")
    major_ids = _validate_majors_for_course(db, payload.major_ids or [payload.major_id or 0])
    if _course_label_exists(db, major_ids=major_ids, label=payload.name):
        raise HTTPException(
            status_code=409,
            detail="A course with this name already exists for one of the selected majors.",
        )
    code = None
    if payload.code and payload.code.strip():
        code = payload.code.strip().upper()
        conflict = db.query(EducationCourse).filter(EducationCourse.code == code).first()
        if conflict:
            raise HTTPException(status_code=409, detail="Course code already exists.")
    record = EducationCourse(
        education_major_id=major_ids[0],
        program_id=None,
        level_id=None,
        code=code,
        label=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        course_level=None,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.flush()
    _replace_course_major_mappings(db, record, major_ids)
    db.commit()
    db.refresh(record)
    return get_education_course(db, record.id)


def update_education_course(
    db: Session, course_id: int, payload: CourseAdminUpdate
) -> EducationCourse:
    record = get_education_course(db, course_id)
    data = payload.model_dump(exclude_unset=True)
    fields_set = getattr(payload, "model_fields_set", set())

    next_major_ids = _course_major_ids(db, course_id)
    if not next_major_ids and record.education_major_id:
        next_major_ids = [int(record.education_major_id)]

    majors_provided = "major_ids" in fields_set or (
        "major_id" in fields_set and payload.major_id is not None
    )
    if "major_ids" in fields_set and payload.major_ids is not None:
        next_major_ids = list(
            dict.fromkeys(int(major_id) for major_id in payload.major_ids if major_id)
        )
    elif "major_id" in fields_set and payload.major_id is not None:
        next_major_ids = [int(payload.major_id)]

    next_label = data["name"].strip() if "name" in data and data["name"] is not None else record.label
    if next_major_ids and next_label and _course_label_exists(
        db,
        major_ids=next_major_ids,
        label=next_label,
        exclude_id=course_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="A course with this name already exists for one of the selected majors.",
        )

    if majors_provided:
        next_major_ids = _replace_course_major_mappings(db, record, next_major_ids)
        record.education_major_id = next_major_ids[0]
        record.program_id = None
        record.level_id = None

    if "name" in data and data["name"] is not None:
        record.label = data["name"].strip()
    if "code" in data:
        if data["code"] and str(data["code"]).strip():
            code = str(data["code"]).strip().upper()
            conflict = (
                db.query(EducationCourse)
                .filter(EducationCourse.code == code, EducationCourse.id != course_id)
                .first()
            )
            if conflict:
                raise HTTPException(status_code=409, detail="Course code already exists.")
            record.code = code
        else:
            record.code = None
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    db.commit()
    db.expire_all()
    return get_education_course(db, course_id)


def delete_education_course(db: Session, course_id: int) -> None:
    record = get_education_course(db, course_id)
    db.delete(record)
    db.commit()
