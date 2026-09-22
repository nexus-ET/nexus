from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class OfflineLeadLocation(BaseModel):
    address_line_1: str = Field(default="", max_length=255)
    address_line_2: str = Field(default="", max_length=255)
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    country_iso2: str = Field(default="", max_length=2)
    zip_code: str | None = Field(default=None, max_length=20)

    @field_validator("address_line_1", "address_line_2", "city", "state")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str:
        return (value or "").strip()

    @field_validator("zip_code")
    @classmethod
    def normalize_zip_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("country_iso2")
    @classmethod
    def normalize_country_iso2(cls, value: str | None) -> str:
        return (value or "").strip().upper()

    def has_content(self) -> bool:
        return bool(
            self.address_line_1
            or self.address_line_2
            or self.city
            or self.state
            or self.country_iso2
            or self.zip_code
        )

class OfflineLeadEducation(BaseModel):
    degree_code: str | None = Field(default=None, max_length=50)
    degree: str | None = Field(default=None, max_length=255)
    program_code: str | None = Field(default=None, max_length=50)
    program: str | None = Field(default=None, max_length=255)
    full_time_study_years: str | None = Field(default=None, max_length=10)
    level_id: int | None = Field(default=None, ge=1)
    major: str | None = Field(default=None, max_length=255)
    gpa_cgpa_code: str | None = Field(default=None, max_length=50)
    gpa_cgpa: str | None = Field(default=None, max_length=255)
    university: str | None = None
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator("degree_code", "gpa_cgpa_code", "program_code")
    @classmethod
    def normalize_code_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("full_time_study_years")
    @classmethod
    def normalize_study_years(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class OfflineLeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: EmailStr
    phone_country_iso2: str = Field(..., min_length=2, max_length=2)
    phone_local: str = Field(..., min_length=10, max_length=10)
    date_of_birth: date | None = None
    education: OfflineLeadEducation | None = None
    target_destination_iso2s: list[str] = Field(default_factory=list, max_length=6)
    target_level_id: int | None = Field(default=None, ge=1)
    target_major_ids: list[int] = Field(default_factory=list, max_length=3)
    target_program_codes: list[str] = Field(default_factory=list)
    location: OfflineLeadLocation = Field(default_factory=OfflineLeadLocation)

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("First name is required.")
        return normalized

    @field_validator("last_name")
    @classmethod
    def normalize_last_name(cls, value: str | None) -> str:
        return (value or "").strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Email is required.")
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("target_destination_iso2s")
    @classmethod
    def normalize_target_destination_iso2s(cls, value: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value or []:
            iso2 = (item or "").strip().upper()
            if not iso2 or iso2 in seen:
                continue
            if len(iso2) != 2:
                raise ValueError("Each target destination must be a 2-letter country code.")
            seen.add(iso2)
            normalized.append(iso2)
        if len(normalized) > 6:
            raise ValueError("Select up to 6 target destinations.")
        return normalized

    @field_validator("target_major_ids")
    @classmethod
    def normalize_target_major_ids(cls, value: list[int] | None) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for item in value or []:
            major_id = int(item)
            if major_id < 1 or major_id in seen:
                continue
            seen.add(major_id)
            normalized.append(major_id)
        if len(normalized) > 3:
            raise ValueError("Select up to 3 target majors.")
        return normalized

    @field_validator("target_program_codes")
    @classmethod
    def normalize_target_program_codes(cls, value: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value or []:
            code = (item or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            normalized.append(code)
        return normalized

    @field_validator("phone_country_iso2")
    @classmethod
    def normalize_phone_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("phone_local")
    @classmethod
    def normalize_phone_local(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Phone number must be exactly 10 digits.")
        return digits

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def empty_date_of_birth_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value is None:
            return None
        today = date.today()
        if value > today:
            raise ValueError("Date of birth cannot be in the future.")
        age = today.year - value.year
        if (today.month, today.day) < (value.month, value.day):
            age -= 1
        if age < 16:
            raise ValueError("Applicants must be at least 16 years old.")
        return value


OfflineLeadUpdate = OfflineLeadCreate


class OfflineLeadActiveUpdate(BaseModel):
    """Toggle All Leads active/inactive. Prefer is_active; new_status is accepted as an alias."""

    is_active: bool | None = None
    new_status: Literal["active", "inactive"] | None = None
    reasons: list[str] = Field(default_factory=list)

    @field_validator("reasons", mode="before")
    @classmethod
    def coerce_reasons(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("reasons")
    @classmethod
    def normalize_reasons(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value or []:
            label = (item or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            normalized.append(label)
            if len(normalized) >= 5:
                break
        return normalized

    @model_validator(mode="after")
    def resolve_status_and_reasons(self) -> "OfflineLeadActiveUpdate":
        if self.is_active is None and self.new_status is not None:
            self.is_active = self.new_status == "active"
        if self.is_active is None:
            raise ValueError("Provide is_active or new_status.")
        if not self.reasons:
            raise ValueError("Select at least one reason.")
        return self


class OfflineLeadActiveReasonsResponse(BaseModel):
    inactive: list[str]
    active: list[str]

class OfflineLeadListItem(BaseModel):
    id: int
    full_name: str
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    phone_country_iso2: str | None = None
    stage: str
    status_label: str
    source: str
    is_active: bool = True
    target_destination: str | None = None
    target_destination_iso2: str | None = None
    target_destination_iso2s: list[str] = Field(default_factory=list)
    target_destinations: list[str] = Field(default_factory=list)
    target_level_id: int | None = None
    target_level_name: str | None = None
    target_major_ids: list[int] = Field(default_factory=list)
    target_majors: list[str] = Field(default_factory=list)
    target_program_codes: list[str] = Field(default_factory=list)
    target_programs: list[str] = Field(default_factory=list)
    target_program: str | None = None
    target_program_code: str | None = None
    target_course: str | None = None
    target_course_code: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    country: str | None = None
    country_iso2: str | None = None
    degree: str | None = None
    degree_code: str | None = None
    program: str | None = None
    program_code: str | None = None
    level_id: int | None = None
    full_time_study_years: str | None = None
    major: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    gpa_cgpa: str | None = None
    gpa_cgpa_code: str | None = None
    date_of_birth: str | None = None
    age: int | None = None
    created_at: datetime | None = None
    booking_count: int = 0
    followup_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class OfflineLeadListResponse(BaseModel):
    items: list[OfflineLeadListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class OfflineLeadDuplicateCheckResponse(BaseModel):
    email_taken: bool = False
    phone_taken: bool = False


SortField = Literal["full_name", "created_at", "email", "phone_number"]
SortDirection = Literal["asc", "desc"]
