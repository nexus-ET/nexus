from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, load_only, selectinload

from app.models.academia_geography import GeographyCity, GeographyState
from app.models.academia_institution import (
    Campus,
    CampusType,
    College,
    CollegeCampus,
    Institution,
    InstitutionType,
)
from app.models.country import Country
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
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
    FrameworkCountryCoverage,
    FrameworkCoverageMetrics,
    FrameworkCoveragePair,
    FrameworkInstitutionCoverage,
    HierarchyCourseNode,
    HierarchyLevelNode,
    HierarchyMajorNode,
    HierarchyProgramNode,
    GeographyCityCreate,
    GeographyCityUpdate,
    GeographyStateCreate,
    GeographyStateUpdate,
    INSTITUTION_PROFILE_TEXT_FIELD_NAMES,
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
logger = logging.getLogger(__name__)


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
    with_institutions: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> tuple[list[Country], int]:
    q = db.query(Country)
    if with_institutions:
        q = q.filter(
            exists().where(
                Institution.country_id == Country.id,
            )
        )
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
    rows = (
        db.query(Institution.is_active, func.count(Institution.id))
        .group_by(Institution.is_active)
        .all()
    )
    tally = {bool(is_active): int(count or 0) for is_active, count in rows}
    return tally.get(True, 0), tally.get(False, 0)


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
                InstitutionType.name.ilike(pattern),
                Institution.accreditation_details.ilike(pattern),
            )
        ).outerjoin(InstitutionType, Institution.institution_type_id == InstitutionType.id)
    return q.all()


def _college_scoped_payload_courses(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Wizard college mappings are stored with college_local_id, not legacy college_id."""
    courses = payload.get("courses") or []
    return [
        item
        for item in courses
        if isinstance(item, dict)
        and str(item.get("college_local_id") or "").strip()
    ]


INSTITUTION_METRIC_KEYS = (
    "campus_count",
    "college_count",
    "level_count",
    "program_count",
    "major_count",
    "sub_major_count",
    "course_count",
    "intake_count",
    "picture_count",
)


def _empty_institution_metrics() -> dict[str, int]:
    return {key: 0 for key in INSTITUTION_METRIC_KEYS}


def _best_college_scoped_courses(
    drafts: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Richest college-linked course set across an institution's drafts, published last."""
    best: list[dict[str, Any]] = []
    best_score = (-1, -1)
    for status, payload in drafts:
        linked = _college_scoped_payload_courses(payload)
        score = (len(linked), 1 if status == "published" else 0)
        if score > best_score:
            best = linked
            best_score = score
    return best


def _best_wizard_payload(drafts: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Prefer an in-progress draft, else the richest published payload, so intake and
    picture fallbacks survive a publish."""
    if not drafts:
        return {}

    def _score(entry: tuple[str, dict[str, Any]]) -> tuple[int, int, int]:
        status, payload = entry
        courses = payload.get("courses") or []
        return (
            1 if status == "draft" else 0,
            1 if courses else 0,
            len(courses),
        )

    return max(drafts, key=_score)[1]


def _grouped_institution_counts(db: Session, model, ids: Sequence[int]) -> dict[int, int]:
    return {
        row[0]: int(row[1] or 0)
        for row in db.query(model.institution_id, func.count(model.id))
        .filter(model.institution_id.in_(ids))
        .group_by(model.institution_id)
        .all()
    }


CatalogSets = tuple[set[int], set[str], set[int], set[int]]


def _empty_catalog_sets() -> CatalogSets:
    return (set(), set(), set(), set())


def accumulate_offering_catalog_row(
    catalog: dict[int, CatalogSets],
    institution_id: int,
    *,
    program_id: Any,
    course_id: Any,
    major_id: Any,
    level_id: Any,
) -> None:
    """Fold one offering/program join row into distinct catalog id sets."""
    level_ids, program_ids, major_ids, course_ids = catalog.setdefault(
        int(institution_id), _empty_catalog_sets()
    )
    if level_id is not None:
        level_ids.add(int(level_id))
    if program_id is not None:
        program_ids.add(str(program_id))
    if major_id is not None:
        major_ids.add(int(major_id))
    if course_id is not None:
        course_ids.add(int(course_id))


def _education_course_join():
    """Match an offering's target_course to a real Academic Framework course."""
    return and_(
        EducationCourse.program_id == TargetCourse.qualification_program_id,
        EducationCourse.code == TargetCourse.code,
        EducationCourse.code.isnot(None),
        EducationCourse.is_active.is_(True),
    )


def _mapped_course_id_expr():
    """Course id counted on the Institutions list.

    `institution_course_offerings.course_id` is required, so program–institution
    links were stored by cloning each program into `target_courses` (same code).
    Those placeholders are not courses. Count:
    - matching `education_courses`, or
    - `target_courses` whose code is not a 1:1 clone of the parent program.
    """
    from app.models.academia_wizard import InstitutionCourseOffering

    is_real_course = or_(
        EducationCourse.id.isnot(None),
        Program.id.is_(None),
        TargetCourse.code.is_distinct_from(Program.code),
    )
    return case(
        (
            is_real_course,
            func.coalesce(EducationCourse.id, InstitutionCourseOffering.course_id),
        ),
        else_=None,
    )


def _education_course_ids_in(db: Session, course_ids: set[int]) -> set[int]:
    if not course_ids:
        return set()
    return {
        int(row[0])
        for row in db.query(EducationCourse.id).filter(
            EducationCourse.id.in_(list(course_ids))
        )
    }


def _sub_major_metrics_subquery(db: Session, ids: Sequence[int]):
    """Distinct mapped sub-majors per institution via active offerings.

    Join mappings on ``target_courses.qualification_program_id`` (programs.id),
    not ``target_courses.id``. Count only non-null ``education_sub_major_id``.
    """
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(
                func.distinct(ProgramEducationMajorMapping.education_sub_major_id)
            ).label("sub_major_count"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(
            ProgramEducationMajorMapping,
            and_(
                ProgramEducationMajorMapping.program_id
                == TargetCourse.qualification_program_id,
                ProgramEducationMajorMapping.education_sub_major_id.isnot(None),
            ),
        )
        .filter(
            InstitutionCourseOffering.institution_id.in_(list(ids)),
            InstitutionCourseOffering.is_active.is_(True),
        )
        .group_by(InstitutionCourseOffering.institution_id)
        .subquery("sub_major_metrics")
    )


def _offering_catalog_metrics_query(db: Session, ids: Sequence[int]):
    """GROUP BY institution_id — never pull offering rows into Python."""
    from app.models.academia_wizard import InstitutionCourseOffering

    nonempty_label = and_(
        EducationMajor.label.isnot(None),
        func.trim(EducationMajor.label) != "",
    )
    major_label_expr = case(
        (nonempty_label, func.lower(func.trim(EducationMajor.label))),
        else_=None,
    )
    sub_major_metrics = _sub_major_metrics_subquery(db, ids)
    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(func.distinct(Program.level_id)).label("level_count"),
            func.count(func.distinct(TargetCourse.qualification_program_id)).label(
                "program_count"
            ),
            func.count(func.distinct(TargetCourse.education_major_id)).label(
                "major_id_count"
            ),
            func.count(func.distinct(major_label_expr)).label("major_label_count"),
            func.coalesce(func.max(sub_major_metrics.c.sub_major_count), 0).label(
                "sub_major_count"
            ),
            func.count(func.distinct(_mapped_course_id_expr())).label("course_count"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .outerjoin(Program, TargetCourse.qualification_program_id == Program.id)
        .outerjoin(EducationCourse, _education_course_join())
        .outerjoin(EducationMajor, TargetCourse.education_major_id == EducationMajor.id)
        .outerjoin(
            sub_major_metrics,
            sub_major_metrics.c.institution_id
            == InstitutionCourseOffering.institution_id,
        )
        .filter(
            InstitutionCourseOffering.institution_id.in_(list(ids)),
            InstitutionCourseOffering.is_active.is_(True),
        )
        .group_by(InstitutionCourseOffering.institution_id)
    )


def _mapping_major_metrics_query(db: Session, ids: Sequence[int]):
    from app.models.academia_wizard import InstitutionCourseOffering

    nonempty_label = and_(
        EducationMajor.label.isnot(None),
        func.trim(EducationMajor.label) != "",
    )
    major_label_expr = case(
        (nonempty_label, func.lower(func.trim(EducationMajor.label))),
        else_=None,
    )
    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(
                func.distinct(ProgramEducationMajorMapping.education_major_id)
            ).label("major_id_count"),
            func.count(func.distinct(major_label_expr)).label("major_label_count"),
            func.count(
                func.distinct(ProgramEducationMajorMapping.education_sub_major_id)
            ).label("sub_major_count"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.program_id
            == TargetCourse.qualification_program_id,
        )
        .outerjoin(
            EducationMajor,
            ProgramEducationMajorMapping.education_major_id == EducationMajor.id,
        )
        .filter(
            InstitutionCourseOffering.institution_id.in_(list(ids)),
            InstitutionCourseOffering.is_active.is_(True),
        )
        .group_by(InstitutionCourseOffering.institution_id)
    )


def _live_offering_catalog_counts(
    db: Session, ids: Sequence[int]
) -> dict[int, dict[str, int]]:
    """Distinct catalog counts via one aggregated offerings join per page."""
    empty = {
        "level_count": 0,
        "program_count": 0,
        "major_count": 0,
        "sub_major_count": 0,
        "course_count": 0,
    }
    catalog = {int(i): dict(empty) for i in ids}
    if not ids:
        return catalog

    rows = _offering_catalog_metrics_query(db, ids).all()
    missing_majors: list[int] = []
    for row in rows:
        institution_id = int(row.institution_id)
        program_count = int(row.program_count or 0)
        major_id_count = int(row.major_id_count or 0)
        major_label_count = int(row.major_label_count or 0)
        catalog[institution_id] = {
            "level_count": int(row.level_count or 0),
            "program_count": program_count,
            "major_count": major_label_count or major_id_count,
            "sub_major_count": int(row.sub_major_count or 0),
            "course_count": int(row.course_count or 0),
        }
        if program_count and not major_id_count:
            missing_majors.append(institution_id)

    mapping_rows = _mapping_major_metrics_query(db, ids).all()
    mapping_by_id = {int(row.institution_id): row for row in mapping_rows}
    for institution_id, row in mapping_by_id.items():
        catalog[institution_id]["sub_major_count"] = int(row.sub_major_count or 0)
    for institution_id in missing_majors:
        row = mapping_by_id.get(institution_id)
        if row is None:
            continue
        catalog[institution_id]["major_count"] = int(
            row.major_label_count or row.major_id_count or 0
        )

    return catalog


def _page_entity_counts(
    db: Session, ids: Sequence[int]
) -> dict[str, dict[int, int]]:
    """Campus/college/picture/intake counts in one UNION ALL round trip."""
    from app.models.academia_wizard import InstitutionIntake, InstitutionPicture

    empty: dict[str, dict[int, int]] = {
        "campus": {},
        "college": {},
        "picture": {},
        "intake": {},
        "intake_entity": {},
    }
    if not ids:
        return empty

    campus_q = (
        db.query(
            literal("campus").label("kind"),
            Campus.institution_id.label("institution_id"),
            func.count(Campus.id).label("metric"),
        )
        .filter(Campus.institution_id.in_(ids))
        .group_by(Campus.institution_id)
    )
    college_q = (
        db.query(
            literal("college").label("kind"),
            College.institution_id.label("institution_id"),
            func.count(College.id).label("metric"),
        )
        .filter(College.institution_id.in_(ids))
        .group_by(College.institution_id)
    )
    picture_q = (
        db.query(
            literal("picture").label("kind"),
            InstitutionPicture.institution_id.label("institution_id"),
            func.count(InstitutionPicture.id).label("metric"),
        )
        .filter(InstitutionPicture.institution_id.in_(ids))
        .group_by(InstitutionPicture.institution_id)
    )
    intake_q = (
        db.query(
            literal("intake").label("kind"),
            InstitutionIntake.institution_id.label("institution_id"),
            func.count(InstitutionIntake.id).label("metric"),
        )
        .filter(InstitutionIntake.institution_id.in_(ids))
        .group_by(InstitutionIntake.institution_id)
    )
    intake_entity_q = (
        db.query(
            literal("intake_entity").label("kind"),
            InstitutionIntake.institution_id.label("institution_id"),
            func.count(InstitutionIntake.entity_type).label("metric"),
        )
        .filter(InstitutionIntake.institution_id.in_(ids))
        .group_by(InstitutionIntake.institution_id)
    )
    combined = campus_q.union_all(college_q, picture_q, intake_q, intake_entity_q)
    for kind, institution_id, metric in combined.all():
        empty[str(kind)][int(institution_id)] = int(metric or 0)
    return empty


def institution_hierarchy_counts(
    db: Session,
    institution_ids: Sequence[int],
    *,
    draft_backed_ids: set[int] | None = None,
    repair_from_drafts: bool = True,
) -> dict[int, tuple[int, int]]:
    """Campus/college counts for many institutions, optionally repairing draft-backed gaps."""
    from app.models.academia_wizard import InstitutionWizardDraft

    ids = list(dict.fromkeys(int(value) for value in institution_ids))
    if not ids:
        return {}

    campus_counts = _grouped_institution_counts(db, Campus, ids)
    college_counts = _grouped_institution_counts(db, College, ids)

    incomplete = [
        institution_id
        for institution_id in ids
        if not campus_counts.get(institution_id) or not college_counts.get(institution_id)
    ]
    if incomplete and repair_from_drafts:
        if draft_backed_ids is None:
            draft_backed_ids = {
                row[0]
                for row in db.query(InstitutionWizardDraft.institution_id)
                .filter(
                    InstitutionWizardDraft.institution_id.in_(incomplete),
                    InstitutionWizardDraft.status == "draft",
                )
                .distinct()
                .all()
            }
        # The single-row helpers repaired missing hierarchy rows from an in-progress
        # draft on read; keep that behaviour, but skip institutions with no draft.
        needs_reconcile = [i for i in incomplete if i in draft_backed_ids]
        if needs_reconcile:
            from app.services import institution_wizard_service as wizard_service

            for institution_id in needs_reconcile:
                wizard_service.reconcile_institution_hierarchy_from_draft(db, institution_id)
            campus_counts = _grouped_institution_counts(db, Campus, ids)
            college_counts = _grouped_institution_counts(db, College, ids)

    return {
        institution_id: (
            campus_counts.get(institution_id, 0),
            college_counts.get(institution_id, 0),
        )
        for institution_id in ids
    }


def institution_summary_metrics(
    db: Session, institution_ids: Sequence[int]
) -> dict[int, dict[str, int]]:
    """Resolve list counters for a page of institutions in a few grouped queries.

    Does not load offering rows into Python and does not reconcile wizard drafts
    (list GET must stay read-only and fast when live offerings already exist).
    """
    from app.models.academia_wizard import InstitutionWizardDraft

    ids = list(dict.fromkeys(int(value) for value in institution_ids))
    metrics: dict[int, dict[str, int]] = {
        institution_id: _empty_institution_metrics() for institution_id in ids
    }
    if not ids:
        return metrics

    catalog = _live_offering_catalog_counts(db, ids)
    entity_counts = _page_entity_counts(db, ids)

    need_draft_payload: list[int] = []
    for institution_id in ids:
        live = catalog[institution_id]
        if live["program_count"] == 0 and live["course_count"] == 0:
            need_draft_payload.append(institution_id)

    drafts_by_institution: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    if need_draft_payload:
        for institution_id, status, payload in (
            db.query(
                InstitutionWizardDraft.institution_id,
                InstitutionWizardDraft.status,
                InstitutionWizardDraft.payload,
            )
            .filter(InstitutionWizardDraft.institution_id.in_(need_draft_payload))
            .order_by(InstitutionWizardDraft.updated_at.desc())
            .all()
        ):
            drafts_by_institution[institution_id].append(
                (status or "", payload if isinstance(payload, dict) else {})
            )

    for institution_id in ids:
        live = catalog[institution_id]
        level_count = live["level_count"]
        program_count = live["program_count"]
        major_count = live["major_count"]
        sub_major_count = live["sub_major_count"]
        course_count = live["course_count"]
        if not program_count and not course_count:
            draft_catalog = {institution_id: _empty_catalog_sets()}
            for course in _best_college_scoped_courses(
                drafts_by_institution.get(institution_id, [])
            ):
                accumulate_offering_catalog_row(
                    draft_catalog,
                    institution_id,
                    program_id=course.get("program_id"),
                    course_id=course.get("course_id") if course.get("course_id") else None,
                    major_id=course.get("major_id"),
                    level_id=course.get("level_id"),
                )
            level_ids, program_ids, major_ids, course_ids = draft_catalog[institution_id]
            # Ignore placeholder course_id <= 0 and program-clone ids that are
            # not real Academic Framework courses.
            course_ids = _education_course_ids_in(
                db, {cid for cid in course_ids if cid > 0}
            )
            level_count = len(level_ids)
            program_count = len(program_ids)
            major_count = len(major_ids)
            course_count = len(course_ids)

        scoped_intakes = entity_counts["intake"].get(institution_id, 0)
        entity_intakes = entity_counts["intake_entity"].get(institution_id, 0)
        intake_count = entity_intakes or scoped_intakes
        if not intake_count:
            payload = _best_wizard_payload(drafts_by_institution.get(institution_id, []))
            intake_count = len(payload.get("intakes") or [])

        picture_count = entity_counts["picture"].get(institution_id, 0)
        if not picture_count:
            payload = _best_wizard_payload(drafts_by_institution.get(institution_id, []))
            picture_count = len(payload.get("pictures") or [])

        metrics[institution_id] = {
            "campus_count": entity_counts["campus"].get(institution_id, 0),
            "college_count": entity_counts["college"].get(institution_id, 0),
            "level_count": level_count,
            "program_count": program_count,
            "major_count": major_count,
            "sub_major_count": sub_major_count,
            "course_count": course_count,
            "intake_count": intake_count,
            "picture_count": picture_count,
        }

    return metrics


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

    via_course = (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            EducationMajor.label.label("label"),
        )
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(EducationMajor, TargetCourse.education_major_id == EducationMajor.id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            EducationMajor.label.isnot(None),
        )
    )
    via_mapping = (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            EducationMajor.label.label("label"),
        )
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.program_id == TargetCourse.qualification_program_id,
        )
        .join(EducationMajor, ProgramEducationMajorMapping.education_major_id == EducationMajor.id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            EducationMajor.label.isnot(None),
        )
    )
    major_pairs = union_all(via_course, via_mapping).subquery("major_pairs")
    return (
        db.query(
            major_pairs.c.institution_id.label("institution_id"),
            func.count(func.distinct(func.lower(func.trim(major_pairs.c.label)))).label("metric"),
        )
        .group_by(major_pairs.c.institution_id)
        .subquery("major_count_sort")
    )


def _sub_major_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(
                func.distinct(ProgramEducationMajorMapping.education_sub_major_id)
            ).label("metric"),
        )
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.program_id
            == TargetCourse.qualification_program_id,
        )
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            ProgramEducationMajorMapping.education_sub_major_id.isnot(None),
        )
        .group_by(InstitutionCourseOffering.institution_id)
        .subquery("sub_major_count_sort")
    )


def _course_count_sort_subq(db: Session):
    from app.models.academia_wizard import InstitutionCourseOffering

    return (
        db.query(
            InstitutionCourseOffering.institution_id.label("institution_id"),
            func.count(func.distinct(_mapped_course_id_expr())).label("metric"),
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .outerjoin(Program, TargetCourse.qualification_program_id == Program.id)
        .outerjoin(EducationCourse, _education_course_join())
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
    "level_count": _level_count_sort_subq,
    "program_count": _program_count_sort_subq,
    "major_count": _major_count_sort_subq,
    "sub_major_count": _sub_major_count_sort_subq,
    "course_count": _course_count_sort_subq,
}


def _offering_institution_filter_query(
    db: Session,
    *,
    program_ids: list[int] | None = None,
    major_ids: list[int] | None = None,
    sub_major_ids: list[int] | None = None,
):
    """Institutions whose active offerings match program / major / sub-major filters."""
    from app.models.academia_wizard import InstitutionCourseOffering

    offering_q = (
        db.query(InstitutionCourseOffering.institution_id)
        .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
        .filter(InstitutionCourseOffering.is_active.is_(True))
    )
    if program_ids:
        offering_q = offering_q.filter(TargetCourse.qualification_program_id.in_(program_ids))
    if major_ids:
        offering_q = offering_q.filter(TargetCourse.education_major_id.in_(major_ids))
    if sub_major_ids:
        offering_q = offering_q.join(
            ProgramEducationMajorMapping,
            ProgramEducationMajorMapping.program_id == TargetCourse.qualification_program_id,
        ).filter(ProgramEducationMajorMapping.education_sub_major_id.in_(sub_major_ids))
    return offering_q.distinct()


def list_institutions_summary_admin(
    db: Session,
    *,
    query: str | None = None,
    country_ids: list[int] | None = None,
    state_ids: list[int] | None = None,
    city_ids: list[int] | None = None,
    is_active: bool | None = None,
    institution_type_ids: list[int] | None = None,
    program_ids: list[int] | None = None,
    major_ids: list[int] | None = None,
    sub_major_ids: list[int] | None = None,
    template_ids: list[int] | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Institution], int]:
    q = db.query(Institution).options(
        load_only(
            Institution.id,
            Institution.country_id,
            Institution.state_id,
            Institution.city_id,
            Institution.name,
            Institution.code,
            Institution.institution_type_id,
            Institution.is_active,
            Institution.sort_order,
            Institution.publish_status,
            Institution.last_publish_attempt_at,
            Institution.created_at,
            Institution.updated_at,
        ),
        joinedload(Institution.country).load_only(Country.id, Country.name),
        joinedload(Institution.state).load_only(GeographyState.id, GeographyState.name),
        joinedload(Institution.city).load_only(GeographyCity.id, GeographyCity.name),
        joinedload(Institution.institution_type_ref).load_only(
            InstitutionType.id, InstitutionType.code, InstitutionType.name
        ),
    )

    if query:
        pattern = _search_pattern(query)
        q = q.filter(Institution.name.ilike(pattern))

    if country_ids:
        q = q.filter(Institution.country_id.in_(country_ids))
    if state_ids:
        q = q.filter(Institution.state_id.in_(state_ids))
    if city_ids:
        q = q.filter(Institution.city_id.in_(city_ids))
    if is_active is not None:
        q = q.filter(Institution.is_active.is_(is_active))
    if institution_type_ids:
        q = q.filter(Institution.institution_type_id.in_(institution_type_ids))

    if program_ids or major_ids or sub_major_ids:
        matching_ids = [
            row[0]
            for row in _offering_institution_filter_query(
                db,
                program_ids=program_ids,
                major_ids=major_ids,
                sub_major_ids=sub_major_ids,
            ).all()
        ]
        if not matching_ids:
            return [], 0
        q = q.filter(Institution.id.in_(matching_ids))

    if template_ids:
        from app.models.academia_wizard import InstitutionIntake

        matching_ids = [
            row[0]
            for row in db.query(InstitutionIntake.institution_id)
            .filter(InstitutionIntake.template_id.in_(template_ids))
            .distinct()
            .all()
        ]
        if not matching_ids:
            return [], 0
        q = q.filter(Institution.id.in_(matching_ids))

    total = q.order_by(None).enable_eagerloads(False).count()

    sort_map = {
        "name": Institution.name,
        "created_at": Institution.created_at,
        "code": Institution.code,
        "status": Institution.is_active,
        "sort_order": Institution.sort_order,
        "id": Institution.id,
    }

    if sort_by in _COUNT_SORT_SUBQUERIES:
        subq = _COUNT_SORT_SUBQUERIES[sort_by](db)
        q = q.outerjoin(subq, Institution.id == subq.c.institution_id)
        sort_column = func.coalesce(subq.c.metric, 0)
    elif sort_by == "institution_type_id":
        sort_column = Institution.institution_type_id
    elif sort_by == "institution_type":
        q = q.outerjoin(
            InstitutionType, Institution.institution_type_id == InstitutionType.id
        )
        sort_column = InstitutionType.name
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
        .options(
            joinedload(Institution.country),
            joinedload(Institution.institution_type_ref),
        )
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
    if payload.institution_type_id is not None:
        get_institution_type_admin(db, payload.institution_type_id)
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
    if "institution_type_id" in data and data["institution_type_id"] is not None:
        get_institution_type_admin(db, data["institution_type_id"])
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
            "institution_type_id",
            "company_affiliated",
            "ranking_tier_global",
            "ad_promotion_flag",
            "institution_web_url",
            "web_links",
            "currency_type",
            "students_count",
            *INSTITUTION_PROFILE_TEXT_FIELD_NAMES,
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
    # Batched on purpose: per-institution/per-campus lookups turned into ~750
    # round trips once the US institution import landed, which timed out the page.
    institutions = (
        db.query(Institution)
        .order_by(Institution.sort_order.asc(), Institution.name.asc())
        .all()
    )
    campuses = (
        db.query(Campus)
        .options(
            joinedload(Campus.location).joinedload(GeographyCity.state),
            joinedload(Campus.location).joinedload(GeographyCity.country),
        )
        .order_by(Campus.sort_order.asc(), Campus.name.asc())
        .all()
    )
    colleges = (
        db.query(College)
        .options(selectinload(College.campus_links))
        .order_by(College.sort_order.asc(), College.name.asc())
        .all()
    )

    campus_names = {campus.id: campus.name for campus in campuses}
    campuses_by_institution: dict[int, list[Campus]] = defaultdict(list)
    for campus in campuses:
        campuses_by_institution[campus.institution_id].append(campus)

    colleges_by_campus: dict[int, list[College]] = defaultdict(list)
    linked_names_by_college: dict[int, list[str]] = {}
    for college in colleges:
        linked_ids = [link.campus_id for link in college.campus_links]
        if college.campus_id is not None and college.campus_id not in linked_ids:
            linked_ids.insert(0, college.campus_id)
        linked_names_by_college[college.id] = [
            campus_names[campus_id] for campus_id in linked_ids if campus_id in campus_names
        ]
        # A college nests under every campus it is linked to, not just the primary.
        for campus_id in linked_ids:
            colleges_by_campus[campus_id].append(college)

    nodes: list[InstitutionHierarchyNode] = []
    for institution in institutions:
        campus_nodes = [
            InstitutionHierarchyCampusNode(
                id=campus.id,
                name=campus.name,
                location_label=_city_location_label(campus.location),
                description=campus.description,
                colleges=[
                    InstitutionHierarchyCollegeNode(
                        id=college.id,
                        name=college.name,
                        dean_name=college.dean_name,
                        campus_names=linked_names_by_college.get(college.id, []),
                    )
                    for college in colleges_by_campus.get(campus.id, [])
                ],
            )
            for campus in campuses_by_institution.get(institution.id, [])
        ]
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


# --- Institution types ---


def list_institution_types_admin(db: Session) -> list[InstitutionType]:
    return (
        db.query(InstitutionType)
        .filter(InstitutionType.is_active.is_(True))
        .order_by(InstitutionType.sort_order.asc(), InstitutionType.name.asc())
        .all()
    )


def get_institution_type_admin(db: Session, institution_type_id: int) -> InstitutionType:
    record = (
        db.query(InstitutionType)
        .filter(InstitutionType.id == institution_type_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Institution type not found.")
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
        .options(
            joinedload(College.institution),
            joinedload(College.campus),
            selectinload(College.campus_links).joinedload(CollegeCampus.campus),
        )
        .order_by(College.sort_order.asc(), College.name.asc())
    )
    if institution_id is not None:
        q = q.filter(College.institution_id == institution_id)
    if campus_id is not None:
        q = q.filter(
            or_(
                College.campus_id == campus_id,
                College.campus_links.any(CollegeCampus.campus_id == campus_id),
            )
        )
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
            selectinload(College.campus_links)
            .joinedload(CollegeCampus.campus)
            .joinedload(Campus.location),
        )
        .filter(College.id == college_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="College not found.")
    return record


def _sync_college_campuses(
    db: Session,
    record: College,
    campus_ids: list[int] | None,
) -> None:
    if campus_ids is None:
        campus_ids = [record.campus_id] if record.campus_id is not None else []
    unique_ids = list(dict.fromkeys(int(value) for value in campus_ids))
    if record.campus_id is not None and record.campus_id not in unique_ids:
        unique_ids.insert(0, record.campus_id)
    campuses = (
        db.query(Campus).filter(Campus.id.in_(unique_ids)).all() if unique_ids else []
    )
    by_id = {campus.id: campus for campus in campuses}
    missing = [campus_id for campus_id in unique_ids if campus_id not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f"Campus IDs not found: {missing}.")
    if any(campus.institution_id != record.institution_id for campus in campuses):
        raise HTTPException(
            status_code=400,
            detail="All linked campuses must belong to the selected institution.",
        )
    db.query(CollegeCampus).filter(CollegeCampus.college_id == record.id).delete(
        synchronize_session=False
    )
    for campus_id in unique_ids:
        db.add(
            CollegeCampus(
                college_id=record.id,
                campus_id=campus_id,
                is_primary=campus_id == record.campus_id,
            )
        )


def create_college_admin(db: Session, payload: CollegeCreate) -> College:
    get_institution_admin(db, payload.institution_id)
    if payload.campus_id is not None:
        campus = get_campus_admin(db, payload.campus_id)
        if campus.institution_id != payload.institution_id:
            raise HTTPException(
                status_code=400,
                detail="Campus does not belong to the selected institution.",
            )
    data = payload.model_dump(exclude={"campus_ids"})
    record = College(**data)
    db.add(record)
    db.flush()
    _sync_college_campuses(db, record, payload.campus_ids)
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
    if "campus_ids" in data or "campus_id" in data or "institution_id" in data:
        _sync_college_campuses(db, record, data.get("campus_ids"))
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


def _find_program_name_conflict(
    db: Session,
    *,
    level_id: int,
    name: str,
    exclude_id: int | None = None,
    institution_id: int | None = None,
    country_id: int | None = None,
) -> Program | None:
    """Match another program by country + institution + level + name.

    Never falls back to a global name+level lock. If institution is missing,
    there is no uniqueness collision to report.
    """
    if not normalized_display_name(name) or not institution_id:
        return None
    resolved_institution_id = int(institution_id)
    resolved_country_id = int(country_id) if country_id else None
    if not resolved_country_id:
        inst = db.query(Institution).filter(Institution.id == resolved_institution_id).first()
        if inst and inst.country_id:
            resolved_country_id = int(inst.country_id)
    query = filter_by_display_name(
        db.query(Program).filter(Program.level_id == level_id),
        Program.name,
        name,
        exclude_id=int(exclude_id) if exclude_id is not None else None,
        id_column=Program.id,
    )
    query = query.filter(
        _program_offering_match_exists(
            institution_ids=[resolved_institution_id],
            country_ids=[resolved_country_id] if resolved_country_id else None,
        )
    )
    hit = query.first()
    if not hit:
        return None
    offering = program_offering_institution_payloads(db, [int(hit.id)]).get(int(hit.id), {})
    offered_at = {int(iid) for iid in (offering.get("institution_ids") or []) if iid}
    if offering.get("institution_id"):
        offered_at.add(int(offering["institution_id"]))
    if resolved_institution_id not in offered_at:
        return None
    return hit


def _program_name_exists(
    db: Session,
    *,
    level_id: int,
    name: str,
    exclude_id: int | None = None,
    institution_id: int | None = None,
    country_id: int | None = None,
) -> bool:
    return (
        _find_program_name_conflict(
            db,
            level_id=level_id,
            name=name,
            exclude_id=exclude_id,
            institution_id=institution_id,
            country_id=country_id,
        )
        is not None
    )


def _program_name_conflict_http_detail(db: Session, conflict: Program) -> dict[str, Any]:
    offering = program_offering_institution_payloads(db, [int(conflict.id)]).get(
        int(conflict.id), {}
    )
    iid = offering.get("institution_id")
    names = offering.get("institution_names") or []
    inst = (
        db.query(Institution).filter(Institution.id == int(iid)).first()
        if iid
        else None
    )
    cid = offering.get("country_id")
    if inst and inst.country_id:
        cid = inst.country_id
    detail = {
        "message": (
            "A program with this name already exists for the selected level."
            f" (conflict program_id={int(conflict.id)}"
            f" institution_id={int(iid) if iid else 'none'}"
            f" country_id={int(cid) if cid else 'none'})"
        ),
        "conflict_program_id": int(conflict.id),
        "conflict_institution_id": int(iid) if iid else None,
        "conflict_institution_name": inst.name if inst else (names[0] if names else None),
        "conflict_country_id": int(cid) if cid else None,
    }
    logger.warning("Program name uniqueness conflict: %s", detail)
    return detail


def _degree_program_count(db: Session, program_id: int) -> int:
    return db.query(TargetProgram).filter(TargetProgram.program_id == program_id).count()


def _degree_major_details(db: Session, program_id: int) -> tuple[int, list[str]]:
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


def _degree_major_count(db: Session, program_id: int) -> int:
    return (
        db.query(ProgramEducationMajorMapping)
        .join(EducationMajor, EducationMajor.id == ProgramEducationMajorMapping.education_major_id)
        .filter(
            ProgramEducationMajorMapping.program_id == program_id,
            EducationMajor.is_active.is_(True),
        )
        .count()
    )


def get_degree_admin(db: Session, program_id: int) -> Program:
    record = (
        db.query(Program)
        .options(joinedload(Program.level))
        .filter(Program.id == program_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Program not found.")
    return record


def _program_offering_match_exists(
    *,
    country_ids: list[int] | None = None,
    institution_ids: list[int] | None = None,
):
    """True when the program is offered via active institution_course_offerings.

    INNER JOIN offerings → target_courses.qualification_program_id. An institution
    with zero matching offerings matches nothing (no fallback to other institutions).
    """
    from app.models.academia_wizard import InstitutionCourseOffering

    stmt = (
        select(literal(1))
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
    )
    if country_ids:
        stmt = stmt.join(
            Institution,
            Institution.id == InstitutionCourseOffering.institution_id,
        )
    conditions = [
        InstitutionCourseOffering.is_active.is_(True),
        TargetCourse.qualification_program_id == Program.id,
    ]
    if institution_ids:
        conditions.append(
            InstitutionCourseOffering.institution_id.in_(list(institution_ids))
        )
    if country_ids:
        conditions.append(Institution.country_id.in_(list(country_ids)))
    return exists(stmt.where(*conditions))


def program_offering_institution_payloads(
    db: Session, program_ids: Sequence[int]
) -> dict[int, dict]:
    """Institution names for programs on this page (one query, no N+1)."""
    from app.models.academia_wizard import InstitutionCourseOffering

    empty: dict = {
        "institution_id": None,
        "institution_ids": [],
        "institution_names": [],
        "country_id": None,
        "college_id": None,
    }
    unique_ids = list(dict.fromkeys(int(pid) for pid in program_ids if pid))
    result: dict[int, dict] = {pid: {**empty, "institution_ids": [], "institution_names": []} for pid in unique_ids}
    if not unique_ids:
        return result

    rows = (
        db.query(
            TargetCourse.qualification_program_id,
            Institution.id,
            Institution.name,
            Institution.country_id,
            InstitutionCourseOffering.college_id,
            InstitutionCourseOffering.id,
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, InstitutionCourseOffering.course_id == TargetCourse.id)
        .join(Institution, Institution.id == InstitutionCourseOffering.institution_id)
        .filter(
            InstitutionCourseOffering.is_active.is_(True),
            TargetCourse.qualification_program_id.in_(unique_ids),
        )
        .order_by(InstitutionCourseOffering.id.asc(), Institution.name.asc(), Institution.id.asc())
        .all()
    )
    seen: dict[int, set[int]] = defaultdict(set)
    for program_id, institution_id, name, country_id, college_id, _offering_id in rows:
        if program_id is None or institution_id is None:
            continue
        pid = int(program_id)
        iid = int(institution_id)
        bucket = result.setdefault(
            pid, {**empty, "institution_ids": [], "institution_names": []}
        )
        if iid in seen[pid]:
            continue
        seen[pid].add(iid)
        bucket["institution_ids"].append(iid)
        if name:
            bucket["institution_names"].append(name)
        if bucket["institution_id"] is None:
            bucket["institution_id"] = iid
            bucket["country_id"] = int(country_id) if country_id else None
            bucket["college_id"] = int(college_id) if college_id else None
    return result


def _unique_related_code(db: Session, model, base_code: str) -> str:
    code = (base_code or "PROG")[:50]
    if not db.query(model).filter(model.code == code).first():
        return code
    suffix = 2
    while suffix < 1000:
        candidate = f"{(base_code or 'PROG')[:45]}_{suffix}"
        if not db.query(model).filter(model.code == candidate).first():
            return candidate
        suffix += 1
    raise HTTPException(status_code=409, detail="Could not generate a unique offering code.")


def _ensure_program_clone_course(db: Session, program: Program) -> TargetCourse:
    existing = (
        db.query(TargetCourse)
        .filter(TargetCourse.qualification_program_id == program.id)
        .order_by(TargetCourse.id.asc())
        .first()
    )
    if existing:
        return existing

    target_program = (
        db.query(TargetProgram)
        .filter(TargetProgram.program_id == program.id)
        .order_by(TargetProgram.id.asc())
        .first()
    )
    if not target_program:
        target_program = TargetProgram(
            program_id=program.id,
            code=_unique_related_code(db, TargetProgram, program.code),
            label=program.name,
            description=program.description,
            is_active=True,
            sort_order=0,
        )
        db.add(target_program)
        db.flush()

    from app.models.level import Level

    level = getattr(program, "level", None) or db.query(Level).filter(Level.id == program.level_id).first()
    major_ids = _degree_major_ids(db, program.id)
    course = TargetCourse(
        program_id=target_program.id,
        education_major_id=major_ids[0] if major_ids else None,
        qualification_program_id=program.id,
        code=_unique_related_code(db, TargetCourse, program.code),
        label=program.name,
        level=(level.name[:40] if level and level.name else None),
        is_active=True,
        sort_order=0,
    )
    db.add(course)
    db.flush()
    return course


def ensure_program_institution_offering(
    db: Session,
    program: Program,
    institution_id: int,
    college_id: int | None = None,
) -> None:
    from app.models.academia_wizard import InstitutionCourseOffering

    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=400, detail="Invalid institution.")
    resolved_college_id = college_id
    if college_id is not None:
        college = (
            db.query(College)
            .filter(College.id == college_id, College.institution_id == institution_id)
            .first()
        )
        if not college:
            raise HTTPException(
                status_code=400,
                detail="College does not belong to the selected institution.",
            )

    offering = (
        db.query(InstitutionCourseOffering)
        .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
        .filter(
            TargetCourse.qualification_program_id == program.id,
            InstitutionCourseOffering.institution_id == institution_id,
        )
        .order_by(InstitutionCourseOffering.id.asc())
        .first()
    )
    if offering:
        offering.is_active = True
        if resolved_college_id is not None:
            offering.college_id = resolved_college_id
        return

    course = _ensure_program_clone_course(db, program)
    db.add(
        InstitutionCourseOffering(
            institution_id=institution_id,
            campus_id=None,
            college_id=resolved_college_id,
            course_id=course.id,
            is_active=True,
            sort_order=0,
        )
    )


def _deactivate_program_offerings_for_institution(
    db: Session, program_id: int, institution_id: int
) -> None:
    from app.models.academia_wizard import InstitutionCourseOffering

    course_ids = db.query(TargetCourse.id).filter(
        TargetCourse.qualification_program_id == program_id
    )
    (
        db.query(InstitutionCourseOffering)
        .filter(
            InstitutionCourseOffering.course_id.in_(course_ids),
            InstitutionCourseOffering.institution_id == institution_id,
        )
        .update({InstitutionCourseOffering.is_active: False}, synchronize_session=False)
    )


def _active_offering_institution_ids(db: Session, program_id: int) -> list[int]:
    from app.models.academia_wizard import InstitutionCourseOffering

    rows = (
        db.query(InstitutionCourseOffering.institution_id)
        .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
        .filter(
            TargetCourse.qualification_program_id == program_id,
            InstitutionCourseOffering.is_active.is_(True),
        )
        .distinct()
        .all()
    )
    return [int(institution_id) for (institution_id,) in rows if institution_id]


def _program_target_course_ids(db: Session, program_id: int) -> list[int]:
    target_program_ids = db.query(TargetProgram.id).filter(
        TargetProgram.program_id == program_id
    )
    rows = (
        db.query(TargetCourse.id)
        .filter(
            or_(
                TargetCourse.qualification_program_id == program_id,
                TargetCourse.program_id.in_(target_program_ids),
            )
        )
        .all()
    )
    return [int(course_id) for (course_id,) in rows]


def _delete_program_dependents(db: Session, program_id: int) -> None:
    """Clear offering/clone FKs so a qualification program row can be removed.

    Catalog majors and education_courses are detached, not deleted.
    """
    from app.models.academia_wizard import InstitutionCourseOffering
    from app.models.academic_calendar import ProgramIntakeAssignment

    course_ids = _program_target_course_ids(db, program_id)
    if course_ids:
        db.query(InstitutionCourseOffering).filter(
            InstitutionCourseOffering.course_id.in_(course_ids)
        ).delete(synchronize_session=False)
        db.query(TargetCourse).filter(TargetCourse.id.in_(course_ids)).delete(
            synchronize_session=False
        )

    db.query(ProgramIntakeAssignment).filter(
        ProgramIntakeAssignment.program_id == program_id
    ).delete(synchronize_session=False)
    db.query(ProgramEducationMajorMapping).filter(
        ProgramEducationMajorMapping.program_id == program_id
    ).delete(synchronize_session=False)
    db.query(EducationMajor).filter(EducationMajor.program_id == program_id).update(
        {EducationMajor.program_id: None}, synchronize_session=False
    )
    db.query(EducationCourse).filter(EducationCourse.program_id == program_id).update(
        {EducationCourse.program_id: None}, synchronize_session=False
    )
    db.query(TargetProgram).filter(TargetProgram.program_id == program_id).delete(
        synchronize_session=False
    )


def list_degrees_admin(
    db: Session,
    *,
    query: str | None = None,
    level_id: int | None = None,
    major_ids: list[int] | None = None,
    sub_major_ids: list[int] | None = None,
    country_ids: list[int] | None = None,
    institution_ids: list[int] | None = None,
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
    cleaned_major_ids = [int(item) for item in (major_ids or []) if int(item) > 0]
    cleaned_sub_major_ids = [int(item) for item in (sub_major_ids or []) if int(item) > 0]
    cleaned_country_ids = [int(item) for item in (country_ids or []) if int(item) > 0]
    cleaned_institution_ids = [
        int(item) for item in (institution_ids or []) if int(item) > 0
    ]
    if cleaned_major_ids:
        q = q.filter(
            Program.id.in_(
                db.query(ProgramEducationMajorMapping.program_id).filter(
                    ProgramEducationMajorMapping.education_major_id.in_(cleaned_major_ids)
                )
            )
        )
    if cleaned_sub_major_ids:
        q = q.filter(
            Program.id.in_(
                db.query(ProgramEducationMajorMapping.program_id).filter(
                    ProgramEducationMajorMapping.education_sub_major_id.in_(
                        cleaned_sub_major_ids
                    )
                )
            )
        )
    if cleaned_country_ids or cleaned_institution_ids:
        q = q.filter(
            _program_offering_match_exists(
                country_ids=cleaned_country_ids or None,
                institution_ids=cleaned_institution_ids or None,
            )
        )
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
    major_ids: list[int] | None = None,
    sub_major_ids: list[int] | None = None,
    country_ids: list[int] | None = None,
    institution_ids: list[int] | None = None,
    active_only: bool = False,
) -> list[Program]:
    rows, _ = list_degrees_admin(
        db,
        query=query,
        level_id=level_id,
        major_ids=major_ids,
        sub_major_ids=sub_major_ids,
        country_ids=country_ids,
        institution_ids=institution_ids,
        active_only=active_only,
        page=1,
        page_size=10_000,
    )
    return rows


def program_major_mapping_payloads(
    db: Session, program_ids: Sequence[int]
) -> dict[int, dict[str, list]]:
    empty: dict[str, list] = {
        "major_ids": [],
        "major_names": [],
        "sub_major_ids": [],
        "sub_major_names": [],
    }
    unique_ids = list(dict.fromkeys(int(pid) for pid in program_ids if pid))
    result: dict[int, dict[str, list]] = {pid: {key: [] for key in empty} for pid in unique_ids}
    if not unique_ids:
        return result

    rows = (
        db.query(
            ProgramEducationMajorMapping,
            EducationMajor.label,
            EducationSubMajor.name,
        )
        .outerjoin(
            EducationMajor,
            EducationMajor.id == ProgramEducationMajorMapping.education_major_id,
        )
        .outerjoin(
            EducationSubMajor,
            EducationSubMajor.id == ProgramEducationMajorMapping.education_sub_major_id,
        )
        .filter(ProgramEducationMajorMapping.program_id.in_(unique_ids))
        .order_by(
            ProgramEducationMajorMapping.program_id.asc(),
            ProgramEducationMajorMapping.id.asc(),
        )
        .all()
    )
    seen_majors: dict[int, set[int]] = defaultdict(set)
    seen_subs: dict[int, set[int]] = defaultdict(set)
    for mapping, major_label, sub_name in rows:
        pid = int(mapping.program_id)
        bucket = result.setdefault(pid, {key: [] for key in empty})
        major_id = mapping.education_major_id
        if major_id and int(major_id) not in seen_majors[pid]:
            seen_majors[pid].add(int(major_id))
            bucket["major_ids"].append(int(major_id))
            if major_label:
                bucket["major_names"].append(major_label)
        sub_id = mapping.education_sub_major_id
        if sub_id and int(sub_id) not in seen_subs[pid]:
            seen_subs[pid].add(int(sub_id))
            bucket["sub_major_ids"].append(int(sub_id))
            if sub_name:
                bucket["sub_major_names"].append(sub_name)
    return result


def _degree_major_ids(db: Session, program_id: int) -> list[int]:
    return program_major_mapping_payloads(db, [program_id]).get(program_id, {}).get(
        "major_ids", []
    )


def _sub_major_ids_by_parent(
    db: Session, major_ids: list[int], sub_major_ids: list[int]
) -> dict[int, list[int]]:
    unique_subs = list(dict.fromkeys(int(item) for item in sub_major_ids if item))
    if not unique_subs:
        return {}
    allowed_majors = set(major_ids)
    rows = (
        db.query(EducationSubMajor)
        .filter(EducationSubMajor.id.in_(unique_subs))
        .all()
    )
    found = {int(row.id): row for row in rows}
    missing = [item for item in unique_subs if item not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid catalog sub-major(s): {', '.join(str(i) for i in missing)}",
        )
    by_parent: dict[int, list[int]] = {}
    for sub_id in unique_subs:
        record = found[sub_id]
        parent_id = int(record.major_id)
        if parent_id not in allowed_majors:
            raise HTTPException(
                status_code=400,
                detail="Each sub-major must belong to a selected catalog major.",
            )
        by_parent.setdefault(parent_id, []).append(int(record.id))
    return by_parent


def _program_major_mapping_pairs(
    db: Session,
    program_id: int,
    unique_major_ids: list[int],
    sub_major_ids: list[int] | None,
) -> list[tuple[int, int | None]]:
    remaining = set(unique_major_ids)
    if sub_major_ids is None:
        existing = (
            db.query(ProgramEducationMajorMapping)
            .filter(ProgramEducationMajorMapping.program_id == program_id)
            .order_by(ProgramEducationMajorMapping.id.asc())
            .all()
        )
        pairs: list[tuple[int, int | None]] = []
        seen: set[tuple[int, int | None]] = set()
        majors_with_pairs: set[int] = set()
        for row in existing:
            mid = int(row.education_major_id)
            if mid not in remaining:
                continue
            sid = int(row.education_sub_major_id) if row.education_sub_major_id else None
            key = (mid, sid)
            if key in seen:
                continue
            seen.add(key)
            majors_with_pairs.add(mid)
            pairs.append(key)
        for mid in unique_major_ids:
            if mid not in majors_with_pairs:
                pairs.append((mid, None))
        return pairs

    by_parent = _sub_major_ids_by_parent(db, unique_major_ids, sub_major_ids)
    pairs = []
    for mid in unique_major_ids:
        children = by_parent.get(mid) or []
        if children:
            pairs.extend((mid, sid) for sid in children)
        else:
            pairs.append((mid, None))
    return pairs


def _replace_program_major_mappings(
    db: Session,
    program_id: int,
    major_ids: list[int],
    sub_major_ids: list[int] | None = None,
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

    pairs = _program_major_mapping_pairs(db, program_id, unique_ids, sub_major_ids)

    db.query(ProgramEducationMajorMapping).filter(
        ProgramEducationMajorMapping.program_id == program_id
    ).delete(synchronize_session=False)

    for major_id, sub_id in pairs:
        db.add(
            ProgramEducationMajorMapping(
                program_id=program_id,
                education_major_id=major_id,
                education_sub_major_id=sub_id,
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
    if not payload.institution_id:
        raise HTTPException(status_code=400, detail="Institution is required.")
    validate_program_intake_assignments(
        db,
        program_id=None,
        institution_id=payload.institution_id,
        intake_ids=payload.intake_ids,
        is_active=payload.is_active,
    )
    conflict = _find_program_name_conflict(
        db,
        level_id=payload.level_id,
        name=payload.name,
        institution_id=payload.institution_id,
        country_id=getattr(payload, "country_id", None),
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=_program_name_conflict_http_detail(db, conflict),
        )
    base_code = (payload.code or _slugify_degree_code(payload.name)).upper()
    code = _unique_degree_code(db, base_code)
    record = Program(
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        program_url=(payload.program_url or "").strip() or None,
        level_id=payload.level_id,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.flush()
    _replace_program_major_mappings(
        db, record.id, payload.major_ids, payload.sub_major_ids
    )
    ensure_program_institution_offering(
        db,
        record,
        payload.institution_id,
        college_id=getattr(payload, "college_id", None),
    )
    replace_program_intake_assignments(
        db,
        record.id,
        payload.institution_id,
        payload.intake_ids,
    )
    db.commit()
    db.refresh(record)
    return get_degree_admin(db, record.id)


def update_degree_admin(db: Session, program_id: int, payload: DegreeAdminUpdate) -> Program:
    from app.services.academic_calendar_service import (
        get_program_intake_ids,
        replace_program_intake_assignments,
        validate_program_intake_assignments,
    )

    record = get_degree_admin(db, program_id)
    data = payload.model_dump(exclude_unset=True)
    institution_id = data.pop("institution_id", None)
    college_id = data.pop("college_id", None)
    intake_ids = data.pop("intake_ids", None)
    major_ids_provided = "major_ids" in getattr(payload, "model_fields_set", set()) or "major_ids" in data
    major_ids = data.pop("major_ids", None) if major_ids_provided else None
    if major_ids_provided and major_ids is None:
        major_ids = []
    sub_major_ids_provided = (
        "sub_major_ids" in getattr(payload, "model_fields_set", set()) or "sub_major_ids" in data
    )
    sub_major_ids = data.pop("sub_major_ids", None) if sub_major_ids_provided else None
    if sub_major_ids_provided and sub_major_ids is None:
        sub_major_ids = []
    next_level_id = data["level_id"] if "level_id" in data and data["level_id"] is not None else record.level_id
    next_name = data["name"].strip() if "name" in data and data["name"] is not None else record.name
    existing_offering = program_offering_institution_payloads(db, [program_id]).get(
        program_id, {}
    )
    current_institution_id = existing_offering.get("institution_id")
    next_institution_id = institution_id if institution_id is not None else current_institution_id
    payload_country_id = data.pop("country_id", None)
    next_country_id = payload_country_id or existing_offering.get("country_id")
    name_unchanged = normalized_display_name(next_name) == normalized_display_name(record.name)
    level_unchanged = int(next_level_id) == int(record.level_id)
    institution_unchanged = (
        next_institution_id is not None
        and current_institution_id is not None
        and int(next_institution_id) == int(current_institution_id)
    ) or (institution_id is None and current_institution_id is not None)
    # Dual degrees share names across unis (e.g. JCU 1032 vs UOW 1062). Never 409
    # an existing row when country/institution/level/name identity is unchanged.
    identity_unchanged = name_unchanged and level_unchanged and (
        institution_unchanged or next_institution_id is None
    )
    if not identity_unchanged:
        conflict = _find_program_name_conflict(
            db,
            level_id=next_level_id,
            name=next_name,
            exclude_id=int(program_id),
            institution_id=int(next_institution_id) if next_institution_id else None,
            country_id=int(next_country_id) if next_country_id else None,
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=_program_name_conflict_http_detail(db, conflict),
            )
    if "name" in data and data["name"] is not None:
        record.name = data["name"].strip()
    if "description" in data:
        record.description = (data["description"] or "").strip() or None
    if "program_url" in data:
        record.program_url = (data["program_url"] or "").strip() or None
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
    if institution_id is not None:
        previous = program_offering_institution_payloads(db, [program_id]).get(
            program_id, {}
        )
        previous_primary = previous.get("institution_id")
        ensure_program_institution_offering(
            db, record, institution_id, college_id=college_id
        )
        if (
            previous_primary
            and int(previous_primary) != int(institution_id)
        ):
            _deactivate_program_offerings_for_institution(
                db, program_id, int(previous_primary)
            )
    if major_ids is not None or sub_major_ids_provided:
        resolved_majors = major_ids if major_ids is not None else _degree_major_ids(db, program_id)
        _replace_program_major_mappings(
            db,
            program_id,
            resolved_majors,
            sub_major_ids if sub_major_ids_provided else None,
        )
    db.commit()
    db.refresh(record)
    return get_degree_admin(db, program_id)


def delete_degree_admin(
    db: Session, program_id: int, *, institution_id: int | None = None
) -> None:
    get_degree_admin(db, program_id)
    if institution_id is not None:
        other_institutions = [
            iid
            for iid in _active_offering_institution_ids(db, program_id)
            if iid != int(institution_id)
        ]
        if other_institutions:
            _deactivate_program_offerings_for_institution(
                db, program_id, int(institution_id)
            )
            db.commit()
            return

    _delete_program_dependents(db, program_id)
    db.query(Program).filter(Program.id == program_id).delete(synchronize_session=False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete this program because other records still reference it."
            ),
        ) from None


_INSTITUTION_COVERAGE_LIMIT = 40


def _coverage_pct(*, part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * part / total, 1)


def _coverage_pair(*, mapped: int, total: int) -> FrameworkCoveragePair:
    mapped = max(int(mapped or 0), 0)
    total = max(int(total or 0), 0)
    mapped = min(mapped, total)
    unmapped = max(total - mapped, 0)
    mapped_pct = _coverage_pct(part=mapped, total=total)
    unmapped_pct = _coverage_pct(part=unmapped, total=total)
    if total > 0 and unmapped == 0:
        mapped_pct = 100.0
        unmapped_pct = 0.0
    elif unmapped > 0 and mapped_pct >= 100.0:
        mapped_pct = 99.9
        unmapped_pct = max(unmapped_pct, 0.1)
    return FrameworkCoveragePair(
        mapped=mapped,
        unmapped=unmapped,
        total=total,
        mapped_pct=mapped_pct,
        unmapped_pct=unmapped_pct,
    )


def _framework_program_ids_with_courses(
    db: Session, program_ids: set[int] | None = None
) -> set[int]:
    """Programs that have a Framework course (education_courses), directly or via major mapping."""
    if program_ids is not None and not program_ids:
        return set()
    direct_q = db.query(EducationCourse.program_id).filter(
        EducationCourse.program_id.isnot(None),
        EducationCourse.is_active.is_(True),
    )
    if program_ids is not None:
        direct_q = direct_q.filter(EducationCourse.program_id.in_(program_ids))
    direct = {int(row[0]) for row in direct_q.distinct().all() if row[0] is not None}
    via_q = (
        db.query(ProgramEducationMajorMapping.program_id)
        .join(
            CourseEducationMajorMapping,
            CourseEducationMajorMapping.education_major_id
            == ProgramEducationMajorMapping.education_major_id,
        )
        .join(
            EducationCourse,
            EducationCourse.id == CourseEducationMajorMapping.course_id,
        )
        .filter(EducationCourse.is_active.is_(True))
    )
    if program_ids is not None:
        via_q = via_q.filter(ProgramEducationMajorMapping.program_id.in_(program_ids))
    via_major = {int(row[0]) for row in via_q.distinct().all() if row[0] is not None}
    return direct | via_major


def _program_taxonomy_sets(
    db: Session,
    program_ids: set[int] | None = None,
) -> tuple[set[int], set[int], dict[int, set[int]], dict[int, set[int]]]:
    majors_by_program: dict[int, set[int]] = defaultdict(set)
    sub_majors_by_program: dict[int, set[int]] = defaultdict(set)
    with_major: set[int] = set()
    with_sub_major: set[int] = set()
    if program_ids is not None and not program_ids:
        return with_major, with_sub_major, majors_by_program, sub_majors_by_program
    query = (
        db.query(
            ProgramEducationMajorMapping.program_id,
            ProgramEducationMajorMapping.education_major_id,
            ProgramEducationMajorMapping.education_sub_major_id,
            EducationMajor.is_active,
        )
        .outerjoin(
            EducationMajor,
            EducationMajor.id == ProgramEducationMajorMapping.education_major_id,
        )
    )
    if program_ids is not None:
        query = query.filter(ProgramEducationMajorMapping.program_id.in_(program_ids))
    for program_id, major_id, sub_major_id, major_active in query.all():
        if program_id is None:
            continue
        pid = int(program_id)
        if major_id is not None and major_active:
            majors_by_program[pid].add(int(major_id))
            with_major.add(pid)
        # Same rule as Framework Programs: a live sub-major FK on the mapping.
        if sub_major_id is not None:
            sub_majors_by_program[pid].add(int(sub_major_id))
            with_sub_major.add(pid)
    return with_major, with_sub_major, majors_by_program, sub_majors_by_program


def _mapped_count(program_ids: set[int], mapped: set[int]) -> int:
    if not program_ids:
        return 0
    return sum(1 for pid in program_ids if pid in mapped)


def _institution_coverage_row(
    *,
    institution_id: int,
    name: str,
    country_id: int | None,
    country_name: str | None,
    program_ids: set[int],
    with_major: set[int],
    with_sub_major: set[int],
    with_course: set[int],
    with_level: set[int],
    with_url: set[int],
) -> FrameworkInstitutionCoverage:
    without_major = sum(1 for pid in program_ids if pid not in with_major)
    without_sub = sum(1 for pid in program_ids if pid not in with_sub_major)
    without_course = sum(1 for pid in program_ids if pid not in with_course)
    without_level = sum(1 for pid in program_ids if pid not in with_level)
    without_url = sum(1 for pid in program_ids if pid not in with_url)
    program_count = len(program_ids)
    return FrameworkInstitutionCoverage(
        institution_id=institution_id,
        institution_name=name,
        country_id=country_id,
        country_name=country_name,
        program_count=program_count,
        without_major=without_major,
        without_sub_major=without_sub,
        without_course=without_course,
        without_level=without_level,
        without_url=without_url,
        without_major_pct=_coverage_pct(part=without_major, total=program_count),
        without_sub_major_pct=_coverage_pct(part=without_sub, total=program_count),
        without_course_pct=_coverage_pct(part=without_course, total=program_count),
        without_level_pct=_coverage_pct(part=without_level, total=program_count),
        without_url_pct=_coverage_pct(part=without_url, total=program_count),
    )


def _programs_by_institution_from_offerings(
    db: Session,
) -> tuple[
    dict[int, tuple[str, int | None, str | None, set[int]]],
    set[int],
    dict[int, int | None],
    set[int],
]:
    """Distinct ``programs.id`` with an active offering, keyed by institution.

    Matches Framework Programs (``list_degrees_admin`` + institution filter):
    ``institution_course_offerings.is_active`` → ``target_courses.qualification_program_id``.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.models.academia_wizard import InstitutionCourseOffering

    empty: tuple[
        dict[int, tuple[str, int | None, str | None, set[int]]],
        set[int],
        dict[int, int | None],
        set[int],
    ] = ({}, set(), {}, set())
    table_names = set(sa_inspect(db.get_bind()).get_table_names())
    if "institution_course_offerings" not in table_names or "target_courses" not in table_names:
        return empty

    rows = (
        db.query(
            Institution.id,
            Institution.name,
            Institution.country_id,
            Country.name,
            Program.id,
            Program.level_id,
            Program.program_url,
        )
        .select_from(InstitutionCourseOffering)
        .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
        .join(Program, Program.id == TargetCourse.qualification_program_id)
        .join(Institution, Institution.id == InstitutionCourseOffering.institution_id)
        .outerjoin(Country, Country.id == Institution.country_id)
        .filter(InstitutionCourseOffering.is_active.is_(True))
        .all()
    )
    programs_by_institution: dict[int, tuple[str, int | None, str | None, set[int]]] = {}
    offered_ids: set[int] = set()
    level_id_by_program: dict[int, int | None] = {}
    with_url: set[int] = set()
    for institution_id, name, country_id, country_name, program_id, level_id, program_url in rows:
        if program_id is None:
            continue
        pid = int(program_id)
        offered_ids.add(pid)
        level_id_by_program[pid] = int(level_id) if level_id is not None else None
        if str(program_url or "").strip():
            with_url.add(pid)
        iid = int(institution_id)
        bucket = programs_by_institution.get(iid)
        if bucket is None:
            programs_by_institution[iid] = (
                str(name or ""),
                int(country_id) if country_id is not None else None,
                str(country_name) if country_name else None,
                set(),
            )
            bucket = programs_by_institution[iid]
        bucket[3].add(pid)
    return programs_by_institution, offered_ids, level_id_by_program, with_url


def _framework_offering_coverage(
    *,
    programs_by_institution: dict[int, tuple[str, int | None, str | None, set[int]]],
    with_major: set[int],
    with_sub_major: set[int],
    with_course: set[int],
    with_level: set[int],
    with_url: set[int],
    majors_by_program: dict[int, set[int]],
    sub_majors_by_program: dict[int, set[int]],
    level_id_by_program: dict[int, int | None],
    campus_counts: dict[int, int] | None = None,
    college_counts: dict[int, int] | None = None,
) -> tuple[list[FrameworkInstitutionCoverage], bool, list[FrameworkCountryCoverage]]:
    campus_counts = campus_counts or {}
    college_counts = college_counts or {}
    all_items: list[FrameworkInstitutionCoverage] = []
    country_program_ids: dict[tuple[int | None, str | None], set[int]] = defaultdict(set)
    country_institutions: dict[tuple[int | None, str | None], list[FrameworkInstitutionCoverage]] = (
        defaultdict(list)
    )
    for institution_id, (name, country_id, country_name, program_ids) in programs_by_institution.items():
        item = _institution_coverage_row(
            institution_id=institution_id,
            name=name,
            country_id=country_id,
            country_name=country_name,
            program_ids=program_ids,
            with_major=with_major,
            with_sub_major=with_sub_major,
            with_course=with_course,
            with_level=with_level,
            with_url=with_url,
        )
        all_items.append(item)
        key = (country_id, country_name)
        country_program_ids[key].update(program_ids)
        country_institutions[key].append(item)

    gap_items = [
        row
        for row in all_items
        if (
            row.without_major
            or row.without_sub_major
            or row.without_course
            or row.without_level
            or row.without_url
        )
    ]
    gap_items.sort(
        key=lambda row: (
            row.without_major,
            row.without_sub_major,
            row.without_course,
            row.without_level,
            row.without_url,
            row.program_count,
        ),
        reverse=True,
    )
    truncated = len(gap_items) > _INSTITUTION_COVERAGE_LIMIT

    by_country: list[FrameworkCountryCoverage] = []
    for key, program_ids in country_program_ids.items():
        country_id, country_name = key
        institutions = country_institutions[key]
        institutions.sort(
            key=lambda row: (
                -row.without_major,
                -row.without_sub_major,
                -row.without_course,
                -row.without_level,
                -row.without_url,
                -row.program_count,
                row.institution_name.lower(),
            )
        )
        majors: set[int] = set()
        sub_majors: set[int] = set()
        levels: set[int] = set()
        for pid in program_ids:
            majors.update(majors_by_program.get(pid, ()))
            sub_majors.update(sub_majors_by_program.get(pid, ()))
            level_id = level_id_by_program.get(pid)
            if level_id is not None:
                levels.add(int(level_id))
        program_count = len(program_ids)
        country_institution_ids = [row.institution_id for row in institutions]
        major_mapping = _coverage_pair(
            mapped=_mapped_count(program_ids, with_major),
            total=program_count,
        )
        sub_major_mapping = _coverage_pair(
            mapped=_mapped_count(program_ids, with_sub_major),
            total=program_count,
        )
        by_country.append(
            FrameworkCountryCoverage(
                country_id=country_id,
                country_name=country_name,
                institution_count=len(institutions),
                campus_count=sum(
                    campus_counts.get(institution_id, 0)
                    for institution_id in country_institution_ids
                ),
                college_count=sum(
                    college_counts.get(institution_id, 0)
                    for institution_id in country_institution_ids
                ),
                program_count=program_count,
                major_count=len(majors),
                sub_major_count=len(sub_majors),
                level_count=len(levels),
                programs_with_no_major=major_mapping.unmapped,
                programs_with_no_sub_major=sub_major_mapping.unmapped,
                major_mapping=major_mapping,
                sub_major_mapping=sub_major_mapping,
                course_link=_coverage_pair(
                    mapped=_mapped_count(program_ids, with_course),
                    total=program_count,
                ),
                level_assignment=_coverage_pair(
                    mapped=_mapped_count(program_ids, with_level),
                    total=program_count,
                ),
                program_url=_coverage_pair(
                    mapped=_mapped_count(program_ids, with_url),
                    total=program_count,
                ),
                by_institution=institutions,
                program_ids=sorted(program_ids),
            )
        )
    by_country.sort(
        key=lambda row: (
            row.country_name is None,
            (row.country_name or "").lower(),
        )
    )
    return gap_items[:_INSTITUTION_COVERAGE_LIMIT], truncated, by_country


def get_framework_coverage_metrics(db: Session) -> FrameworkCoverageMetrics:
    from app.models.level import Level

    (
        programs_by_institution,
        offered_ids,
        level_id_by_program,
        with_url,
    ) = _programs_by_institution_from_offerings(db)
    program_count = len(offered_ids)
    major_count = (
        db.query(func.count(EducationMajor.id))
        .filter(EducationMajor.is_active.is_(True))
        .scalar()
        or 0
    )
    sub_major_count = db.query(func.count(EducationSubMajor.id)).scalar() or 0
    level_count = db.query(func.count(Level.id)).scalar() or 0
    course_count = (
        db.query(func.count(EducationCourse.id))
        .filter(EducationCourse.is_active.is_(True))
        .scalar()
        or 0
    )

    with_major, with_sub_major, majors_by_program, sub_majors_by_program = (
        _program_taxonomy_sets(db, offered_ids)
    )
    with_course = _framework_program_ids_with_courses(db, offered_ids)
    with_level = {pid for pid, level_id in level_id_by_program.items() if level_id is not None}

    institution_ids = list(programs_by_institution.keys())
    if institution_ids:
        campus_counts = _grouped_institution_counts(db, Campus, institution_ids)
        college_counts = _grouped_institution_counts(db, College, institution_ids)
    else:
        campus_counts = {}
        college_counts = {}

    by_institution, truncated, by_country = _framework_offering_coverage(
        programs_by_institution=programs_by_institution,
        with_major=with_major,
        with_sub_major=with_sub_major,
        with_course=with_course,
        with_level=with_level,
        with_url=with_url,
        majors_by_program=majors_by_program,
        sub_majors_by_program=sub_majors_by_program,
        level_id_by_program=level_id_by_program,
        campus_counts=campus_counts,
        college_counts=college_counts,
    )
    major_mapping = _coverage_pair(
        mapped=_mapped_count(offered_ids, with_major),
        total=program_count,
    )
    sub_major_mapping = _coverage_pair(
        mapped=_mapped_count(offered_ids, with_sub_major),
        total=program_count,
    )
    return FrameworkCoverageMetrics(
        institution_count=len(institution_ids),
        campus_count=sum(campus_counts.values()),
        college_count=sum(college_counts.values()),
        program_count=program_count,
        major_count=int(major_count),
        sub_major_count=int(sub_major_count),
        level_count=int(level_count),
        course_count=int(course_count),
        programs_with_no_major=major_mapping.unmapped,
        programs_with_no_sub_major=sub_major_mapping.unmapped,
        major_mapping=major_mapping,
        sub_major_mapping=sub_major_mapping,
        course_link=_coverage_pair(
            mapped=_mapped_count(offered_ids, with_course),
            total=program_count,
        ),
        level_assignment=_coverage_pair(
            mapped=_mapped_count(offered_ids, with_level),
            total=program_count,
        ),
        program_url=_coverage_pair(
            mapped=_mapped_count(offered_ids, with_url),
            total=program_count,
        ),
        by_institution=by_institution,
        by_institution_truncated=truncated,
        by_country=by_country,
    )


def get_academic_hierarchy_summary(db: Session) -> AcademicHierarchySummary:
    from app.models.level import Level

    coverage = get_framework_coverage_metrics(db)
    offered_ids: set[int] = set()
    for country in coverage.by_country:
        offered_ids.update(country.program_ids)

    # Batched on purpose: per-level/per-program/per-major lookups became ~12k+
    # round trips after large program imports and stalled Framework Summary View.
    levels = (
        db.query(Level)
        .options(load_only(Level.id, Level.name))
        .order_by(Level.id.asc())
        .all()
    )
    programs = (
        db.query(Program)
        .options(load_only(Program.id, Program.name, Program.level_id, Program.sort_order))
        .filter(Program.is_active.is_(True))
        .order_by(Program.sort_order.asc(), Program.name.asc())
        .all()
    )
    mappings = (
        db.query(ProgramEducationMajorMapping)
        .options(
            load_only(
                ProgramEducationMajorMapping.id,
                ProgramEducationMajorMapping.program_id,
                ProgramEducationMajorMapping.education_major_id,
                ProgramEducationMajorMapping.education_sub_major_id,
            ),
            joinedload(ProgramEducationMajorMapping.education_major).load_only(
                EducationMajor.id,
                EducationMajor.label,
                EducationMajor.is_active,
            ),
        )
        .order_by(ProgramEducationMajorMapping.id.asc())
        .all()
    )

    majors_by_program: dict[int, dict[int, str]] = defaultdict(dict)
    sub_major_ids_by_program: dict[int, set[int]] = defaultdict(set)
    active_major_ids: set[int] = set()
    for mapping in mappings:
        major = mapping.education_major
        if not major or not major.is_active:
            continue
        majors_by_program[mapping.program_id][major.id] = major.label
        active_major_ids.add(major.id)
        sub_id = mapping.education_sub_major_id
        if sub_id is not None:
            sub_major_ids_by_program[mapping.program_id].add(int(sub_id))

    courses_by_major: dict[int, list[HierarchyCourseNode]] = defaultdict(list)
    if active_major_ids:
        course_rows = (
            db.query(
                CourseEducationMajorMapping.education_major_id,
                EducationCourse.id,
                EducationCourse.label,
                EducationCourse.code,
            )
            .join(
                EducationCourse,
                EducationCourse.id == CourseEducationMajorMapping.course_id,
            )
            .filter(
                CourseEducationMajorMapping.education_major_id.in_(active_major_ids),
                EducationCourse.is_active.is_(True),
            )
            .order_by(
                CourseEducationMajorMapping.education_major_id.asc(),
                EducationCourse.sort_order.asc(),
                EducationCourse.label.asc(),
            )
            .all()
        )
        for major_id, course_id, label, code in course_rows:
            courses_by_major[major_id].append(
                HierarchyCourseNode(id=course_id, name=label, code=code)
            )

    programs_by_level: dict[int, list[Program]] = defaultdict(list)
    for program in programs:
        if offered_ids and program.id not in offered_ids:
            continue
        programs_by_level[program.level_id].append(program)

    level_nodes: list[HierarchyLevelNode] = []
    for level in levels:
        level_programs = programs_by_level.get(level.id, [])
        program_nodes = [
            HierarchyProgramNode(
                id=program.id,
                name=program.name,
                majors=[
                    HierarchyMajorNode(
                        id=major_id,
                        name=major_name,
                        courses=list(courses_by_major.get(major_id, [])),
                    )
                    for major_id, major_name in majors_by_program.get(program.id, {}).items()
                ],
                sub_major_count=len(sub_major_ids_by_program.get(program.id, set())),
                sub_major_ids=sorted(sub_major_ids_by_program.get(program.id, set())),
            )
            for program in level_programs
        ]
        distinct_major_ids: set[int] = set()
        distinct_sub_major_ids: set[int] = set()
        for program in level_programs:
            distinct_major_ids.update(majors_by_program.get(program.id, {}))
            distinct_sub_major_ids.update(
                sub_major_ids_by_program.get(program.id, set())
            )
        level_nodes.append(
            HierarchyLevelNode(
                id=level.id,
                name=level.name,
                programs=program_nodes,
                major_count=len(distinct_major_ids),
                sub_major_count=len(distinct_sub_major_ids),
            )
        )

    return AcademicHierarchySummary(levels=level_nodes, coverage=coverage)


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
    """Count Academic Framework courses for a legacy target_program row.

    Do not count 1:1 `target_courses` clones of the parent qualification program.
    """
    qualification_id = (
        db.query(TargetProgram.program_id)
        .filter(TargetProgram.id == program_id)
        .scalar()
    )
    if qualification_id is None:
        return 0
    return int(
        db.query(func.count(EducationCourse.id))
        .filter(EducationCourse.program_id == qualification_id)
        .scalar()
        or 0
    )


def list_programs_admin(
    db: Session,
    *,
    query: str | None = None,
    degree_id: int | None = None,
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
    db: Session, *, degree_id: int, education_major_id: int
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
    degree_id: int | None = None,
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
    degree_id: int | None = None,
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


def get_course_admin(db: Session, course_id: int) -> EducationCourse | TargetCourse:
    try:
        return get_education_course(db, course_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    target = (
        db.query(TargetCourse)
        .options(
            joinedload(TargetCourse.qualification_program).joinedload(Program.level),
            joinedload(TargetCourse.education_major),
        )
        .filter(TargetCourse.id == course_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Course not found.")
    return target


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
