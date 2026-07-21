from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_academia_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.education_major import (
    EducationMajorCreate,
    EducationMajorListResponse,
    EducationMajorRead,
    EducationMajorUpdate,
)
from app.schemas.program_major_mapping import (
    EducationMajorBulkAssignRequest,
    EducationMajorBulkAssignResponse,
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
    InstitutionalHierarchySummary,
    InstitutionAdminListResponse,
    InstitutionCreate,
    InstitutionRead,
    InstitutionSummaryRead,
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
        institution_type=row.institution_type,
        accreditation_details=row.accreditation_details,
        is_active=row.is_active,
        sort_order=row.sort_order,
        country_name=row.country.name if row.country else None,
        campus_count=campus_count or 0,
        college_count=college_count or 0,
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


def _institution_summary_read(
    row,
    db: Session,
    *,
    campus_count: int | None = None,
    college_count: int | None = None,
) -> InstitutionSummaryRead:
    return InstitutionSummaryRead(
        id=row.id,
        country_id=row.country_id,
        state_id=row.state_id,
        city_id=row.city_id,
        zipcode=row.zipcode,
        name=row.name,
        code=row.code,
        institution_type=row.institution_type,
        company_affiliated=row.company_affiliated,
        ranking_tier_global=row.ranking_tier_global,
        ad_promotion_flag=row.ad_promotion_flag,
        institution_web_url=row.institution_web_url,
        currency_type=row.currency_type,
        students_count=row.students_count,
        accreditation_details=row.accreditation_details,
        short_description=row.short_description,
        long_description=row.long_description,
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
        campus_count=campus_count or 0,
        college_count=college_count or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
        level_count=service._institution_level_count(db, row.id),
        program_count=service._institution_program_count(db, row.id),
        major_count=service._institution_major_count(db, row.id),
        course_count=service._institution_course_count(db, row.id),
        intake_count=service._institution_intake_count(db, row.id),
        picture_count=service._institution_picture_count(db, row.id),
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
    return CollegeRead(
        id=row.id,
        institution_id=row.institution_id,
        campus_id=row.campus_id,
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
    institution_id: int | None = None,
    intake_ids: list[int] | None = None,
) -> DegreeAdminRead:
    level = getattr(row, "level", None)
    resolved_major_ids = major_ids or []
    return DegreeAdminRead(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        level_id=row.level_id,
        level_code=level.code if level else None,
        level_name=level.name if level else None,
        is_active=row.is_active,
        sort_order=row.sort_order,
        major_count=major_count if major_count is not None else len(resolved_major_ids),
        major_ids=resolved_major_ids,
        institution_id=institution_id,
        intake_ids=intake_ids or [],
    )


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


def _course_read(row) -> CourseAdminRead:
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
    return [
        _institution_read(
            row,
            campus_count=service._institution_campus_count(db, row.id),
            college_count=service._institution_college_count(db, row.id),
        )
        for row in service.list_institutions_admin(db, query=q)
    ]


@router.get("/academia/institutions/summary", response_model=InstitutionAdminListResponse)
def list_institutions_summary(
    q: str | None = Query(None, max_length=120, description="Search institution names"),
    country_id: int | None = Query(None, ge=1),
    state_id: int | None = Query(None, ge=1),
    city_id: int | None = Query(None, ge=1),
    is_active: bool | None = Query(None, description="Filter by active/inactive status"),
    institution_type: str | None = Query(None, max_length=80, description="Institution type / program type"),
    program_id: UUID | None = Query(None, description="Filter institutions offering courses under this program"),
    major_id: int | None = Query(None, ge=1, description="Filter institutions offering courses under this major"),
    template_id: int | None = Query(None, ge=1, description="Filter institutions using this academic template"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "created_at",
        pattern=(
            "^(name|city|state|country|created_at|code|institution_type|status|sort_order|id|"
            "program_count|major_count|course_count|campus_count|college_count|intake_count)$"
        ),
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    rows, total = service.list_institutions_summary_admin(
        db,
        query=q,
        country_id=country_id,
        state_id=state_id,
        city_id=city_id,
        is_active=is_active,
        institution_type=institution_type,
        program_id=program_id,
        major_id=major_id,
        template_id=template_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    active_count, inactive_count = service.get_institution_status_counts(db)
    return InstitutionAdminListResponse(
        items=[
            _institution_summary_read(
                row,
                db,
                campus_count=service._institution_campus_count(db, row.id),
                college_count=service._institution_college_count(db, row.id),
            )
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
    program_id: UUID | None = Query(None, description="Parent qualification program (programs.id)"),
    catalog_only: bool = Query(True, description="Return only catalog majors (not program clones)"),
    active_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("name", pattern="^(name|code|program|level|id|sort_order)$"),
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
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    return DegreeAdminListResponse(
        items=[
            _degree_read(
                row,
                major_ids=service._degree_major_ids(db, row.id),
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
    return _degree_read(
        row,
        major_ids=service._degree_major_ids(db, row.id),
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.get("/academia/degrees/{degree_id}", response_model=DegreeAdminRead)
def get_degree(
    degree_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.academic_calendar_service import enrich_degree_with_intakes

    row = service.get_degree_admin(db, degree_id)
    intake_meta = enrich_degree_with_intakes(db, row)
    return _degree_read(
        row,
        major_ids=service._degree_major_ids(db, degree_id),
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.put("/academia/degrees/{degree_id}", response_model=DegreeAdminRead)
def update_degree(
    degree_id: UUID,
    payload: DegreeAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    from app.services.academic_calendar_service import enrich_degree_with_intakes

    row = service.update_degree_admin(db, degree_id, payload)
    intake_meta = enrich_degree_with_intakes(db, row)
    return _degree_read(
        row,
        major_ids=service._degree_major_ids(db, degree_id),
        institution_id=intake_meta["institution_id"],
        intake_ids=intake_meta["intake_ids"],
    )


@router.delete("/academia/degrees/{degree_id}")
def delete_degree(
    degree_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    service.delete_degree_admin(db, degree_id)
    return {"ok": True}


@router.get("/academia/programs", response_model=list[ProgramAdminRead])
def list_programs(
    q: str | None = Query(None, max_length=120),
    degree_id: UUID | None = Query(None, description="Parent qualification program UUID (programs.id)"),
    program_id: UUID | None = Query(
        None, description="Alias for degree_id — parent qualification program UUID"
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
    program_id: UUID | None = Query(
        None, description="Parent qualification program UUID (programs.id)"
    ),
    degree_id: UUID | None = Query(None, description="Alias for program_id"),
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
    degree_id: UUID | None = Query(None, description="Parent qualification program UUID"),
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
