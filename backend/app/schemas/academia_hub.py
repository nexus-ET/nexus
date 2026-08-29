from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.contact_entry import (
    ContactEntry,
    ContactListFields,
    EmailContactListMixin,
    FaxContactListFields,
    OptionalEmailContactListMixin,
    OptionalPhoneContactListMixin,
    PhoneContactListMixin,
    assert_optional_email_formats,
    normalize_email_contacts,
    normalize_fax_contacts,
    normalize_phone_contacts,
    normalize_web_links,
    primary_web_url,
    serialize_contacts,
)
from app.schemas.rich_text import OptionalRichText5000


class CampusTypeRead(BaseModel):
    id: int
    code: str
    name: str
    description: str
    model_config = ConfigDict(from_attributes=True)


class InstitutionTypeRead(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool = True
    sort_order: int = 0
    model_config = ConfigDict(from_attributes=True)


class CountryAdminBase(BaseModel):
    iso2: str = Field(min_length=2, max_length=2)
    name: str = Field(min_length=1, max_length=100)
    dial_code: str = Field(min_length=1, max_length=6)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("iso2")
    @classmethod
    def normalize_iso2(cls, value: str) -> str:
        return value.strip().upper()


class CountryAdminCreate(CountryAdminBase):
    iso_code: str | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="before")
    @classmethod
    def map_iso_code(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("iso_code") and not data.get("iso2"):
            data = {**data, "iso2": data["iso_code"]}
        return data


class CountryAdminUpdate(BaseModel):
    iso2: str | None = Field(default=None, min_length=2, max_length=2)
    iso_code: str | None = Field(default=None, min_length=2, max_length=2)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    dial_code: str | None = Field(default=None, min_length=1, max_length=6)
    is_active: bool | None = None
    sort_order: int | None = None

    @model_validator(mode="before")
    @classmethod
    def map_iso_code(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("iso_code") and not data.get("iso2"):
            data = {**data, "iso2": data["iso_code"]}
        return data


class CountryAdminRead(CountryAdminBase):
    id: int
    iso_code: str | None = None

    @model_validator(mode="after")
    def populate_iso_code(self) -> "CountryAdminRead":
        self.iso_code = self.iso2
        return self

    model_config = ConfigDict(from_attributes=True)


class CountryAdminListResponse(BaseModel):
    items: list[CountryAdminRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class GeographyStateBase(BaseModel):
    country_id: int
    name: str = Field(min_length=1, max_length=120)
    region_code: str | None = Field(default=None, max_length=20)
    is_active: bool = True
    sort_order: int = 0


class GeographyStateCreate(GeographyStateBase):
    pass


class GeographyStateUpdate(BaseModel):
    country_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    region_code: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    sort_order: int | None = None


class GeographyStateRead(GeographyStateBase):
    id: int
    country_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class GeographyStateListResponse(BaseModel):
    items: list[GeographyStateRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class GeographyCityBase(BaseModel):
    country_id: int
    state_id: int
    name: str = Field(min_length=1, max_length=120)
    time_zone: str | None = Field(default=None, max_length=64)
    postal_code_prefix: str | None = Field(default=None, max_length=20)
    is_active: bool = True
    sort_order: int = 0


class GeographyCityCreate(GeographyCityBase):
    pass


class GeographyCityUpdate(BaseModel):
    country_id: int | None = None
    state_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    time_zone: str | None = Field(default=None, max_length=64)
    postal_code_prefix: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    sort_order: int | None = None


class GeographyCityRead(GeographyCityBase):
    id: int
    country_name: str | None = None
    state_name: str | None = None
    region_code: str | None = None
    model_config = ConfigDict(from_attributes=True)


class GeographyCityListResponse(BaseModel):
    items: list[GeographyCityRead]
    page: int
    page_size: int
    total: int
    total_pages: int


INSTITUTION_PROFILE_TEXT_FIELD_NAMES: tuple[str, ...] = (
    "year_established",
    "global_ranking",
    "national_ranking",
    "brochure_url",
    "tuition_fees",
    "hostel_expenses",
    "food_expense",
    "books_expense",
    "commutation_expense",
    "insurance_expense",
    "medical_expense",
    "other_expense",
)


class InstitutionProfileTextFields(BaseModel):
    year_established: str | None = None
    global_ranking: str | None = None
    national_ranking: str | None = None
    brochure_url: str | None = None
    tuition_fees: str | None = None
    hostel_expenses: str | None = None
    food_expense: str | None = None
    books_expense: str | None = None
    commutation_expense: str | None = None
    insurance_expense: str | None = None
    medical_expense: str | None = None
    other_expense: str | None = None


class InstitutionBase(InstitutionProfileTextFields, BaseModel):
    country_id: int | None = None
    state_id: int | None = None
    city_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=200)
    phone_numbers: list[ContactEntry] | None = None
    fax_numbers: list[ContactEntry] | None = None
    email_addresses: list[ContactEntry] | None = None
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    dean_name: str | None = Field(default=None, max_length=255)
    institution_type_id: int | None = None
    company_affiliated: bool | None = None
    ranking_tier_global: str | None = Field(default=None, max_length=120)
    ad_promotion_flag: bool | None = None
    institution_web_url: str | None = Field(default=None, max_length=250)
    web_links: list[ContactEntry] | None = None
    currency_type: str = Field(default="USD", max_length=10)
    students_count: str | None = Field(default=None, max_length=250)
    accreditation_details: str | None = Field(default=None, max_length=2500)
    short_description: str | None = Field(default=None, max_length=2500)
    long_description: str | None = Field(default=None, max_length=5000)
    is_active: bool = True
    sort_order: int = 0

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def coerce_phone_numbers(cls, value: object) -> object:
        return normalize_phone_contacts(value) if value is not None else None

    @field_validator("fax_numbers", mode="before")
    @classmethod
    def coerce_fax_numbers(cls, value: object) -> object:
        return normalize_fax_contacts(value) if value is not None else None

    @field_validator("email_addresses", mode="before")
    @classmethod
    def coerce_email_addresses(cls, value: object) -> object:
        return normalize_email_contacts(value) if value is not None else None

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links_and_url(self) -> InstitutionBase:
        links = normalize_web_links(self.web_links, self.institution_web_url)
        serialized = serialize_contacts(links)
        self.web_links = serialized or None
        self.institution_web_url = primary_web_url(links)
        return self

    @model_validator(mode="after")
    def validate_optional_emails(self) -> InstitutionBase:
        assert_optional_email_formats(self.email_addresses)
        return self


class InstitutionCreate(InstitutionBase):
    pass


class InstitutionUpdate(InstitutionProfileTextFields, BaseModel):
    country_id: int | None = None
    state_id: int | None = None
    city_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=200)
    phone_numbers: list[ContactEntry] | None = None
    fax_numbers: list[ContactEntry] | None = None
    email_addresses: list[ContactEntry] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    dean_name: str | None = Field(default=None, max_length=255)
    institution_type_id: int | None = None
    company_affiliated: bool | None = None
    ranking_tier_global: str | None = Field(default=None, max_length=120)
    ad_promotion_flag: bool | None = None
    institution_web_url: str | None = Field(default=None, max_length=250)
    web_links: list[ContactEntry] | None = None
    currency_type: str | None = Field(default=None, max_length=10)
    students_count: str | None = Field(default=None, max_length=250)
    accreditation_details: str | None = Field(default=None, max_length=2500)
    short_description: str | None = Field(default=None, max_length=2500)
    long_description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def coerce_phone_numbers(cls, value: object) -> object:
        return normalize_phone_contacts(value) if value is not None else None

    @field_validator("fax_numbers", mode="before")
    @classmethod
    def coerce_fax_numbers(cls, value: object) -> object:
        return normalize_fax_contacts(value) if value is not None else None

    @field_validator("email_addresses", mode="before")
    @classmethod
    def coerce_email_addresses(cls, value: object) -> object:
        return normalize_email_contacts(value) if value is not None else None

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links_and_url(self) -> InstitutionUpdate:
        if self.web_links is None and self.institution_web_url is None:
            return self
        links = normalize_web_links(self.web_links, self.institution_web_url)
        serialized = serialize_contacts(links)
        self.web_links = serialized or None
        self.institution_web_url = primary_web_url(links)
        return self

    @model_validator(mode="after")
    def validate_optional_emails(self) -> InstitutionUpdate:
        assert_optional_email_formats(self.email_addresses)
        return self


class InstitutionRead(InstitutionBase):
    id: int
    country_name: str | None = None
    institution_type_code: str | None = None
    institution_type_name: str | None = None
    campus_count: int = 0
    college_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class InstitutionSummaryRead(BaseModel):
    """Slim list DTO — no profile text, contacts, or description blobs."""

    id: int
    country_id: int | None = None
    state_id: int | None = None
    city_id: int | None = None
    name: str
    code: str | None = None
    institution_type_id: int | None = None
    institution_type_code: str | None = None
    institution_type_name: str | None = None
    is_active: bool = True
    sort_order: int = 0
    country_name: str | None = None
    state_name: str | None = None
    city_name: str | None = None
    campus_count: int = 0
    college_count: int = 0
    publish_status: str = "pending"
    last_publish_attempt_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    level_count: int = 0
    program_count: int = 0
    major_count: int = 0
    sub_major_count: int = 0
    course_count: int = 0
    intake_count: int = 0
    picture_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class InstitutionAdminListResponse(BaseModel):
    items: list[InstitutionSummaryRead]
    page: int
    page_size: int
    total: int
    total_pages: int
    active_count: int = 0
    inactive_count: int = 0


class CampusBase(OptionalPhoneContactListMixin, OptionalEmailContactListMixin, FaxContactListFields, BaseModel):
    institution_id: int
    location_id: int
    name: str = Field(min_length=1, max_length=250)
    campus_type_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=200)
    country_id: int | None = None
    state_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    web_links: list[ContactEntry] | None = None
    is_residential: bool | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links(self) -> CampusBase:
        if self.web_links is None:
            return self
        self.web_links = serialize_contacts(normalize_web_links(self.web_links)) or None
        return self


class CampusCreate(CampusBase):
    pass


class CampusUpdate(BaseModel):
    institution_id: int | None = None
    location_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=250)
    campus_type_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=200)
    country_id: int | None = None
    state_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    phone_numbers: list[ContactEntry] | None = None
    fax_numbers: list[ContactEntry] | None = None
    email_addresses: list[ContactEntry] | None = None
    web_links: list[ContactEntry] | None = None
    is_residential: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def coerce_phone_numbers(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_phone_contacts(value)

    @field_validator("fax_numbers", mode="before")
    @classmethod
    def coerce_fax_numbers(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_fax_contacts(value)

    @field_validator("email_addresses", mode="before")
    @classmethod
    def coerce_email_addresses(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_email_contacts(value)

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links(self) -> CampusUpdate:
        if self.web_links is None:
            return self
        self.web_links = serialize_contacts(normalize_web_links(self.web_links)) or None
        return self

    @model_validator(mode="after")
    def validate_optional_emails(self) -> CampusUpdate:
        assert_optional_email_formats(self.email_addresses)
        return self


class CampusRead(ContactListFields, FaxContactListFields, BaseModel):
    id: int
    institution_id: int
    location_id: int | None = None
    name: str
    campus_type_id: int | None = None
    campus_type_code: str | None = None
    campus_type_name: str | None = None
    campus_type_description: str | None = None
    description: str | None = None
    address: str | None = None
    country_id: int | None = None
    state_id: int | None = None
    zipcode: str | None = None
    web_links: list[ContactEntry] | None = None
    is_residential: bool | None = None
    is_active: bool = True
    sort_order: int = 0
    institution_name: str | None = None
    location_name: str | None = None
    location_label: str | None = None
    country_name: str | None = None
    state_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class CollegeCampusLinkRead(BaseModel):
    campus_id: int
    name: str
    address: str | None = None
    location_label: str | None = None
    is_primary: bool = False
    source_url: str | None = None
    evidence: str | None = None


class CollegeBase(PhoneContactListMixin, EmailContactListMixin, BaseModel):
    institution_id: int
    campus_id: int | None = None
    campus_ids: list[int] | None = None
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=64)
    dean_name: str | None = Field(default=None, max_length=255)
    web_url: str | None = Field(default=None, max_length=250)
    web_links: list[ContactEntry] | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links_and_url(self) -> CollegeBase:
        links = normalize_web_links(self.web_links, self.web_url)
        serialized = serialize_contacts(links)
        self.web_links = serialized or None
        self.web_url = primary_web_url(links)
        return self


class CollegeCreate(CollegeBase):
    pass


class CollegeUpdate(BaseModel):
    institution_id: int | None = None
    campus_id: int | None = None
    campus_ids: list[int] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=64)
    dean_name: str | None = Field(default=None, max_length=255)
    web_url: str | None = Field(default=None, max_length=250)
    web_links: list[ContactEntry] | None = None
    phone_numbers: list[ContactEntry] | None = None
    email_addresses: list[ContactEntry] | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def coerce_phone_numbers(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_phone_contacts(value)

    @field_validator("email_addresses", mode="before")
    @classmethod
    def coerce_email_addresses(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_email_contacts(value)

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> object:
        if value is not None:
            return normalize_web_links(value)
        return None

    @model_validator(mode="after")
    def sync_web_links_and_url(self) -> CollegeUpdate:
        if self.web_links is None and self.web_url is None:
            return self
        links = normalize_web_links(self.web_links, self.web_url)
        serialized = serialize_contacts(links)
        self.web_links = serialized or None
        self.web_url = primary_web_url(links)
        return self


class CollegeRead(ContactListFields, BaseModel):
    id: int
    institution_id: int
    campus_id: int | None = None
    campus_ids: list[int] = Field(default_factory=list)
    linked_campuses: list[CollegeCampusLinkRead] = Field(default_factory=list)
    name: str
    code: str | None = None
    category: str | None = None
    dean_name: str | None = None
    web_url: str | None = None
    web_links: list[ContactEntry] | None = None
    is_active: bool = True
    sort_order: int = 0
    institution_name: str | None = None
    campus_name: str | None = None
    campus_address: str | None = None
    campus_location_label: str | None = None
    hierarchy_breadcrumb: str | None = None
    model_config = ConfigDict(from_attributes=True)


class InstitutionHierarchyCollegeNode(BaseModel):
    id: int
    name: str
    dean_name: str | None = None
    campus_names: list[str] = Field(default_factory=list)


class InstitutionHierarchyCampusNode(BaseModel):
    id: int
    name: str
    location_label: str | None = None
    description: str | None = None
    colleges: list[InstitutionHierarchyCollegeNode]


class InstitutionHierarchyNode(BaseModel):
    id: int
    name: str
    accreditation_details: str | None = None
    campuses: list[InstitutionHierarchyCampusNode]


class InstitutionalHierarchySummary(BaseModel):
    institutions: list[InstitutionHierarchyNode]


class ProgramAdminBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=255)
    name: str | None = None
    description: OptionalRichText5000 = None
    is_active: bool = True
    sort_order: int = 0


class ProgramAdminCreate(BaseModel):
    program_id: int | None = None
    degree_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    description: OptionalRichText5000 = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool = True
    sort_order: int = 0

    @model_validator(mode="after")
    def resolve_program_id(self) -> "ProgramAdminCreate":
        if self.program_id is None and self.degree_id is not None:
            self.program_id = self.degree_id
        if self.program_id is None:
            raise ValueError("program_id is required")
        return self


class ProgramAdminUpdate(BaseModel):
    program_id: int | None = None
    degree_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: OptionalRichText5000 = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def resolve_program_id(self) -> "ProgramAdminUpdate":
        if self.program_id is None and self.degree_id is not None:
            self.program_id = self.degree_id
        return self


class ProgramAdminRead(BaseModel):
    id: int
    program_id: int
    degree_id: int
    code: str
    label: str
    name: str
    description: str | None = None
    degree_name: str | None = None
    level_id: int | None = None
    level_code: str | None = None
    level_name: str | None = None
    is_active: bool = True
    sort_order: int = 0
    course_count: int = 0

    @model_validator(mode="after")
    def sync_degree_id(self) -> "ProgramAdminRead":
        self.degree_id = self.program_id
        return self

    model_config = ConfigDict(from_attributes=True)


class DegreeAdminCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    level_id: int = Field(ge=1)
    description: OptionalRichText5000 = None
    program_url: str | None = Field(default=None, max_length=2048)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool = True
    sort_order: int = 0
    institution_id: int = Field(ge=1, description="Required offering institution")
    country_id: int | None = Field(default=None, ge=1)
    college_id: int | None = Field(default=None, ge=1)
    intake_ids: list[int] = Field(default_factory=list)
    major_ids: list[int] = Field(default_factory=list, description="Catalog majors to map to this program")
    sub_major_ids: list[int] = Field(
        default_factory=list,
        description="Catalog sub-majors to map (multiple per selected major allowed)",
    )


class DegreeAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    level_id: int | None = Field(default=None, ge=1)
    description: OptionalRichText5000 = None
    program_url: str | None = Field(default=None, max_length=2048)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None
    sort_order: int | None = None
    institution_id: int | None = Field(default=None, ge=1)
    country_id: int | None = Field(default=None, ge=1)
    college_id: int | None = Field(default=None, ge=1)
    intake_ids: list[int] | None = None
    major_ids: list[int] | None = Field(
        default=None, description="Replace mapped catalog majors when provided"
    )
    sub_major_ids: list[int] | None = Field(
        default=None,
        description="Replace mapped catalog sub-majors when provided (multiple per major allowed)",
    )


class DegreeAdminRead(BaseModel):
    id: int
    code: str
    name: str
    level_id: int
    level_code: str | None = None
    level_name: str | None = None
    description: str | None = None
    program_url: str | None = None
    is_active: bool = True
    sort_order: int = 0
    major_count: int = 0
    major_ids: list[int] = Field(default_factory=list)
    major_names: list[str] = Field(default_factory=list)
    sub_major_ids: list[int] = Field(default_factory=list)
    sub_major_names: list[str] = Field(default_factory=list)
    institution_id: int | None = None
    institution_ids: list[int] = Field(default_factory=list)
    institution_names: list[str] = Field(default_factory=list)
    country_id: int | None = None
    college_id: int | None = None
    intake_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DegreeAdminListResponse(BaseModel):
    items: list[DegreeAdminRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class HierarchyCourseNode(BaseModel):
    id: int
    name: str
    code: str | None = None


class HierarchyMajorNode(BaseModel):
    id: int
    name: str
    courses: list[HierarchyCourseNode]


class HierarchyProgramNode(BaseModel):
    id: int
    name: str
    majors: list[HierarchyMajorNode]
    sub_major_count: int = 0
    sub_major_ids: list[int] = Field(default_factory=list)


class HierarchyLevelNode(BaseModel):
    id: int
    name: str
    programs: list[HierarchyProgramNode]
    major_count: int = 0
    sub_major_count: int = 0


class FrameworkCoveragePair(BaseModel):
    mapped: int = 0
    unmapped: int = 0
    total: int = 0
    mapped_pct: float = 0
    unmapped_pct: float = 0


class FrameworkInstitutionCoverage(BaseModel):
    institution_id: int
    institution_name: str
    country_id: int | None = None
    country_name: str | None = None
    program_count: int = 0
    without_major: int = 0
    without_sub_major: int = 0
    without_course: int = 0
    without_level: int = 0
    without_url: int = 0
    without_major_pct: float = 0
    without_sub_major_pct: float = 0
    without_course_pct: float = 0
    without_level_pct: float = 0
    without_url_pct: float = 0


class FrameworkCountryCoverage(BaseModel):
    country_id: int | None = None
    country_name: str | None = None
    institution_count: int = 0
    campus_count: int = 0
    college_count: int = 0
    program_count: int = 0
    major_count: int = 0
    sub_major_count: int = 0
    level_count: int = 0
    programs_with_no_major: int = 0
    programs_with_no_sub_major: int = 0
    major_mapping: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    sub_major_mapping: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    course_link: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    level_assignment: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    program_url: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    by_institution: list[FrameworkInstitutionCoverage] = Field(default_factory=list)
    program_ids: list[int] = Field(
        default_factory=list,
        description="Distinct offered program ids in this country (for LPMC tree filter)",
    )


class FrameworkCoverageMetrics(BaseModel):
    """Offered-program coverage (not every ``programs`` row).

    Denominator = distinct ``programs.id`` with an active
    ``institution_course_offerings`` → ``target_courses`` link.
    Major / sub-major numerators intersect ``program_education_major_mappings``
    (same table NZ Mapping Review bulk-apply writes).
    """

    institution_count: int = 0
    campus_count: int = 0
    college_count: int = 0
    program_count: int = 0
    major_count: int = 0
    sub_major_count: int = 0
    level_count: int = 0
    course_count: int = 0
    programs_with_no_major: int = 0
    programs_with_no_sub_major: int = 0
    major_mapping: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    sub_major_mapping: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    course_link: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    level_assignment: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    program_url: FrameworkCoveragePair = Field(default_factory=FrameworkCoveragePair)
    by_institution: list[FrameworkInstitutionCoverage] = Field(default_factory=list)
    by_institution_truncated: bool = False
    by_country: list[FrameworkCountryCoverage] = Field(default_factory=list)


class AcademicHierarchySummary(BaseModel):
    levels: list[HierarchyLevelNode]
    coverage: FrameworkCoverageMetrics = Field(default_factory=FrameworkCoverageMetrics)


class CourseAdminBase(BaseModel):
    program_id: int
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=255)
    name: str | None = None
    level: str | None = Field(default=None, max_length=40)
    is_active: bool = True
    sort_order: int = 0


class CourseAdminCreate(BaseModel):
    major_ids: list[int] = Field(
        default_factory=list,
        description="Catalog education major ids to map this course to",
    )
    major_id: int | None = Field(
        default=None,
        ge=1,
        description="Deprecated single major; use major_ids",
    )
    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: OptionalRichText5000 = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("code", mode="before")
    @classmethod
    def normalize_create_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def resolve_major_ids(self):
        ids = [int(major_id) for major_id in self.major_ids if major_id]
        if not ids and self.major_id:
            ids = [int(self.major_id)]
        if not ids:
            raise ValueError("Select at least one major.")
        self.major_ids = list(dict.fromkeys(ids))
        self.major_id = self.major_ids[0]
        return self


class CourseAdminUpdate(BaseModel):
    major_ids: list[int] | None = Field(
        default=None,
        description="Catalog education major ids to map this course to",
    )
    major_id: int | None = Field(
        default=None,
        ge=1,
        description="Deprecated single major; use major_ids",
    )
    name: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: OptionalRichText5000 = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_update_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def resolve_major_ids(self):
        fields_set = getattr(self, "model_fields_set", set())
        if "major_ids" in fields_set and self.major_ids is not None:
            ids = [int(major_id) for major_id in self.major_ids if major_id]
            if not ids:
                raise ValueError("Select at least one major.")
            self.major_ids = list(dict.fromkeys(ids))
            self.major_id = self.major_ids[0]
        elif "major_id" in fields_set and self.major_id is not None:
            self.major_ids = [int(self.major_id)]
        return self


class CourseAdminRead(BaseModel):
    id: int
    program_id: int
    major_id: int | None = None
    major_ids: list[int] = Field(default_factory=list)
    degree_id: int | None = None
    level_id: int | None = None
    code: str | None = None
    description: str | None = None
    label: str
    name: str
    level: str | None = None
    is_active: bool = True
    sort_order: int = 0
    program_code: str | None = None
    program_label: str | None = None
    program_name: str | None = None
    major_name: str | None = None
    major_names: list[str] = Field(default_factory=list)
    degree_name: str | None = None
    hierarchy_breadcrumb: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CourseAdminListResponse(BaseModel):
    items: list[CourseAdminRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class AcademiaSearchResult(BaseModel):
    entity_type: str
    entity_label: str
    category: str
    id: int
    title: str
    subtitle: str | None = None
    path: str
