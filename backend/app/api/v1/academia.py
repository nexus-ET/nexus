from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_academia_admin
from app.db.database import get_db
from app.models.target_course import TargetCourse
from app.models.user import User
from app.schemas.education_major import (
    EducationMajorCreate,
    EducationMajorListResponse,
    EducationMajorRead,
    EducationMajorUpdate,
)
from app.schemas.education_sub_major import (
    EducationSubMajorCreate,
    EducationSubMajorListResponse,
    EducationSubMajorRead,
    EducationSubMajorUpdate,
)
from app.schemas.education_super_major import (
    EducationSuperMajorCreate,
    EducationSuperMajorListResponse,
    EducationSuperMajorRead,
    EducationSuperMajorUpdate,
)
from app.schemas.program_major_mapping import (
    EducationMajorBulkAssignRequest,
    EducationMajorBulkAssignResponse,
    NzProgramMappingSuggestionsResponse,
    CaProgramMappingSuggestionsResponse,
    ProgramMappingBulkApplyRequest,
    ProgramMappingBulkApplyResponse,
    ProgramMajorMappingListResponse,
)
from app.schemas.level import LevelCreate, LevelRead, LevelUpdate
from app.schemas.academia_hub import (
    AcademiaSearchResult,
    CampusCreate,
    CampusRead,
    CampusTypeRead,
    CampusUpdate,
    CollegeCreate,
    CollegeRead,
    CollegeUpdate,
    CountryAdminCreate,
    CountryAdminListResponse,
    CountryAdminRead,
    CountryAdminUpdate,
    DegreeAdminCreate,
    DegreeAdminListResponse,
    DegreeAdminRead,
    DegreeAdminUpdate,
    AcademicHierarchySummary,
    CourseAdminCreate,
    CourseAdminListResponse,
    CourseAdminRead,
    CourseAdminUpdate,
    GeographyCityCreate,
    GeographyCityListResponse,
    GeographyCityRead,
    GeographyCityUpdate,
    GeographyStateCreate,
    GeographyStateListResponse,
    GeographyStateRead,
    GeographyStateUpdate,
    INSTITUTION_PROFILE_TEXT_FIELD_NAMES,
    InstitutionalHierarchySummary,
    InstitutionAdminListResponse,
    InstitutionCreate,
    InstitutionRead,
    InstitutionSummaryRead,
    InstitutionTypeRead,
    InstitutionUpdate,
    ProgramAdminCreate,
    ProgramAdminRead,
    ProgramAdminUpdate,
)
from app.services import academia_hub_service as service

router = APIRouter()


def _country_read(row) -> CountryAdminRead:
    return CountryAdminRead.model_validate(row)


def _state_read(row) -> GeographyStateRead:
    return GeographyStateRead(
        id=row.id,
        country_id=row.country_id,
        name=row.name,
        region_code=row.region_code,
        is_active=row.is_active,
        sort_order=row.sort_order,
        country_name=row.country.name if row.country else None,
    )


def _city_read(row) -> GeographyCityRead:
    return GeographyCityRead(
        id=row.id,
        country_id=row.country_id,
        state_id=row.state_id,
        name=row.name,
        time_zone=row.time_zone,
        postal_code_prefix=row.postal_code_prefix,
        is_active=row.is_active,
        sort_order=row.sort_order,
        country_name=row.country.name if row.country else None,
        state_name=row.state.name if row.state else None,
        region_code=row.state.region_code if row.state else None,
    )


def _institution_profile_text(row) -> dict[str, str | None]:
    return {
        name: getattr(row, name, None) for name in INSTITUTION_PROFILE_TEXT_FIELD_NAMES
    }


def _institution_type_fields(row) -> dict[str, str | int | None]:
    institution_type = getattr(row, "institution_type_ref", None)
    return {
        "institution_type_id": row.institution_type_id,
        "institution_type_code": institution_type.code if institution_type else None,
        "institution_type_name": institution_type.name if institution_type else None,
    }


def _institution_read(
    row,
    *,
    campus_count: int | None = None,
    college_count: int | None = None,
) -> InstitutionRead:
    return InstitutionRead(
        id=row.id,
        country_id=row.country_id,
        name=row.name,
        code=row.code,
        accreditation_details=row.accreditation_details,
        is_active=row.is_active,
        sort_order=row.sort_order,
        country_name=row.country.name if row.country else None,
        campus_count=campus_count or 0,
        college_count=college_count or 0,
        **_institution_type_fields(row),
        **_institution_profile_text(row),
    )


def _normalize_institution_publish_status(
    publish_status: str | None,
    last_publish_attempt_at,
) -> str:
    """Never-attempted publishes must show as pending, not failure."""
    status = (publish_status or "pending").strip().lower() or "pending"
    if last_publish_attempt_at is None and status == "failure":
        return "pending"
    if status in {"pending", "success", "failure"}:
        return status
    return "pending"


def _clip_text(value: str | None, limit: int) -> str | None:
    """Clamp stored text so summary responses never fail schema max_length checks."""
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _institution_summary_read(
    row,
    *,
    metrics: dict[str, int] | None = None,
) -> InstitutionSummaryRead:
    resolved = metrics or {}
    return InstitutionSummaryRead(
        id=row.id,
        country_id=row.country_id,
        state_id=row.state_id,
        city_id=row.city_id,
        name=row.name,
        code=row.code,
        is_active=row.is_active,
        sort_order=row.sort_order,
        publish_status=_normalize_institution_publish_status(
            getattr(row, "publish_status", None),
            getattr(row, "last_publish_attempt_at", None),
        ),
        last_publish_attempt_at=getattr(row, "last_publish_attempt_at", None),
        country_name=row.country.name if row.country else None,
        state_name=row.state.name if row.state else None,
        city_name=row.city.name if row.city else None,
        campus_count=resolved.get("campus_count", 0),
        college_count=resolved.get("college_count", 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
        level_count=resolved.get("level_count", 0),
        program_count=resolved.get("program_count", 0),
        major_count=resolved.get("major_count", 0),
        sub_major_count=resolved.get("sub_major_count", 0),
        course_count=resolved.get("course_count", 0),
        intake_count=resolved.get("intake_count", 0),
        picture_count=resolved.get("picture_count", 0),
        **_institution_type_fields(row),
    )


def _campus_read(row) -> CampusRead:
    location_label = service._city_location_label(row.location) if row.location else None
    campus_type = row.campus_type_ref
    return CampusRead(
        id=row.id,
        institution_id=row.institution_id,
        location_id=row.location_id,
        name=row.name,
        campus_type_id=row.campus_type_id,
        campus_type_code=campus_type.code if campus_type else None,
        campus_type_name=campus_type.name if campus_type else None,
        campus_type_description=campus_type.description if campus_type else None,
        description=row.description,
        address=row.address,
        country_id=row.country_id,
        state_id=row.state_id,
        zipcode=row.zipcode,
        phone_numbers=row.phone_numbers or [],
        fax_numbers=row.fax_numbers or [],
        email_addresses=row.email_addresses or [],
        web_links=row.web_links or [],
        is_residential=row.is_residential,
        is_active=row.is_active,
        sort_order=row.sort_order,
        institution_name=row.institution.name if row.institution else None,
        location_name=row.location.name if row.location else None,
        location_label=location_label,
        country_name=row.country.name if getattr(row, "country", None) else None,
        state_name=row.state.name if getattr(row, "state", None) else None,
    )


def _college_read(row) -> CollegeRead:
    institution_name = row.institution.name if row.institution else None
    campus = getattr(row, "campus", None)
    campus_name = campus.name if campus else None
    campus_address = campus.address if campus else None
    campus_location_label = None
    if campus:
        location = getattr(campus, "location", None)
        location_name = location.name if location else None
        city = campus.city or location_name
        state = campus.state.name if getattr(campus, "state", None) else None
        country = campus.country.name if getattr(campus, "country", None) else None
        campus_location_label = ", ".join(
            part for part in [city, state, country] if part
        ) or None
    breadcrumb_parts = [part for part in [institution_name, campus_name, row.name] if part]
    linked_campuses = []
    for link in sorted(
        getattr(row, "campus_links", []) or [],
        key=lambda item: (not item.is_primary, item.campus.name if item.campus else ""),
    ):
        linked = link.campus
        if linked is None:
            continue
        linked_location = getattr(linked, "location", None)
        linked_location_label = ", ".join(
            part
            for part in [
                linked.city or (linked_location.name if linked_location else None),
                linked.state.name if getattr(linked, "state", None) else None,
                linked.country.name if getattr(linked, "country", None) else None,
            ]
            if part
        ) or None
        linked_campuses.append(
            {
                "campus_id": linked.id,
                "name": linked.name,
                "address": linked.address,
                "location_label": linked_location_label,
                "is_primary": link.is_primary,
                "source_url": link.source_url,
                "evidence": link.evidence,
            }
        )
    return CollegeRead(
        id=row.id,
        institution_id=row.institution_id,
        campus_id=row.campus_id,
        campus_ids=[item["campus_id"] for item in linked_campuses],
        linked_campuses=linked_campuses,
        name=row.name,
        code=row.code,
        category=row.category,
        dean_name=row.dean_name,
        web_url=row.web_url,
        web_links=row.web_links or [],
        phone_numbers=row.phone_numbers or [],
        email_addresses=row.email_addresses or [],
        is_active=row.is_active,
        sort_order=row.sort_order,
        institution_name=institution_name,
        campus_name=campus_name,
        campus_address=campus_address,
        campus_location_label=campus_location_label,
        hierarchy_breadcrumb=" > ".join(breadcrumb_parts) if breadcrumb_parts else None,
    )


def _degree_read(
    row,
    *,
    major_count: int | None = None,
    major_ids: list[int] | None = None,
    major_names: list[str] | None = None,
    sub_major_ids: list[int] | None = None,
    sub_major_names: list[str] | None = None,
    institution_id: int | None = None,
    institution_ids: list[int] | None = None,
    institution_names: list[str] | None = None,
    country_id: int | None = None,
    college_id: int | None = None,
    intake_ids: list[int] | None = None,
) -> DegreeAdminRead:
    level = getattr(row, "level", None)
    resolved_major_ids = major_ids or []
    resolved_institution_ids = institution_ids or []
    return DegreeAdminRead(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        program_url=getattr(row, "program_url", None),
        level_id=row.level_id,
        level_code=level.code if level else None,
        level_name=level.name if level else None,
        is_active=row.is_active,
        sort_order=row.sort_order,
        major_count=major_count if major_count is not None else len(resolved_major_ids),
        major_ids=resolved_major_ids,
        major_names=major_names or [],
        sub_major_ids=sub_major_ids or [],
        sub_major_names=sub_major_names or [],
        institution_id=institution_id if institution_id is not None else (
            resolved_institution_ids[0] if resolved_institution_ids else None
        ),
        institution_ids=resolved_institution_ids,
        institution_names=institution_names or [],
        country_id=country_id,
        college_id=college_id,
        intake_ids=intake_ids or [],
    )


def _degree_read_with_mappings(db: Session, row, **kwargs) -> DegreeAdminRead:
    payload = service.program_major_mapping_payloads(db, [row.id]).get(int(row.id), {})
    offering = service.program_offering_institution_payloads(db, [row.id]).get(int(row.id), {})
    merged = {**offering, **payload}
    merged["intake_ids"] = kwargs.get("intake_ids") or []
    if not merged.get("institution_id"):
        merged["institution_id"] = kwargs.get("institution_id")
        ids = merged.get("institution_ids") or []
        if not merged["institution_id"] and ids:
            merged["institution_id"] = ids[0]
    return _degree_read(row, **merged)


def _program_read(row, *, course_count: int | None = None) -> ProgramAdminRead:
    count = course_count if course_count is not None else 0
    parent_program = getattr(row, "program", None)
    level = getattr(parent_program, "level", None) if parent_program else None
    return ProgramAdminRead(
        id=row.id,
        program_id=row.program_id,
        degree_id=row.program_id,
        code=row.code,
        label=row.label,
        name=row.label,
        description=row.description,
        degree_name=parent_program.name if parent_program else None,
        level_id=parent_program.level_id if parent_program else None,
        level_code=level.code if level else None,
        level_name=level.name if level else None,
        is_active=row.is_active,
        sort_order=row.sort_order,
        course_count=count,
    )


def _target_course_read(row: TargetCourse) -> CourseAdminRead:
    program = row.qualification_program
    program_name = program.name if program else None
    major = row.education_major
    major_name = major.label if major else None
    major_id = row.education_major_id
    level_obj = program.level if program else None
    level_name = level_obj.name if level_obj else None
    breadcrumb_parts = [part for part in [level_name, program_name, major_name] if part]
    return CourseAdminRead(
        id=row.id,
        program_id=0,
        major_id=major_id,
        major_ids=[major_id] if major_id else [],
        degree_id=row.qualification_program_id,
        level_id=program.level_id if program else None,
        code=row.code,
        description=None,
        label=row.label,
        name=row.label,
        level=row.level,
        is_active=row.is_active,
        sort_order=row.sort_order or 0,
        program_code=program.code if program else None,
        program_label=program_name,
        program_name=program_name,
        major_name=major_name,
        major_names=[major_name] if major_name else [],
        degree_name=program_name,
        hierarchy_breadcrumb=" > ".join(breadcrumb_parts) if breadcrumb_parts else None,
    )


def _course_read(row) -> CourseAdminRead:
    if isinstance(row, TargetCourse):
        return _target_course_read(row)
    program_name = row.program.name if row.program else None
    program_id = row.program_id
    mappings = getattr(row, "education_major_mappings", None) or []
    mapped_majors = [
        mapping.education_major
        for mapping in mappings
        if getattr(mapping, "education_major", None) is not None
    ]
    major_ids = [major.id for major in mapped_majors]
    major_names = [major.label for major in mapped_majors]
    if not major_ids and row.education_major_id:
        major_ids = [row.education_major_id]
    if not major_names and row.education_major:
        major_names = [row.education_major.label]
    major_name = ", ".join(major_names) if major_names else None
    major_id = major_ids[0] if major_ids else row.education_major_id
    level_name = None
    if getattr(row, "level", None):
        level_name = row.level.name
    elif row.program and row.program.level:
        level_name = row.program.level.name

    breadcrumb_parts = [
        part for part in [level_name, program_name, major_name] if part
    ]
    return CourseAdminRead(
        id=row.id,
        program_id=0,
        major_id=major_id,
        major_ids=major_ids,
        degree_id=program_id,
        level_id=getattr(row, "level_id", None),
        code=row.code,
        description=row.description,
        label=row.label,
        name=row.label,
        level=row.course_level,
        is_active=row.is_active,
        sort_order=row.sort_order,
        program_code=row.program.code if row.program else None,
        program_label=row.program.name if row.program else None,
        program_name=program_name,
        major_name=major_name,
        major_names=major_names,
        degree_name=program_name,
        hierarchy_breadcrumb=" > ".join(breadcrumb_parts) if breadcrumb_parts else None,
    )


@router.get("/academia/search", response_model=list[AcademiaSearchResult])
def search_academia(
    q: str = Query("", min_length=0, max_length=120),
    limit: int = Query(25, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return service.search_academia_entities(db, q, limit=limit)


@router.get("/academia/countries", response_model=CountryAdminListResponse)
def list_countries(
    q: str | None = Query(None, max_length=120),
    active_only: bool = Query(False),
    with_institutions: bool = Query(
        False,
        description="When true, only countries with at least one institution are returned.",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|iso2|dial_code|sort_order|is_active|id)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_countries_admin(
        db,
        query=q,
        active_only=active_only,
        with_institutions=with_institutions,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return CountryAdminListResponse(
        items=[_country_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/countries", response_model=CountryAdminRead)
def create_country(
    payload: CountryAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _country_read(service.create_country_admin(db, payload))


@router.get("/academia/countries/{country_id}", response_model=CountryAdminRead)
def get_country(
    country_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _country_read(service.get_country_admin(db, country_id))


@router.put("/academia/countries/{country_id}", response_model=CountryAdminRead)
def update_country(
    country_id: int,
    payload: CountryAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _country_read(service.update_country_admin(db, country_id, payload))


@router.delete("/academia/countries/{country_id}")
def delete_country(
    country_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_country_admin(db, country_id)
    return {"ok": True}


@router.get("/academia/timezones", response_model=list[str])
def list_timezones(
    q: str | None = Query(None, max_length=120),
    _: User = Depends(require_academia_admin),
):
    from app.services.iana_timezones import IANA_TIME_ZONES

    if not q or not q.strip():
        return IANA_TIME_ZONES
    needle = q.strip().lower()
    return [zone for zone in IANA_TIME_ZONES if needle in zone.lower()]


@router.get("/academia/states", response_model=GeographyStateListResponse)
def list_states(
    q: str | None = Query(None, max_length=120),
    country_id: int | None = Query(None, ge=1),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "name", pattern="^(name|region_code|country|sort_order|is_active|id)$"
    ),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_states_admin(
        db,
        query=q,
        country_id=country_id,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return GeographyStateListResponse(
        items=[_state_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/states", response_model=GeographyStateRead)
def create_state(
    payload: GeographyStateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _state_read(service.create_state_admin(db, payload))


@router.get("/academia/states/{state_id}", response_model=GeographyStateRead)
def get_state(
    state_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _state_read(service.get_state_admin(db, state_id))


@router.put("/academia/states/{state_id}", response_model=GeographyStateRead)
def update_state(
    state_id: int,
    payload: GeographyStateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _state_read(service.update_state_admin(db, state_id, payload))


@router.delete("/academia/states/{state_id}")
def delete_state(
    state_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_state_admin(db, state_id)
    return {"ok": True}


@router.get("/academia/cities", response_model=GeographyCityListResponse)
def list_cities(
    q: str | None = Query(None, max_length=120),
    country_id: int | None = Query(None, ge=1),
    state_id: int | None = Query(None, ge=1),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "name", pattern="^(name|country|state|time_zone|sort_order|is_active|id)$"
    ),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_cities_admin(
        db,
        query=q,
        country_id=country_id,
        state_id=state_id,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return GeographyCityListResponse(
        items=[_city_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/cities", response_model=GeographyCityRead)
def create_city(
    payload: GeographyCityCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _city_read(service.create_city_admin(db, payload))


@router.get("/academia/cities/{city_id}", response_model=GeographyCityRead)
def get_city(
    city_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _city_read(service.get_city_admin(db, city_id))


@router.put("/academia/cities/{city_id}", response_model=GeographyCityRead)
def update_city(
    city_id: int,
    payload: GeographyCityUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _city_read(service.update_city_admin(db, city_id, payload))


@router.delete("/academia/cities/{city_id}")
def delete_city(
    city_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_city_admin(db, city_id)
    return {"ok": True}


@router.get("/academia/institutions", response_model=list[InstitutionRead])
def list_institutions(
    q: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows = service.list_institutions_admin(db, query=q)
    counts = service.institution_hierarchy_counts(db, [row.id for row in rows])
    return [
        _institution_read(
            row,
            campus_count=counts.get(row.id, (0, 0))[0],
            college_count=counts.get(row.id, (0, 0))[1],
        )
        for row in rows
    ]


# Per-item constraints for list query params. Putting ge= on Query() for list[int]
# makes Pydantic apply ge to the whole list (TypeError → HTTP 500).
_SummaryIdList = Annotated[list[Annotated[int, Query(ge=1)]] | None, Query()]


@router.get("/academia/institutions/summary", response_model=InstitutionAdminListResponse)
def list_institutions_summary(
    q: str | None = Query(None, max_length=120, description="Search institution names"),
    country_id: _SummaryIdList = None,
    state_id: _SummaryIdList = None,
    city_id: _SummaryIdList = None,
    is_active: bool | None = Query(None, description="Filter by active/inactive status"),
    institution_type_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(description="Filter by institution type id"),
    ] = None,
    program_id: list[int] | None = Query(None, description="Filter institutions offering courses under these programs"),
    major_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(description="Filter institutions offering courses under these majors"),
    ] = None,
    sub_major_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(
            description="Filter institutions offering programs mapped to these education sub-majors",
        ),
    ] = None,
    template_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(description="Filter institutions using these academic templates"),
    ] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "created_at",
        pattern=(
            "^(name|city|state|country|created_at|code|institution_type_id|institution_type|status|sort_order|id|"
            "level_count|program_count|major_count|sub_major_count|course_count|campus_count|college_count|intake_count)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_institutions_summary_admin(
        db,
        query=q,
        country_ids=country_id,
        state_ids=state_id,
        city_ids=city_id,
        is_active=is_active,
        institution_type_ids=institution_type_id,
        program_ids=program_id,
        major_ids=major_id,
        sub_major_ids=sub_major_id,
        template_ids=template_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    active_count, inactive_count = service.get_institution_status_counts(db)
    metrics = service.institution_summary_metrics(db, [row.id for row in rows])
    return InstitutionAdminListResponse(
        items=[
            _institution_summary_read(row, metrics=metrics.get(row.id))
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        active_count=active_count,
        inactive_count=inactive_count,
    )


@router.get("/academia/institutions/hierarchy", response_model=InstitutionalHierarchySummary)
def get_institutional_hierarchy(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return service.get_institutional_hierarchy_summary(db)


@router.post("/academia/institutions", response_model=InstitutionRead)
def create_institution(
    payload: InstitutionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _institution_read(
        service.create_institution_admin(db, payload),
        campus_count=0,
        college_count=0,
    )


@router.get("/academia/institutions/{institution_id}", response_model=InstitutionRead)
def get_institution(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.get_institution_admin(db, institution_id)
    return _institution_read(
        row,
        campus_count=service._institution_campus_count(db, institution_id),
        college_count=service._institution_college_count(db, institution_id),
    )


@router.put("/academia/institutions/{institution_id}", response_model=InstitutionRead)
def update_institution(
    institution_id: int,
    payload: InstitutionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.update_institution_admin(db, institution_id, payload)
    return _institution_read(
        row,
        campus_count=service._institution_campus_count(db, institution_id),
        college_count=service._institution_college_count(db, institution_id),
    )


@router.delete("/academia/institutions/{institution_id}")
def delete_institution(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_institution_admin(db, institution_id)
    return {"ok": True}


@router.get("/academia/campus-types", response_model=list[CampusTypeRead])
def list_campus_types(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return [
        CampusTypeRead.model_validate(row)
        for row in service.list_campus_types_admin(db)
    ]


@router.get("/academia/institution-types", response_model=list[InstitutionTypeRead])
def list_institution_types(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return [
        InstitutionTypeRead.model_validate(row)
        for row in service.list_institution_types_admin(db)
    ]


@router.get("/academia/campuses", response_model=list[CampusRead])
def list_campuses(
    q: str | None = Query(None, max_length=120),
    institution_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return [
        _campus_read(row)
        for row in service.list_campuses_admin(db, query=q, institution_id=institution_id)
    ]


@router.post("/academia/campuses", response_model=CampusRead)
def create_campus(
    payload: CampusCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _campus_read(service.create_campus_admin(db, payload))


@router.get("/academia/campuses/{campus_id}", response_model=CampusRead)
def get_campus(
    campus_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _campus_read(service.get_campus_admin(db, campus_id))


@router.put("/academia/campuses/{campus_id}", response_model=CampusRead)
def update_campus(
    campus_id: int,
    payload: CampusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _campus_read(service.update_campus_admin(db, campus_id, payload))


@router.delete("/academia/campuses/{campus_id}")
def delete_campus(
    campus_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_campus_admin(db, campus_id)
    return {"ok": True}


@router.get("/academia/colleges", response_model=list[CollegeRead])
def list_colleges(
    q: str | None = Query(None, max_length=120),
    institution_id: int | None = Query(None, ge=1),
    campus_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return [
        _college_read(row)
        for row in service.list_colleges_admin(
            db,
            query=q,
            institution_id=institution_id,
            campus_id=campus_id,
        )
    ]


@router.post("/academia/colleges", response_model=CollegeRead)
def create_college(
    payload: CollegeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _college_read(service.create_college_admin(db, payload))


@router.get("/academia/colleges/{college_id}", response_model=CollegeRead)
def get_college(
    college_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _college_read(service.get_college_admin(db, college_id))


@router.put("/academia/colleges/{college_id}", response_model=CollegeRead)
def update_college(
    college_id: int,
    payload: CollegeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _college_read(service.update_college_admin(db, college_id, payload))


@router.delete("/academia/colleges/{college_id}")
def delete_college(
    college_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_college_admin(db, college_id)
    return {"ok": True}


@router.get("/academia/levels", response_model=list[LevelRead])
def list_levels(
    q: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import levels as level_service

    return level_service.list_levels(db, query=q)


@router.post("/academia/levels", response_model=LevelRead)
def create_level(
    payload: LevelCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import levels as level_service

    return level_service.create_level(db, payload)


@router.get("/academia/levels/{level_id}", response_model=LevelRead)
def get_level(
    level_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import levels as level_service

    record = level_service.get_level(db, level_id)
    if not record:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Level not found.")
    return record


@router.put("/academia/levels/{level_id}", response_model=LevelRead)
def update_level(
    level_id: int,
    payload: LevelUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import levels as level_service

    return level_service.update_level(db, level_id, payload)


@router.delete("/academia/levels/{level_id}")
def delete_level(
    level_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import levels as level_service

    level_service.delete_level(db, level_id)
    return {"ok": True}


@router.get("/academia/education-majors", response_model=EducationMajorListResponse)
def list_education_majors_admin(
    q: str | None = Query(None, max_length=120),
    level_id: int | None = Query(None, ge=1),
    program_id: int | None = Query(None, description="Parent qualification program (programs.id)"),
    super_major_id: int | None = Query(None, ge=1, description="education_super_majors.id"),
    catalog_only: bool = Query(True, description="Return only catalog majors (not program clones)"),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "name",
        pattern="^(name|code|program|level|id|sort_order|super_major)$",
    ),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_majors as major_service

    rows, total = major_service.list_education_majors_read(
        db,
        query=q,
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
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return EducationMajorListResponse(
        items=rows,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/education-majors", response_model=EducationMajorRead)
def create_education_major_admin(
    payload: EducationMajorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_majors as major_service

    return major_service.create_education_major(db, payload)


@router.post(
    "/academia/education-majors/bulk-assign",
    response_model=EducationMajorBulkAssignResponse,
)
def bulk_assign_education_majors_admin(
    payload: EducationMajorBulkAssignRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import program_major_mappings as mapping_service

    result = mapping_service.bulk_assign_major_to_programs(
        db,
        major_id=payload.major_id,
        program_ids=payload.program_ids,
    )
    return EducationMajorBulkAssignResponse(**result)


@router.get(
    "/academia/program-major-mappings",
    response_model=ProgramMajorMappingListResponse,
)
def list_program_major_mappings_admin(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import program_major_mappings as mapping_service

    return ProgramMajorMappingListResponse(items=mapping_service.list_program_major_mappings_read(db))


@router.get(
    "/academia/nz-program-mapping-suggestions",
    response_model=NzProgramMappingSuggestionsResponse,
)
def list_nz_program_mapping_suggestions_admin(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import nz_program_mapping_review as review_service

    return review_service.list_nz_program_mapping_suggestions(db)


@router.get(
    "/academia/ca-program-mapping-suggestions",
    response_model=CaProgramMappingSuggestionsResponse,
)
def list_ca_program_mapping_suggestions_admin(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import ca_program_mapping_review as review_service

    return review_service.list_ca_program_mapping_suggestions(db)


@router.post(
    "/academia/program-mappings/bulk-apply",
    response_model=ProgramMappingBulkApplyResponse,
)
def bulk_apply_program_mappings_admin(
    payload: ProgramMappingBulkApplyRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import nz_program_mapping_review as review_service

    return review_service.bulk_apply_program_mappings(
        db,
        payload.items,
        nz_scope_only=payload.nz_scope_only,
        ca_scope_only=payload.ca_scope_only,
    )


@router.get("/academia/education-majors/{major_id}", response_model=EducationMajorRead)
def get_education_major_admin(
    major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_majors as major_service

    record = major_service.get_education_major(db, major_id)
    if not record:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Major not found.")
    return major_service.education_major_to_read(db, record)


@router.put("/academia/education-majors/{major_id}", response_model=EducationMajorRead)
def update_education_major_admin(
    major_id: int,
    payload: EducationMajorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_majors as major_service

    return major_service.update_education_major(db, major_id, payload)


@router.delete("/academia/education-majors/{major_id}")
def delete_education_major_admin(
    major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_majors as major_service

    major_service.delete_education_major(db, major_id)
    return {"ok": True}


@router.get("/academia/education-sub-majors", response_model=EducationSubMajorListResponse)
def list_education_sub_majors_admin(
    q: str | None = Query(None, max_length=120),
    major_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|major|id)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_sub_majors as sub_major_service

    rows, total = sub_major_service.list_education_sub_majors_read(
        db,
        query=q,
        major_id=major_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return EducationSubMajorListResponse(
        items=rows,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/education-sub-majors", response_model=EducationSubMajorRead)
def create_education_sub_major_admin(
    payload: EducationSubMajorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_sub_majors as sub_major_service

    return sub_major_service.create_education_sub_major(db, payload)


@router.get("/academia/education-sub-majors/{sub_major_id}", response_model=EducationSubMajorRead)
def get_education_sub_major_admin(
    sub_major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from fastapi import HTTPException

    from app.services import education_sub_majors as sub_major_service

    record = sub_major_service.get_education_sub_major(db, sub_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Sub-major not found.")
    return sub_major_service.education_sub_major_read(db, record)


@router.put("/academia/education-sub-majors/{sub_major_id}", response_model=EducationSubMajorRead)
def update_education_sub_major_admin(
    sub_major_id: int,
    payload: EducationSubMajorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_sub_majors as sub_major_service

    return sub_major_service.update_education_sub_major(db, sub_major_id, payload)


@router.delete("/academia/education-sub-majors/{sub_major_id}")
def delete_education_sub_major_admin(
    sub_major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_sub_majors as sub_major_service

    sub_major_service.delete_education_sub_major(db, sub_major_id)
    return {"ok": True}


@router.get(
    "/academia/education-super-majors",
    response_model=EducationSuperMajorListResponse,
)
def list_education_super_majors_admin(
    q: str | None = Query(None, max_length=120),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("sort_order", pattern="^(name|code|sort_order|id)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_super_majors as super_major_service

    rows, total = super_major_service.list_education_super_majors_read(
        db,
        query=q,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return EducationSuperMajorListResponse(
        items=rows,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post(
    "/academia/education-super-majors",
    response_model=EducationSuperMajorRead,
)
def create_education_super_major_admin(
    payload: EducationSuperMajorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_super_majors as super_major_service

    return super_major_service.create_education_super_major(db, payload)


@router.get(
    "/academia/education-super-majors/{super_major_id}",
    response_model=EducationSuperMajorRead,
)
def get_education_super_major_admin(
    super_major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from fastapi import HTTPException

    from app.services import education_super_majors as super_major_service

    record = super_major_service.get_education_super_major(db, super_major_id)
    if not record:
        raise HTTPException(status_code=404, detail="Super-major not found.")
    return super_major_service.education_super_major_read(db, record)


@router.put(
    "/academia/education-super-majors/{super_major_id}",
    response_model=EducationSuperMajorRead,
)
def update_education_super_major_admin(
    super_major_id: int,
    payload: EducationSuperMajorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_super_majors as super_major_service

    return super_major_service.update_education_super_major(db, super_major_id, payload)


@router.delete("/academia/education-super-majors/{super_major_id}")
def delete_education_super_major_admin(
    super_major_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services import education_super_majors as super_major_service

    super_major_service.delete_education_super_major(db, super_major_id)
    return {"ok": True}


@router.get("/academia/hierarchy/status-impact")
def get_hierarchy_status_impact(
    entity_type: str = Query(..., pattern="^(level|major|program|course)$"),
    entity_id: str = Query(..., min_length=1),
    is_active: bool = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.hierarchy_status_impact import (
        HierarchyEntityType,
        get_hierarchy_status_impact as resolve_impact,
    )

    return resolve_impact(
        db,
        entity_type=HierarchyEntityType(entity_type),
        entity_id=entity_id,
        proposed_is_active=is_active,
    )


@router.get("/academia/geography/status-impact")
def get_geography_status_impact(
    entity_type: str = Query(..., pattern="^(country|state|city)$"),
    entity_id: int = Query(..., ge=1),
    is_active: bool = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.geography_status_impact import (
        GeographyEntityType,
        get_geography_status_impact as resolve_impact,
    )

    return resolve_impact(
        db,
        entity_type=GeographyEntityType(entity_type),
        entity_id=entity_id,
        proposed_is_active=is_active,
    )


@router.get("/academia/hierarchy", response_model=AcademicHierarchySummary)
def get_academic_hierarchy(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return service.get_academic_hierarchy_summary(db)


@router.get("/academia/degrees", response_model=DegreeAdminListResponse)
def list_degrees(
    q: str | None = Query(None, max_length=120),
    level_id: int | None = Query(None, ge=1),
    major_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(description="Filter programs mapped to these catalog majors"),
    ] = None,
    sub_major_id: Annotated[
        list[Annotated[int, Query(ge=1)]] | None,
        Query(description="Filter programs mapped to these catalog sub-majors"),
    ] = None,
    country_id: _SummaryIdList = None,
    institution_id: _SummaryIdList = None,
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|code|level|id|sort_order)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_degrees_admin(
        db,
        query=q,
        level_id=level_id,
        major_ids=major_id,
        sub_major_ids=sub_major_id,
        country_ids=country_id,
        institution_ids=institution_id,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    program_ids = [row.id for row in rows]
    mapping_by_program = service.program_major_mapping_payloads(db, program_ids)
    institutions_by_program = service.program_offering_institution_payloads(db, program_ids)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return DegreeAdminListResponse(
        items=[
            _degree_read(
                row,
                **mapping_by_program.get(int(row.id), {}),
                **institutions_by_program.get(int(row.id), {}),
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/degrees", response_model=DegreeAdminRead)
def create_degree(
    payload: DegreeAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.academic_calendar_service import enrich_degree_with_intakes

    row = service.create_degree_admin(db, payload)
    intake_meta = enrich_degree_with_intakes(db, row)
    return _degree_read_with_mappings(
        db,
        row,
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.get("/academia/degrees/{degree_id}", response_model=DegreeAdminRead)
def get_degree(
    degree_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.academic_calendar_service import enrich_degree_with_intakes

    row = service.get_degree_admin(db, degree_id)
    intake_meta = enrich_degree_with_intakes(db, row)
    return _degree_read_with_mappings(
        db,
        row,
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.put("/academia/degrees/{degree_id}", response_model=DegreeAdminRead)
def update_degree(
    degree_id: int,
    payload: DegreeAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.academic_calendar_service import enrich_degree_with_intakes

    row = service.update_degree_admin(db, degree_id, payload)
    intake_meta = enrich_degree_with_intakes(db, row)
    return _degree_read_with_mappings(
        db,
        row,
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.delete("/academia/degrees/{degree_id}")
def delete_degree(
    degree_id: int,
    institution_id: int | None = Query(
        None,
        ge=1,
        description="When set, remove this institution's offering only if others remain",
    ),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_degree_admin(db, degree_id, institution_id=institution_id)
    return {"ok": True}


@router.get("/academia/programs", response_model=list[ProgramAdminRead])
def list_programs(
    q: str | None = Query(None, max_length=120),
    degree_id: int | None = Query(None, description="Parent qualification program id (programs.id)"),
    program_id: int | None = Query(
        None, description="Alias for degree_id — parent qualification program id"
    ),
    level_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """Legacy target_programs (disciplines). Framework qualifications use /academia/degrees."""
    parent_program_id = program_id or degree_id
    rows = service.list_programs_admin(
        db, query=q, degree_id=parent_program_id, level_id=level_id
    )
    return [
        _program_read(row, course_count=service._program_course_count(db, row.id))
        for row in rows
    ]


@router.get("/academia/majors", response_model=list[ProgramAdminRead])
def list_majors(
    q: str | None = Query(None, max_length=120),
    program_id: int | None = Query(
        None, description="Parent qualification program id (programs.id)"
    ),
    degree_id: int | None = Query(None, description="Alias for program_id"),
    level_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    """List framework majors/disciplines from target_programs (not programs or education_majors)."""
    parent_program_id = program_id or degree_id
    rows = service.list_programs_admin(
        db, query=q, degree_id=parent_program_id, level_id=level_id
    )
    return [
        _program_read(row, course_count=service._program_course_count(db, row.id))
        for row in rows
    ]


@router.post("/academia/programs", response_model=ProgramAdminRead)
def create_program(
    payload: ProgramAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _program_read(
        service.create_program_admin(db, payload),
        course_count=0,
    )


@router.get("/academia/programs/{program_id}", response_model=ProgramAdminRead)
def get_program(
    program_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    row = service.get_program_admin(db, program_id)
    return _program_read(row, course_count=service._program_course_count(db, program_id))


@router.get("/academia/programs/{program_id}/courses", response_model=list[CourseAdminRead])
def list_program_courses(
    program_id: int,
    q: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.get_program_admin(db, program_id)
    return [
        _course_read(row)
        for row in service.list_courses_admin_all(db, query=q, program_id=program_id)
    ]


@router.put("/academia/programs/{program_id}", response_model=ProgramAdminRead)
def update_program(
    program_id: int,
    payload: ProgramAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _program_read(
        service.update_program_admin(db, program_id, payload),
        course_count=service._program_course_count(db, program_id),
    )


@router.delete("/academia/programs/{program_id}")
def delete_program(
    program_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_program_admin(db, program_id)
    return {"ok": True}


@router.get("/academia/courses", response_model=CourseAdminListResponse)
def list_courses(
    q: str | None = Query(None, max_length=120),
    program_id: int | None = Query(
        None, ge=1, description="Legacy major id (target_programs.id)"
    ),
    major_id: int | None = Query(None, ge=1, description="education_majors.id"),
    degree_id: int | None = Query(None, description="Parent qualification program id"),
    level_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|code|level|id|sort_order)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_courses_admin(
        db,
        query=q,
        program_id=program_id,
        major_id=major_id,
        degree_id=degree_id,
        level_id=level_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return CourseAdminListResponse(
        items=[_course_read(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("/academia/courses", response_model=CourseAdminRead)
def create_course(
    payload: CourseAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _course_read(service.create_course_admin(db, payload))


@router.get("/academia/courses/{course_id}", response_model=CourseAdminRead)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _course_read(service.get_course_admin(db, course_id))


@router.put("/academia/courses/{course_id}", response_model=CourseAdminRead)
def update_course(
    course_id: int,
    payload: CourseAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return _course_read(service.update_course_admin(db, course_id, payload))


@router.delete("/academia/courses/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_course_admin(db, course_id)
    return {"ok": True}
