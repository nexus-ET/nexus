from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class OfflineLeadLocation(BaseModel):
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    country_iso2: str = Field(..., min_length=2, max_length=2)

    @field_validator("city", "state")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field is required.")
        return normalized

    @field_validator("country_iso2")
    @classmethod
    def normalize_country_iso2(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Country is required.")
        return normalized


class OfflineLeadEducation(BaseModel):
    degree_code: str | None = Field(default=None, max_length=50)
    degree: str | None = Field(default=None, max_length=255)
    major: str | None = Field(default=None, max_length=255)
    gpa_cgpa_code: str | None = Field(default=None, max_length=50)
    gpa_cgpa: str | None = Field(default=None, max_length=255)
    university: str | None = None
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator("degree_code", "gpa_cgpa_code")
    @classmethod
    def normalize_code_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class OfflineLeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_country_iso2: str = Field(..., min_length=2, max_length=2)
    phone_local: str = Field(..., min_length=10, max_length=10)
    date_of_birth: date
    education: OfflineLeadEducation | None = None
    target_destination_iso2: str = Field(..., min_length=2, max_length=2)
    target_program_code: str = Field(..., min_length=1, max_length=50)
    target_course_code: str = Field(..., min_length=1, max_length=50)
    location: OfflineLeadLocation

    @field_validator("target_destination_iso2")
    @classmethod
    def normalize_target_destination_iso2(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Target destination is required.")
        return normalized

    @field_validator("target_program_code", "target_course_code")
    @classmethod
    def normalize_study_interest_codes(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("This field is required.")
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

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date) -> date:
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
    target_destination: str | None = None
    target_destination_iso2: str | None = None
    target_program: str | None = None
    target_program_code: str | None = None
    target_course: str | None = None
    target_course_code: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    country_iso2: str | None = None
    degree: str | None = None
    degree_code: str | None = None
    major: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    gpa_cgpa: str | None = None
    gpa_cgpa_code: str | None = None
    date_of_birth: str | None = None
    age: int | None = None
    created_at: datetime | None = None

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
