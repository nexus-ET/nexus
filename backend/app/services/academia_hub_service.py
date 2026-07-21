from __future__ import annotations

import re
import uuid
from typing import Any, Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy import func, or_, union_all
from sqlalchemy.orm import Session, joinedload

from app.models.academia_geography import GeographyCity, GeographyState
from app.models.academia_institution import Campus, CampusType, College, Institution
from app.models.country import Country
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_major import EducationMajor
from app.models.education_course import EducationCourse
from app.models.target_course import TargetCourse
from app.models.target_program import TargetProgram
from app.services.name_uniqueness import filter_by_display_name, normalized_display_name
from app.services.education_courses import (
    create_education_course,
    delete_education_course,
    get_education_course,
    list_education_courses_admin,
    list_education_courses_by_program,
    update_education_course,
)
from app.schemas.academia_hub import (
    AcademiaSearchResult,
    CampusCreate,
    CampusUpdate,
    CollegeCreate,
    CollegeUpdate,
    CountryAdminCreate,
    CountryAdminUpdate,
    CourseAdminCreate,
    CourseAdminUpdate,
    DegreeAdminCreate,
    DegreeAdminUpdate,
    AcademicHierarchySummary,
    HierarchyCourseNode,
    HierarchyLevelNode,
    HierarchyMajorNode,
    HierarchyProgramNode,
    GeographyCityCreate,
    GeographyCityUpdate,
    GeographyStateCreate,
    GeographyStateUpdate,
    InstitutionCreate,
    InstitutionUpdate,
    InstitutionalHierarchySummary,
    InstitutionHierarchyCampusNode,
    InstitutionHierarchyCollegeNode,
    InstitutionHierarchyNode,
    ProgramAdminCreate,
    ProgramAdminUpdate,
)

T = TypeVar("T")


def _apply_updates(record: T, payload: Any, fields: list[str]) -> T:
    data = payload.model_dump(exclude_unset=True)
    for field in fields:
        if field in data:
            setattr(record, field, data[field])
    return record


def _search_pattern(query: str) -> str:
    return f"%{query.strip()}%"


def _validate_city_hierarchy(
    db: Session,
    *,
    country_id: int,
    state_id: int,
) -> GeographyState:
    get_country_admin(db, country_id)
    state = get_state_admin(db, state_id)
    if state.country_id != country_id:
        raise HTTPException(
            status_code=400,
            detail="State does not belong to the selected country.",
        )
    return state


# --- Countries ---


def list_countries_admin(
    db: Session,
    *,
    query: str | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[Country], int]:
    q = db.query(Country)
    if active_only:
        q = q.filter(Country.is_active.is_(True))
    if query:
        pattern = _search_pattern(query)
        q = q.filter(or_(Country.name.ilike(pattern), Country.iso2.ilike(pattern)))

    total = q.order_by(None).count()
    sort_map = {
        "name": Country.name,
        "iso2": Country.iso2,
        "dial_code": Country.dial_code,
        "sort_order": Country.sort_order,
        "is_active": Country.is_active,
        "id": Country.id,
    }
    sort_column = sort_map.get(sort_by, Country.name)
    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, Country.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_country_admin(db: Session, country_id: int) -> Country:
    record = db.query(Country).filter(Country.id == country_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Country not found.")
    return record


def create_country_admin(db: Session, payload: CountryAdminCreate) -> Country:
    existing = db.query(Country).filter(Country.iso2 == payload.iso2.upper()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Country ISO code already exists.")
    record = Country(
        iso2=payload.iso2.upper(),
        name=payload.name.strip(),
        dial_code=payload.dial_code.strip(),
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_country_admin(db: Session, country_id: int, payload: CountryAdminUpdate) -> Country:
    record = get_country_admin(db, country_id)
    data = payload.model_dump(exclude_unset=True)
    if "iso2" in data and data["iso2"]:
        data["iso2"] = data["iso2"].upper()
        conflict = (
            db.query(Country)
            .filter(Country.iso2 == data["iso2"], Country.id != country_id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Country ISO code already exists.")
    _apply_updates(record, payload, ["iso2", "name", "dial_code", "is_active", "sort_order"])
    db.commit()
    db.refresh(record)
    return record


def delete_country_admin(db: Session, country_id: int) -> None:
    record = get_country_admin(db, country_id)
    db.delete(record)
    db.commit()


# --- States ---


def list_states_admin(
    db: Session,
    *,
    query: str | None = None,
    country_id: int | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[GeographyState], int]:
    q = db.query(GeographyState).options(joinedload(GeographyState.country))
    if country_id is not None:
        q = q.filter(GeographyState.country_id == country_id)
    if active_only:
        q = q.filter(GeographyState.is_active.is_(True))
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                GeographyState.name.ilike(pattern),
                GeographyState.region_code.ilike(pattern),
            )
        )

    total = q.order_by(None).count()
    sort_map = {
        "name": GeographyState.name,
        "region_code": GeographyState.region_code,
        "sort_order": GeographyState.sort_order,
        "is_active": GeographyState.is_active,
        "id": GeographyState.id,
    }
    if sort_by == "country":
        q = q.join(Country, Country.id == GeographyState.country_id)
        sort_column = Country.name
    else:
        sort_column = sort_map.get(sort_by, GeographyState.name)
    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, GeographyState.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_state_admin(db: Session, state_id: int) -> GeographyState:
    record = (
        db.query(GeographyState)
        .options(joinedload(GeographyState.country))
        .filter(GeographyState.id == state_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="State not found.")
    return record


def create_state_admin(db: Session, payload: GeographyStateCreate) -> GeographyState:
    get_country_admin(db, payload.country_id)
    record = GeographyState(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_state_admin(db, record.id)


def update_state_admin(db: Session, state_id: int, payload: GeographyStateUpdate) -> GeographyState:
    record = get_state_admin(db, state_id)
    data = payload.model_dump(exclude_unset=True)
    if "country_id" in data and data["country_id"] is not None:
        get_country_admin(db, data["country_id"])
    _apply_updates(record, payload, ["country_id", "name", "region_code", "is_active", "sort_order"])
    db.commit()
    return get_state_admin(db, state_id)


def delete_state_admin(db: Session, state_id: int) -> None:
    record = get_state_admin(db, state_id)
    db.delete(record)
    db.commit()


# --- Cities ---


def list_cities_admin(
    db: Session,
    *,
    query: str | None = None,
    country_id: int | None = None,
    state_id: int | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[GeographyCity], int]:
    q = db.query(GeographyCity).options(
        joinedload(GeographyCity.country), joinedload(GeographyCity.state)
    )
    if country_id is not None:
        q = q.filter(GeographyCity.country_id == country_id)
    if state_id is not None:
        q = q.filter(GeographyCity.state_id == state_id)
    if active_only:
        q = q.filter(GeographyCity.is_active.is_(True))
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                GeographyCity.name.ilike(pattern),
                GeographyCity.time_zone.ilike(pattern),
                GeographyCity.postal_code_prefix.ilike(pattern),
            )
        )

    total = q.order_by(None).count()
    sort_map = {
        "name": GeographyCity.name,
        "time_zone": GeographyCity.time_zone,
        "sort_order": GeographyCity.sort_order,
        "is_active": GeographyCity.is_active,
        "id": GeographyCity.id,
    }
    if sort_by == "country":
        q = q.join(Country, Country.id == GeographyCity.country_id)
        sort_column = Country.name
    elif sort_by == "state":
        q = q.join(GeographyState, GeographyState.id == GeographyCity.state_id)
        sort_column = GeographyState.name
    else:
        sort_column = sort_map.get(sort_by, GeographyCity.name)
    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, GeographyCity.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_city_admin(db: Session, city_id: int) -> GeographyCity:
    record = (
        db.query(GeographyCity)
        .options(joinedload(GeographyCity.country), joinedload(GeographyCity.state))
        .filter(GeographyCity.id == city_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="City not found.")
    return record


def create_city_admin(db: Session, payload: GeographyCityCreate) -> GeographyCity:
    _validate_city_hierarchy(db, country_id=payload.country_id, state_id=payload.state_id)
    record = GeographyCity(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_city_admin(db, record.id)


def update_city_admin(db: Session, city_id: int, payload: GeographyCityUpdate) -> GeographyCity:
    record = get_city_admin(db, city_id)
    data = payload.model_dump(exclude_unset=True)
    country_id = data.get("country_id", record.country_id)
    state_id = data.get("state_id", record.state_id)
    if "country_id" in data or "state_id" in data:
        _validate_city_hierarchy(db, country_id=country_id, state_id=state_id)
    _apply_updates(
        record,
        payload,
        [
            "country_id",
            "state_id",
            "name",
            "time_zone",
            "postal_code_prefix",
            "is_active",
            "sort_order",
        ],
    )
    db.commit()
    return get_city_admin(db, city_id)


def delete_city_admin(db: Session, city_id: int) -> None:
    record = get_city_admin(db, city_id)
    db.delete(record)
    db.commit()


# --- Institutions ---


def _city_location_label(city: GeographyCity | None) -> str | None:
    if not city:
        return None
    parts = [city.name]
    if city.state:
        parts.append(city.state.name)
    if city.country:
        parts.append(city.country.name)
    return ", ".join(parts)


def _institution_campus_count(db: Session, institution_id: int) -> int:
    count = db.query(Campus).filter(Campus.institution_id == institution_id).count()
    if count == 0:
        from app.services import institution_wizard_service as wizard_service

        wizard_service.reconcile_institution_hierarchy_from_draft(db, institution_id)
        count = db.query(Campus).filter(Campus.institution_id == institution_id).count()
    return count


def _institution_college_count(db: Session, institution_id: int) -> int:
    count = db.query(College).filter(College.institution_id == institution_id).count()
    if count == 0:
        from app.services import institution_wizard_service as wizard_service

        wizard_service.reconcile_institution_hierarchy_from_draft(db, institution_id)
        count = db.query(College).filter(College.institution_id == institution_id).count()
    return count


def get_institution_status_counts(db: Session) -> tuple[int, int]:
    active_count = db.query(Institution).filter(Institution.is_active.is_(True)).count()
    inactive_count = db.query(Institution).filter(Institution.is_active.is_(False)).count()
    return active_count, inactive_count


def list_institutions_admin(db: Session, *, query: str | None = None) -> list[Institution]:
    q = (
        db.query(Institution)
        .options(joinedload(Institution.country))
        .order_by(Institution.sort_order.asc(), Institution.name.asc())
    )
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                Institution.name.ilike(pattern),
                Institution.code.ilike(pattern),
                Institution.institution_type.ilike(pattern),
                Institution.accreditation_details.ilike(pattern),
            )
        )
    return q.all()


def _institution_wizard_payload(db: Session, institution_id: int) -> dict[str, Any]:
    from app.models.academia_wizard import InstitutionWizardDraft

    # Prefer an in-progress draft, otherwise the richest recent published payload so
    # level/program/major/course summary metrics survive after publish.
    drafts = (
        db.query(InstitutionWizardDraft)
        .filter(InstitutionWizardDraft.institution_id == institution_id)
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .all()
    )
    if not drafts:
        return {}

    def _score(draft: InstitutionWizardDraft) -> tuple[int, int, int]:
        payload = draft.payload or {}
        courses = payload.get("courses") or []
        return (
            1 if draft.status == "draft" else 0,
            1 if courses else 0,
            len(courses),
        )

    drafts.sort(key=_score, reverse=True)
    return drafts[0].payload or {}


def _college_scoped_payload_courses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Wizard college mappings are stored with college_local_id, not legacy college_id."""
    courses = payload.get("courses") or []
    return [
        item
        for item in courses
        if isinstance(item, dict)
        and str(item.get("college_local_id") or "").strip()
    ]


def _institution_college_scoped_academics_courses(
    db: Session, institution_id: int
) -> list[dict[str, Any]]:
    from app.models.academia_wizard import InstitutionWizardDraft

    drafts = (
        db.query(InstitutionWizardDraft)
        .filter(InstitutionWizardDraft.institution_id == institution_id)
        .order_by(InstitutionWizardDraft.updated_at.desc())
        .all()
    )

    best: list[dict[str, Any]] = []
    best_score = (-1, -1)
    for draft in drafts:
        linked = _college_scoped_payload_courses(draft.payload or {})
        score = (len(linked), 1 if draft.status == "published" else 0)
        if score > best_score:
            best = linked
            best_score = score
    return best


def _draft_course_catalog_counts(
    db: Session, payload: dict[str, Any]
) -> tuple[int, int, int]:
    courses = _college_scoped_payload_courses(payload)
    if not courses:
        return 0, 0, 0

    level_ids: set[int] = set()
    program_ids: set[str] = set()
    major_ids: set[int] = set()
    for course in courses:
        level_id = course.get("level_id")
        program_id = course.get("program_id")
        major_id = course.get("major_id")
        if level_id:
            level_ids.add(int(level_id))
        if program_id:
            program_ids.add(str(program_id))
        if major_id:
            major_ids.add(int(major_id))

    major_count = 0
    if major_ids:
        rows = (
            db.query(EducationMajor.label)
            .filter(EducationMajor.id.in_(major_ids))
            .all()
        )
        major_count = len(
            {row[0].strip().lower() for row in rows if row[0] and str(row[0]).strip()}
        )
        if major_count == 0:
            major_count = len(major_ids)

    return len(level_ids), len(program_ids), major_count


def _institution_level_count(db: Session, institution_id: int) -> int:
    payload = {
        "courses": _institution_college_scoped_academics_courses(db, institution_id)
    }
    level_count, _, _ = _draft_course_catalog_counts(db, payload)
    return level_count


def _institution_program_count(db: Session, institution_id: int) -> int:
    payload = {
        "courses": _institution_college_scoped_academics_courses(db, institution_id)
    }
    _, program_count, _ = _draft_course_catalog_counts(db, payload)
    return program_count


def _institution_major_count(db: Session, institution_id: int) -> int:
    payload = {
        "courses": _institution_college_scoped_academics_courses(db, institution_id)
    }
    _, _, major_count = _draft_course_catalog_counts(db, payload)
    return major_count


def _institution_course_count(db: Session, institution_id: int) -> int:
    courses = _institution_college_scoped_academics_courses(db, institution_id)
    course_ids = {
        int(item.get("course_id"))
        for item in courses
        if item.get("course_id") and int(item.get("course_id")) > 0
    }
    return len(course_ids)


def _institution_intake_count(db: Session, institution_id: int) -> int:
    from app.models.academia_wizard import InstitutionIntake

    count = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.entity_type.isnot(None),
        )
        .count()
    )
    if count > 0:
        return count

    # Legacy rows without entity_type (pre-hierarchy / publish orphans)
    legacy = (
        db.query(InstitutionIntake)
        .filter(InstitutionIntake.institution_id == institution_id)
        .count()
    )
    if legacy > 0:
        return legacy

    payload = _institution_wizard_payload(db, institution_id)
    return len(payload.get("intakes") or [])


def _institution_picture_count(db: Session, institution_id: int) -> int:
    from app.models.academia_wizard import InstitutionPicture

    count = (
        db.query(InstitutionPicture)
        .filter(InstitutionPicture.institution_id == institution_id)
        .count()
    )
    if count > 0:
        return count

    payload = _institution_wizard_payload(db, institution_id)
    return len(payload.get("pictures") or [])


def _campus_count_sort_subq(db: Session):
    return (
        db.query(
            Campus.institution_id.label("institution_id"),
            func.count(Campus.id).label("metric"),
        )
        .group_by(Campus.institution_id)
        .subquery("campus_count_sort")
    )


def _college_count_sort_subq(db: Session):
    return (
        db.query(
            College.institution_id.label("institution_id"),
            func.count(College.id).label("metric"),
        )
        .group_by(College.institution_id)
        .subquery("college_count_sort")
    )


def _intake_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionIntake

    return (
        db.query(
            InstitutionIntake.institution_id.label("institution_id"),
            func.count(InstitutionIntake.id).label("metric"),
        )
        .group_by(InstitutionIntake.institution_id)
        .subquery("intake_count_sort")
    )


def _picture_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionPicture

    return (
        db.query(
            InstitutionPicture.institution_id.label("institution_id"),
            func.count(InstitutionPicture.id).label("metric"),
        )
        .group_by(InstitutionPicture.institution_id)
        .subquery("picture_count_sort")
    )


def _program_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(func.distinct(TargetCourse.qualification_program_id)).label("metric"),
        )
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            TargetCourse.qualification_program_id.isnot(None),
        )
        .group_by(InstitutionCourseOffering.institution_id)
        .subquery("program_count_sort")
    )


def _major_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(func.distinct(func.lower(func.trim(EducationMajor.label)))).label("metric"),
        )
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(EducationMajor, TargetCourse.education_major_id == EducationMajor.id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            EducationMajor.label.isnot(None),
        )
        .group_by(InstitutionCourseOffering.institution_id)
        .subquery("major_count_sort")
    )


def _course_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(func.distinct(InstitutionCourseOffering.course_id)).label("metric"),
        )
        .filter(InstitutionCourseOffering.is_active.is_(True))
        .group_by(InstitutionCourseOffering.institution_id)
        .subquery("course_count_sort")
    )


def _level_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    via_qualification = (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            Program.level_id.label("level_id"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(Program, TargetCourse.qualification_program_id == Program.id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            Program.level_id.isnot(None),
        )
    )
    via_major = (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            Program.level_id.label("level_id"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(EducationMajor, TargetCourse.education_major_id == EducationMajor.id)
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.education_major_id == EducationMajor.id,
        )
        .join(Program, Program.id == ProgramEducationMajorMapping.program_id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            Program.level_id.isnot(None),
        )
    )
    level_pairs = union_all(via_qualification, via_major).subquery("level_pairs")
    return (
        db.query(
            level_pairs.c.institution_id.label("institution_id"),
            func.count(func.distinct(level_pairs.c.level_id)).label("metric"),
        )
        .group_by(level_pairs.c.institution_id)
        .subquery("level_count_sort")
    )


_COUNT_SORT_SUBQUERIES = {
    "campus_count": _campus_count_sort_subq,
    "college_count": _college_count_sort_subq,
    "intake_count": _intake_count_sort_subq,
    "program_count": _program_count_sort_subq,
    "major_count": _major_count_sort_subq,
    "course_count": _course_count_sort_subq,
}


def list_institutions_summary_admin(
    db: Session,
    *,
    query: str | None = None,
    country_id: int | None = None,
    state_id: int | None = None,
    city_id: int | None = None,
    is_active: bool | None = None,
    institution_type: str | None = None,
    program_id: uuid.UUID | None = None,
    major_id: int | None = None,
    template_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Institution], int]:
    from app.models.academia_wizard import InstitutionCourseOffering

    q = db.query(Institution).options(
        joinedload(Institution.country),
        joinedload(Institution.state),
        joinedload(Institution.city),
    )

    if query:
        pattern = _search_pattern(query)
        q = q.filter(Institution.name.ilike(pattern))

    if country_id is not None:
        q = q.filter(Institution.country_id == country_id)
    if state_id is not None:
        q = q.filter(Institution.state_id == state_id)
    if city_id is not None:
        q = q.filter(Institution.city_id == city_id)
    if is_active is not None:
        q = q.filter(Institution.is_active.is_(is_active))
    if institution_type:
        q = q.filter(Institution.institution_type == institution_type)

    if program_id is not None or major_id is not None:
        offering_q = (
            db.query(InstitutionCourseOffering.institution_id)
            .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
            .filter(InstitutionCourseOffering.is_active.is_(True))
        )
        if program_id is not None:
            offering_q = offering_q.filter(TargetCourse.qualification_program_id == program_id)
        if major_id is not None:
            offering_q = offering_q.filter(TargetCourse.education_major_id == major_id)
        matching_ids = [row[0] for row in offering_q.distinct().all()]
        if not matching_ids:
            return [], 0
        q = q.filter(Institution.id.in_(matching_ids))

    if template_id is not None:
        from app.models.academia_wizard import InstitutionIntake

        matching_ids = [
            row[0]
            for row in db.query(InstitutionIntake.institution_id)
            .filter(InstitutionIntake.template_id == template_id)
            .distinct()
            .all()
        ]
        if not matching_ids:
            return [], 0
        q = q.filter(Institution.id.in_(matching_ids))

    total = q.order_by(None).count()

    sort_map = {
        "name": Institution.name,
        "created_at": Institution.created_at,
        "code": Institution.code,
        "institution_type": Institution.institution_type,
        "status": Institution.is_active,
        "sort_order": Institution.sort_order,
        "id": Institution.id,
    }

    if sort_by in _COUNT_SORT_SUBQUERIES:
        subq = _COUNT_SORT_SUBQUERIES[sort_by](db)
        q = q.outerjoin(subq, Institution.id == subq.c.institution_id)
        sort_column = func.coalesce(subq.c.metric, 0)
    elif sort_by == "country":
        q = q.outerjoin(Country, Country.id == Institution.country_id)
        sort_column = Country.name
    elif sort_by == "state":
        q = q.outerjoin(GeographyState, GeographyState.id == Institution.state_id)
        sort_column = GeographyState.name
    elif sort_by == "city":
        q = q.outerjoin(GeographyCity, GeographyCity.id == Institution.city_id)
        sort_column = GeographyCity.name
    else:
        sort_column = sort_map.get(sort_by, Institution.created_at)

    ordered = sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, Institution.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_institution_admin(db: Session, institution_id: int) -> Institution:
    record = (
        db.query(Institution)
        .options(joinedload(Institution.country))
        .filter(Institution.id == institution_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Institution not found.")
    return record


def create_institution_admin(db: Session, payload: InstitutionCreate) -> Institution:
    if payload.country_id is not None:
        get_country_admin(db, payload.country_id)
    if payload.state_id is not None:
        get_state_admin(db, payload.state_id)
    if payload.city_id is not None:
        get_city_admin(db, payload.city_id)
    record = Institution(**payload.model_dump(), publish_status="pending")
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_institution_admin(db, record.id)


def update_institution_admin(db: Session, institution_id: int, payload: InstitutionUpdate) -> Institution:
    record = get_institution_admin(db, institution_id)
    data = payload.model_dump(exclude_unset=True)
    if "country_id" in data and data["country_id"] is not None:
        get_country_admin(db, data["country_id"])
    if "state_id" in data and data["state_id"] is not None:
        get_state_admin(db, data["state_id"])
    if "city_id" in data and data["city_id"] is not None:
        get_city_admin(db, data["city_id"])
    _apply_updates(
        record,
        payload,
        [
            "country_id",
            "state_id",
            "city_id",
            "zipcode",
            "address",
            "phone_numbers",
            "fax_numbers",
            "email_addresses",
            "name",
            "code",
            "dean_name",
            "institution_type",
            "company_affiliated",
            "ranking_tier_global",
            "ad_promotion_flag",
            "institution_web_url",
            "web_links",
            "currency_type",
            "students_count",
            "accreditation_details",
            "short_description",
            "long_description",
            "is_active",
            "sort_order",
        ],
    )
    db.commit()
    return get_institution_admin(db, institution_id)


def delete_institution_admin(db: Session, institution_id: int) -> None:
    """Delete an institution and all institution-scoped dependent rows.

    DB FKs use NO ACTION, so ORM relationship cascades alone are not enough —
    intakes, pictures, offerings, drafts, and alert logs must be removed first.
    """
    from app.models.academia_wizard import (
        InstitutionCourseOffering,
        InstitutionIntake,
        InstitutionPicture,
        InstitutionWizardDraft,
    )
    from app.models.calendar_intake_alert import CalendarIntakeAlertLog

    record = get_institution_admin(db, institution_id)

    # Remove Cloudflare R2 / local uploads before the DB row disappears so the
    # institution prefix (code/name slug) is still available.
    from app.services.institution_asset_storage import delete_all_institution_assets

    try:
        delete_all_institution_assets(record)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to delete institution media assets: {exc}",
        ) from exc

    db.query(CalendarIntakeAlertLog).filter(
        CalendarIntakeAlertLog.institution_id == institution_id
    ).delete(synchronize_session=False)

    # Break self-referential intake parent links before deleting the rows.
    db.query(InstitutionIntake).filter(
        InstitutionIntake.institution_id == institution_id
    ).update({InstitutionIntake.parent_intake_id: None}, synchronize_session=False)
    db.query(InstitutionIntake).filter(
        InstitutionIntake.institution_id == institution_id
    ).delete(synchronize_session=False)

    db.query(InstitutionCourseOffering).filter(
        InstitutionCourseOffering.institution_id == institution_id
    ).delete(synchronize_session=False)
    db.query(InstitutionPicture).filter(
        InstitutionPicture.institution_id == institution_id
    ).delete(synchronize_session=False)
    db.query(InstitutionWizardDraft).filter(
        InstitutionWizardDraft.institution_id == institution_id
    ).delete(synchronize_session=False)

    # Colleges reference campuses; clear campus links then delete both.
    db.query(College).filter(College.institution_id == institution_id).update(
        {College.campus_id: None}, synchronize_session=False
    )
    db.query(College).filter(College.institution_id == institution_id).delete(
        synchronize_session=False
    )
    db.query(Campus).filter(Campus.institution_id == institution_id).delete(
        synchronize_session=False
    )

    db.delete(record)
    db.commit()


def get_institutional_hierarchy_summary(db: Session) -> InstitutionalHierarchySummary:
    institutions = (
        db.query(Institution)
        .order_by(Institution.sort_order.asc(), Institution.name.asc())
        .all()
    )
    nodes: list[InstitutionHierarchyNode] = []
    for institution in institutions:
        campuses = (
            db.query(Campus)
            .options(
                joinedload(Campus.location).joinedload(GeographyCity.state),
                joinedload(Campus.location).joinedload(GeographyCity.country),
            )
            .filter(Campus.institution_id == institution.id)
            .order_by(Campus.sort_order.asc(), Campus.name.asc())
            .all()
        )
        campus_nodes: list[InstitutionHierarchyCampusNode] = []
        for campus in campuses:
            colleges = (
                db.query(College)
                .filter(College.campus_id == campus.id)
                .order_by(College.sort_order.asc(), College.name.asc())
                .all()
            )
            campus_nodes.append(
                InstitutionHierarchyCampusNode(
                    id=campus.id,
                    name=campus.name,
                    location_label=_city_location_label(campus.location),
                    colleges=[
                        InstitutionHierarchyCollegeNode(
                            id=college.id,
                            name=college.name,
                            dean_name=college.dean_name,
                        )
                        for college in colleges
                    ],
                )
            )
        nodes.append(
            InstitutionHierarchyNode(
                id=institution.id,
                name=institution.name,
                accreditation_details=institution.accreditation_details,
                campuses=campus_nodes,
            )
        )
    return InstitutionalHierarchySummary(institutions=nodes)


# --- Campus types ---


def list_campus_types_admin(db: Session) -> list[CampusType]:
    return db.query(CampusType).order_by(CampusType.id.asc()).all()


def get_campus_type_admin(db: Session, campus_type_id: int) -> CampusType:
    record = db.query(CampusType).filter(CampusType.id == campus_type_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Campus type not found.")
    return record


# --- Campuses ---


def list_campuses_admin(
    db: Session,
    *,
    query: str | None = None,
    institution_id: int | None = None,
) -> list[Campus]:
    q = (
        db.query(Campus)
        .options(
            joinedload(Campus.institution),
            joinedload(Campus.campus_type_ref),
            joinedload(Campus.location).joinedload(GeographyCity.state),
            joinedload(Campus.location).joinedload(GeographyCity.country),
        )
        .order_by(Campus.sort_order.asc(), Campus.name.asc())
    )
    if institution_id is not None:
        q = q.filter(Campus.institution_id == institution_id)
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                Campus.name.ilike(pattern),
                Campus.city.ilike(pattern),
            )
        )
    return q.all()


def get_campus_admin(db: Session, campus_id: int) -> Campus:
    record = (
        db.query(Campus)
        .options(
            joinedload(Campus.institution),
            joinedload(Campus.campus_type_ref),
            joinedload(Campus.location).joinedload(GeographyCity.state),
            joinedload(Campus.location).joinedload(GeographyCity.country),
        )
        .filter(Campus.id == campus_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Campus not found.")
    return record


def create_campus_admin(db: Session, payload: CampusCreate) -> Campus:
    get_institution_admin(db, payload.institution_id)
    get_city_admin(db, payload.location_id)
    if payload.campus_type_id is not None:
        get_campus_type_admin(db, payload.campus_type_id)
    record = Campus(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_campus_admin(db, record.id)


def update_campus_admin(db: Session, campus_id: int, payload: CampusUpdate) -> Campus:
    record = get_campus_admin(db, campus_id)
    data = payload.model_dump(exclude_unset=True)
    if "institution_id" in data and data["institution_id"] is not None:
        get_institution_admin(db, data["institution_id"])
    if "location_id" in data and data["location_id"] is not None:
        get_city_admin(db, data["location_id"])
    if "campus_type_id" in data and data["campus_type_id"] is not None:
        get_campus_type_admin(db, data["campus_type_id"])
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    return get_campus_admin(db, campus_id)


def delete_campus_admin(db: Session, campus_id: int) -> None:
    record = get_campus_admin(db, campus_id)
    db.delete(record)
    db.commit()


# --- Colleges ---


def list_colleges_admin(
    db: Session,
    *,
    query: str | None = None,
    institution_id: int | None = None,
    campus_id: int | None = None,
) -> list[College]:
    q = (
        db.query(College)
        .options(joinedload(College.institution), joinedload(College.campus))
        .order_by(College.sort_order.asc(), College.name.asc())
    )
    if institution_id is not None:
        q = q.filter(College.institution_id == institution_id)
    if campus_id is not None:
        q = q.filter(College.campus_id == campus_id)
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                College.name.ilike(pattern),
                College.dean_name.ilike(pattern),
            )
        )
    return q.all()


def get_college_admin(db: Session, college_id: int) -> College:
    record = (
        db.query(College)
        .options(
            joinedload(College.institution),
            joinedload(College.campus).joinedload(Campus.location),
            joinedload(College.campus).joinedload(Campus.state),
            joinedload(College.campus).joinedload(Campus.country),
        )
        .filter(College.id == college_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="College not found.")
    return record


def create_college_admin(db: Session, payload: CollegeCreate) -> College:
    get_institution_admin(db, payload.institution_id)
    if payload.campus_id is not None:
        campus = get_campus_admin(db, payload.campus_id)
        if campus.institution_id != payload.institution_id:
            raise HTTPException(
                status_code=400,
                detail="Campus does not belong to the selected institution.",
            )
    record = College(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_college_admin(db, record.id)


def update_college_admin(db: Session, college_id: int, payload: CollegeUpdate) -> College:
    record = get_college_admin(db, college_id)
    data = payload.model_dump(exclude_unset=True)
    institution_id = data.get("institution_id", record.institution_id)
    campus_id = data.get("campus_id", record.campus_id)
    if "institution_id" in data and data["institution_id"] is not None:
        get_institution_admin(db, data["institution_id"])
    if "campus_id" in data and data["campus_id"] is not None:
        campus = get_campus_admin(db, data["campus_id"])
        if institution_id is not None and campus.institution_id != institution_id:
            raise HTTPException(
                status_code=400,
                detail="Campus does not belong to the selected institution.",
            )
        campus_id = data["campus_id"]
    if institution_id is not None and campus_id is not None:
        campus = get_campus_admin(db, campus_id)
        if campus.institution_id != institution_id:
            raise HTTPException(
                status_code=400,
                detail="College must map to a campus under the selected institution.",
            )
    _apply_updates(
        record,
        payload,
        [
            "institution_id",
            "campus_id",
            "name",
            "code",
            "category",
            "dean_name",
            "web_url",
            "web_links",
            "phone_numbers",
            "email_addresses",
            "is_active",
            "sort_order",
        ],
    )
    db.commit()
    return get_college_admin(db, college_id)


def delete_college_admin(db: Session, college_id: int) -> None:
    record = get_college_admin(db, college_id)
    db.delete(record)
    db.commit()


# --- Qualification programs (programs table; API path still /degrees) ---


def _slugify_degree_code(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().upper()).strip("_")
    return (slug or "DEGREE")[:50]


def _unique_degree_code(db: Session, base_code: str) -> str:
    code = base_code[:50]
    if not db.query(Program).filter(Program.code == code).first():
        return code
    suffix = 2
    while suffix < 1000:
        candidate = f"{base_code[:45]}_{suffix}"
        if not db.query(Program).filter(Program.code == candidate).first():
            return candidate
        suffix += 1
    raise HTTPException(status_code=409, detail="Could not generate a unique program code.")


def _program_name_exists(
    db: Session,
    *,
    level_id: int,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    if not normalized_display_name(name):
        return False
    query = filter_by_display_name(
        db.query(Program).filter(Program.level_id == level_id),
        Program.name,
        name,
        exclude_id=exclude_id,
        id_column=Program.id,
    )
    return query.first() is not None


def _degree_program_count(db: Session, program_id: uuid.UUID) -> int:
    return db.query(TargetProgram).filter(TargetProgram.program_id == program_id).count()


def _degree_major_details(db: Session, program_id: uuid.UUID) -> tuple[int, list[str]]:
    mappings = (
        db.query(ProgramEducationMajorMapping)
        .options(joinedload(ProgramEducationMajorMapping.education_major))
        .filter(ProgramEducationMajorMapping.program_id == program_id)
        .order_by(ProgramEducationMajorMapping.id.asc())
        .all()
    )
    labels = [
        mapping.education_major.label
        for mapping in mappings
        if mapping.education_major and mapping.education_major.is_active
    ]
    return len(labels), labels


def _degree_major_count(db: Session, program_id: uuid.UUID) -> int:
    return (
        db.query(ProgramEducationMajorMapping)
        .join(EducationMajor, EducationMajor.id == ProgramEducationMajorMapping.education_major_id)
        .filter(
            ProgramEducationMajorMapping.program_id == program_id,
            EducationMajor.is_active.is_(True),
        )
        .count()
    )


def get_degree_admin(db: Session, program_id: uuid.UUID) -> Program:
    record = (
        db.query(Program)
        .options(joinedload(Program.level))
        .filter(Program.id == program_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Program not found.")
    return record


def list_degrees_admin(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    active_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[Program], int]:
    from app.models.level import Level

    q = db.query(Program).options(joinedload(Program.level))
    if active_only:
        q = q.filter(Program.is_active.is_(True))
    if level_id is not None:
        q = q.filter(Program.level_id == level_id)
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                Program.name.ilike(pattern),
                Program.code.ilike(pattern),
                Program.description.ilike(pattern),
            )
        )

    total = q.order_by(None).count()

    sort_map = {
        "name": Program.name,
        "code": Program.code,
        "sort_order": Program.sort_order,
        "id": Program.id,
    }
    if sort_by == "level":
        q = q.join(Level, Level.id == Program.level_id)
        sort_column = Level.name
    else:
        sort_column = sort_map.get(sort_by, Program.name)

    ordered = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = (
        q.order_by(ordered, Program.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def list_degrees_admin_all(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    active_only: bool = False,
) -> list[Program]:
    rows, _ = list_degrees_admin(
        db,
        query=query,
        level_id=level_id,
        active_only=active_only,
        page=1,
        page_size=10_000,
    )
    return rows


def _degree_major_ids(db: Session, program_id: uuid.UUID) -> list[int]:
    rows = (
        db.query(ProgramEducationMajorMapping.education_major_id)
        .filter(ProgramEducationMajorMapping.program_id == program_id)
        .order_by(ProgramEducationMajorMapping.id.asc())
        .all()
    )
    return [row.education_major_id for row in rows]


def _replace_program_major_mappings(
    db: Session, program_id: uuid.UUID, major_ids: list[int]
) -> None:
    unique_ids = list(dict.fromkeys(int(major_id) for major_id in major_ids if major_id))
    if unique_ids:
        majors = (
            db.query(EducationMajor)
            .filter(
                EducationMajor.id.in_(unique_ids),
                EducationMajor.is_active.is_(True),
                EducationMajor.program_id.is_(None),
            )
            .all()
        )
        found_ids = {major.id for major in majors}
        missing = [major_id for major_id in unique_ids if major_id not in found_ids]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid or inactive catalog major(s): {', '.join(str(i) for i in missing)}",
            )

    db.query(ProgramEducationMajorMapping).filter(
        ProgramEducationMajorMapping.program_id == program_id
    ).delete(synchronize_session=False)

    for major_id in unique_ids:
        db.add(
            ProgramEducationMajorMapping(
                program_id=program_id,
                education_major_id=major_id,
            )
        )


def create_degree_admin(db: Session, payload: DegreeAdminCreate) -> Program:
    from app.services.academic_calendar_service import (
        replace_program_intake_assignments,
        validate_program_intake_assignments,
    )
    from app.services.levels import get_level

    if not get_level(db, payload.level_id):
        raise HTTPException(status_code=400, detail="Invalid level.")
    validate_program_intake_assignments(
        db,
        program_id=None,
        institution_id=payload.institution_id,
        intake_ids=payload.intake_ids,
        is_active=payload.is_active,
    )
    if _program_name_exists(db, level_id=payload.level_id, name=payload.name):
        raise HTTPException(
            status_code=409,
            detail="A program with this name already exists for the selected level.",
        )
    base_code = (payload.code or _slugify_degree_code(payload.name)).upper()
    code = _unique_degree_code(db, base_code)
    record = Program(
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        level_id=payload.level_id,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.flush()
    _replace_program_major_mappings(db, record.id, payload.major_ids)
    replace_program_intake_assignments(
        db,
        record.id,
        payload.institution_id,
        payload.intake_ids,
    )
    db.commit()
    db.refresh(record)
    return get_degree_admin(db, record.id)


def update_degree_admin(db: Session, program_id: uuid.UUID, payload: DegreeAdminUpdate) -> Program:
    from app.services.academic_calendar_service import (
        get_program_intake_ids,
        replace_program_intake_assignments,
        validate_program_intake_assignments,
    )

    record = get_degree_admin(db, program_id)
    data = payload.model_dump(exclude_unset=True)
    institution_id = data.pop("institution_id", None)
    intake_ids = data.pop("intake_ids", None)
    major_ids_provided = "major_ids" in getattr(payload, "model_fields_set", set()) or "major_ids" in data
    major_ids = data.pop("major_ids", None) if major_ids_provided else None
    if major_ids_provided and major_ids is None:
        major_ids = []
    next_level_id = data["level_id"] if "level_id" in data and data["level_id"] is not None else record.level_id
    next_name = data["name"].strip() if "name" in data and data["name"] is not None else record.name
    if _program_name_exists(
        db,
        level_id=next_level_id,
        name=next_name,
        exclude_id=program_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="A program with this name already exists for the selected level.",
        )
    if "name" in data and data["name"] is not None:
        record.name = data["name"].strip()
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "code" in data and data["code"]:
        conflict = (
            db.query(Program)
            .filter(Program.code == data["code"], Program.id != program_id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Program code already exists.")
        record.code = data["code"]
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    if "level_id" in data and data["level_id"] is not None:
        from app.services.levels import get_level

        if not get_level(db, data["level_id"]):
            raise HTTPException(status_code=400, detail="Invalid level.")
        record.level_id = data["level_id"]

    resolved_institution_id = institution_id
    resolved_intake_ids = intake_ids if intake_ids is not None else get_program_intake_ids(db, program_id)
    if resolved_institution_id is None and resolved_intake_ids:
        from app.models.academia_wizard import InstitutionIntake

        resolved_institution_id = (
            db.query(InstitutionIntake.institution_id)
            .filter(InstitutionIntake.id == resolved_intake_ids[0])
            .scalar()
        )

    validate_program_intake_assignments(
        db,
        program_id=program_id,
        institution_id=resolved_institution_id,
        intake_ids=resolved_intake_ids,
        is_active=record.is_active,
    )
    if institution_id is not None or intake_ids is not None:
        replace_program_intake_assignments(
            db,
            program_id,
            resolved_institution_id,
            resolved_intake_ids,
        )
    if major_ids is not None:
        _replace_program_major_mappings(db, program_id, major_ids)
    db.commit()
    db.refresh(record)
    return get_degree_admin(db, program_id)


def delete_degree_admin(db: Session, program_id: uuid.UUID) -> None:
    record = get_degree_admin(db, program_id)
    db.delete(record)
    db.commit()


def get_academic_hierarchy_summary(db: Session) -> AcademicHierarchySummary:
    from app.models.level import Level

    levels = (
        db.query(Level)
        .order_by(Level.id.asc())
        .all()
    )
    level_nodes: list[HierarchyLevelNode] = []

    for level in levels:
        programs = (
            db.query(Program)
            .filter(Program.level_id == level.id, Program.is_active.is_(True))
            .order_by(Program.sort_order.asc(), Program.name.asc())
            .all()
        )
        program_nodes: list[HierarchyProgramNode] = []
        for program in programs:
            mappings = (
                db.query(ProgramEducationMajorMapping)
                .options(joinedload(ProgramEducationMajorMapping.education_major))
                .filter(ProgramEducationMajorMapping.program_id == program.id)
                .order_by(ProgramEducationMajorMapping.id.asc())
                .all()
            )
            major_nodes: list[HierarchyMajorNode] = []
            for mapping in mappings:
                if not mapping.education_major or not mapping.education_major.is_active:
                    continue
                major = mapping.education_major
                major_courses = (
                    db.query(EducationCourse)
                    .join(
                        CourseEducationMajorMapping,
                        CourseEducationMajorMapping.course_id == EducationCourse.id,
                    )
                    .filter(
                        CourseEducationMajorMapping.education_major_id == major.id,
                        EducationCourse.is_active.is_(True),
                    )
                    .order_by(EducationCourse.sort_order.asc(), EducationCourse.label.asc())
                    .all()
                )
                major_nodes.append(
                    HierarchyMajorNode(
                        id=major.id,
                        name=major.label,
                        courses=[
                            HierarchyCourseNode(
                                id=course.id,
                                name=course.label,
                                code=course.code,
                            )
                            for course in major_courses
                        ],
                    )
                )
            program_nodes.append(
                HierarchyProgramNode(
                    id=str(program.id),
                    name=program.name,
                    majors=major_nodes,
                )
            )
        level_nodes.append(
            HierarchyLevelNode(id=level.id, name=level.name, programs=program_nodes)
        )

    return AcademicHierarchySummary(levels=level_nodes)


# --- Programs ---


def _slugify_program_code(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().upper()).strip("_")
    return (slug or "PROGRAM")[:50]


def _unique_program_code(db: Session, base_code: str) -> str:
    code = base_code[:50]
    if not db.query(TargetProgram).filter(TargetProgram.code == code).first():
        return code
    suffix = 2
    while suffix < 1000:
        candidate = f"{base_code[:45]}_{suffix}"
        if not db.query(TargetProgram).filter(TargetProgram.code == candidate).first():
            return candidate
        suffix += 1
    raise HTTPException(status_code=409, detail="Could not generate a unique program code.")


def _validate_course_level(level: str | None) -> str | None:
    if level is None or not str(level).strip():
        return None
    normalized = str(level).strip()
    if normalized not in COURSE_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid course level. Allowed values: {', '.join(COURSE_LEVELS)}.",
        )
    return normalized


def _program_course_count(db: Session, program_id: int) -> int:
    return db.query(TargetCourse).filter(TargetCourse.program_id == program_id).count()


def list_programs_admin(
    db: Session,
    *,
    query: str | None = None,
    degree_id: uuid.UUID | None = None,
    level_id: int | None = None,
) -> list[TargetProgram]:
    q = (
        db.query(TargetProgram)
        .options(joinedload(TargetProgram.program).joinedload(Program.level))
        .order_by(TargetProgram.sort_order.asc(), TargetProgram.label.asc())
    )
    if degree_id is not None:
        q = q.filter(TargetProgram.program_id == degree_id)
    if level_id is not None:
        q = q.join(Program).filter(Program.level_id == level_id)
    if query:
        pattern = _search_pattern(query)
        q = q.filter(
            or_(
                TargetProgram.label.ilike(pattern),
                TargetProgram.code.ilike(pattern),
                TargetProgram.description.ilike(pattern),
            )
        )
    return q.all()


def get_program_admin(db: Session, program_id: int) -> TargetProgram:
    record = (
        db.query(TargetProgram)
        .options(joinedload(TargetProgram.program).joinedload(Program.level))
        .filter(TargetProgram.id == program_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Program not found.")
    return record


def create_program_admin(db: Session, payload: ProgramAdminCreate) -> TargetProgram:
    get_degree_admin(db, payload.program_id)
    base_code = (payload.code or _slugify_program_code(payload.name)).upper()
    code = _unique_program_code(db, base_code)
    record = TargetProgram(
        program_id=payload.program_id,
        code=code,
        label=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return get_program_admin(db, record.id)


def update_program_admin(db: Session, program_id: int, payload: ProgramAdminUpdate) -> TargetProgram:
    record = get_program_admin(db, program_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        record.label = data["name"].strip()
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "program_id" in data and data["program_id"] is not None:
        get_degree_admin(db, data["program_id"])
        record.program_id = data["program_id"]
    if "code" in data and data["code"]:
        conflict = (
            db.query(TargetProgram)
            .filter(TargetProgram.code == data["code"], TargetProgram.id != program_id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Program code already exists.")
        record.code = data["code"]
    if "is_active" in data and data["is_active"] is not None:
        record.is_active = data["is_active"]
    if "sort_order" in data and data["sort_order"] is not None:
        record.sort_order = data["sort_order"]
    db.commit()
    db.refresh(record)
    return record


def delete_program_admin(db: Session, program_id: int) -> None:
    record = get_program_admin(db, program_id)
    db.delete(record)
    db.commit()


# --- Courses ---


def _resolve_target_program_for_education_major(
    db: Session, *, degree_id: uuid.UUID, education_major_id: int
) -> TargetProgram:
    get_degree_admin(db, degree_id)
    major = db.query(EducationMajor).filter(EducationMajor.id == education_major_id).first()
    if not major:
        raise HTTPException(status_code=404, detail="Major not found.")

    existing = (
        db.query(TargetProgram)
        .filter(
            TargetProgram.program_id == degree_id,
            or_(
                TargetProgram.code == major.code,
                TargetProgram.label == major.label,
            ),
        )
        .first()
    )
    if existing:
        return existing

    code = _unique_program_code(db, major.code)
    record = TargetProgram(
        program_id=degree_id,
        code=code,
        label=major.label,
        is_active=True,
        sort_order=major.sort_order,
    )
    db.add(record)
    db.flush()
    return record


def list_courses_admin(
    db: Session,
    *,
    query: str | None = None,
    program_id: int | None = None,
    major_id: int | None = None,
    degree_id: uuid.UUID | None = None,
    level_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[EducationCourse], int]:
    if program_id is not None and degree_id is None:
        target_program = get_program_admin(db, program_id)
        degree_id = target_program.program_id
    return list_education_courses_admin(
        db,
        query=query,
        major_id=major_id,
        degree_id=degree_id,
        level_id=level_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


def list_courses_admin_all(
    db: Session,
    *,
    query: str | None = None,
    program_id: int | None = None,
    major_id: int | None = None,
    degree_id: uuid.UUID | None = None,
    level_id: int | None = None,
) -> list[EducationCourse]:
    if program_id is not None and degree_id is None:
        target_program = get_program_admin(db, program_id)
        degree_id = target_program.program_id
    if degree_id is not None:
        return list_education_courses_by_program(db, program_id=degree_id, query=query)
    rows, _ = list_education_courses_admin(
        db,
        query=query,
        major_id=major_id,
        degree_id=degree_id,
        level_id=level_id,
        page=1,
        page_size=10_000,
    )
    return rows


def get_course_admin(db: Session, course_id: int) -> EducationCourse:
    return get_education_course(db, course_id)


def create_course_admin(db: Session, payload: CourseAdminCreate) -> EducationCourse:
    return create_education_course(db, payload)


def update_course_admin(db: Session, course_id: int, payload: CourseAdminUpdate) -> EducationCourse:
    return update_education_course(db, course_id, payload)


def delete_course_admin(db: Session, course_id: int) -> None:
    delete_education_course(db, course_id)


# --- Global search ---


def search_academia_entities(db: Session, query: str, *, limit: int = 25) -> list[AcademiaSearchResult]:
    pattern = _search_pattern(query)
    if not query.strip():
        return []

    results: list[AcademiaSearchResult] = []

    def add_results(
        rows: list[Any],
        *,
        entity_type: str,
        entity_label: str,
        category: str,
        path_prefix: str,
        title_getter: Callable[[Any], str],
        subtitle_getter: Callable[[Any], str | None],
    ) -> None:
        for row in rows:
            if len(results) >= limit:
                return
            results.append(
                AcademiaSearchResult(
                    entity_type=entity_type,
                    entity_label=entity_label,
                    category=category,
                    id=row.id,
                    title=title_getter(row),
                    subtitle=subtitle_getter(row),
                    path=f"{path_prefix}/{row.id}",
                )
            )

    countries = (
        db.query(Country)
        .filter(or_(Country.name.ilike(pattern), Country.iso2.ilike(pattern)))
        .order_by(Country.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        countries,
        entity_type="countries",
        entity_label="Country",
        category="Geography",
        path_prefix="/academia/geography/countries",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: row.iso2,
    )

    states = (
        db.query(GeographyState)
        .options(joinedload(GeographyState.country))
        .filter(
            or_(
                GeographyState.name.ilike(pattern),
                GeographyState.region_code.ilike(pattern),
            )
        )
        .order_by(GeographyState.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        states,
        entity_type="states",
        entity_label="State",
        category="Geography",
        path_prefix="/academia/geography/states",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: row.country.name if row.country else None,
    )

    cities = (
        db.query(GeographyCity)
        .options(joinedload(GeographyCity.country), joinedload(GeographyCity.state))
        .filter(GeographyCity.name.ilike(pattern))
        .order_by(GeographyCity.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        cities,
        entity_type="cities",
        entity_label="City",
        category="Geography",
        path_prefix="/academia/geography/cities",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: row.state.name if row.state else (row.country.name if row.country else None),
    )

    institutions = (
        db.query(Institution)
        .options(joinedload(Institution.country))
        .filter(or_(Institution.name.ilike(pattern), Institution.code.ilike(pattern)))
        .order_by(Institution.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        institutions,
        entity_type="institutions",
        entity_label="Institution",
        category="Institutions",
        path_prefix="/academia/institutions/institutions",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: row.country.name if row.country else row.code,
    )

    campuses = (
        db.query(Campus)
        .options(
            joinedload(Campus.institution),
            joinedload(Campus.campus_type_ref),
            joinedload(Campus.location).joinedload(GeographyCity.state),
            joinedload(Campus.location).joinedload(GeographyCity.country),
        )
        .filter(or_(Campus.name.ilike(pattern), Campus.city.ilike(pattern)))
        .order_by(Campus.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        campuses,
        entity_type="campuses",
        entity_label="Campus",
        category="Institutions",
        path_prefix="/academia/institutions/campuses",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: (
            row.institution.name
            if row.institution
            else (_city_location_label(row.location) if row.location else row.city)
        ),
    )

    colleges = (
        db.query(College)
        .options(joinedload(College.institution), joinedload(College.campus))
        .filter(College.name.ilike(pattern))
        .order_by(College.name.asc())
        .limit(limit)
        .all()
    )
    add_results(
        colleges,
        entity_type="colleges",
        entity_label="College",
        category="Institutions",
        path_prefix="/academia/institutions/colleges",
        title_getter=lambda row: row.name,
        subtitle_getter=lambda row: row.institution.name if row.institution else (row.campus.name if row.campus else None),
    )

    degrees = (
        db.query(Program)
        .filter(
            or_(
                Program.name.ilike(pattern),
                Program.code.ilike(pattern),
                Program.description.ilike(pattern),
            )
        )
        .order_by(Program.name.asc())
        .limit(limit)
        .all()
    )
    for row in degrees:
        if len(results) >= limit:
            break
        results.append(
            AcademiaSearchResult(
                entity_type="degrees",
                entity_label="Degree",
                category="Academic Framework",
                id=row.id,
                title=row.name,
                subtitle=row.code,
                path="/academia/framework/degrees",
            )
        )
    if len(results) >= limit:
        return results[:limit]

    programs = (
        db.query(TargetProgram)
        .filter(
            or_(
                TargetProgram.label.ilike(pattern),
                TargetProgram.code.ilike(pattern),
                TargetProgram.description.ilike(pattern),
            )
        )
        .order_by(TargetProgram.label.asc())
        .limit(limit)
        .all()
    )
    for row in programs:
        if len(results) >= limit:
            break
        results.append(
            AcademiaSearchResult(
                entity_type="programs",
                entity_label="Program",
                category="Academic Framework",
                id=row.id,
                title=row.label,
                subtitle=row.code,
                path=f"/academia/framework/programs/{row.id}",
            )
        )
    if len(results) >= limit:
        return results[:limit]

    courses = (
        db.query(EducationCourse)
        .options(
            joinedload(EducationCourse.program),
            joinedload(EducationCourse.education_major),
        )
        .filter(or_(EducationCourse.label.ilike(pattern), EducationCourse.code.ilike(pattern)))
        .order_by(EducationCourse.label.asc())
        .limit(limit)
        .all()
    )
    add_results(
        courses,
        entity_type="courses",
        entity_label="Course",
        category="Academic Framework",
        path_prefix="/academia/framework/courses",
        title_getter=lambda row: row.label,
        subtitle_getter=lambda row: row.program.name if row.program else row.code,
    )

    return results[:limit]
