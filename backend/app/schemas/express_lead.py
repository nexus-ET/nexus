from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ExpressLeadCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., min_length=3, max_length=255)
    phone_country_iso2: str = Field(..., min_length=2, max_length=2)
    phone_local: str = Field(..., min_length=10, max_length=10)
    target_destination_iso2s: list[str] = Field(default_factory=list, max_length=6)
    target_major_ids: list[int] = Field(default_factory=list)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field is required.")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Email is required.")
        if isinstance(value, str):
            return value.strip().lower()
        return value

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

    @field_validator("target_destination_iso2s")
    @classmethod
    def normalize_destinations(cls, value: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value or []:
            iso2 = (item or "").strip().upper()
            if not iso2 or iso2 in seen:
                continue
            if len(iso2) != 2:
                raise ValueError("Each target country must be a 2-letter code.")
            seen.add(iso2)
            normalized.append(iso2)
        if len(normalized) > 6:
            raise ValueError("Select up to 6 target countries.")
        return normalized

    @field_validator("target_major_ids")
    @classmethod
    def normalize_majors(cls, value: list[int] | None) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for item in value or []:
            major_id = int(item)
            if major_id < 1 or major_id in seen:
                continue
            seen.add(major_id)
            normalized.append(major_id)
        if len(normalized) > 6:
            raise ValueError("Select up to 6 target programs.")
        return normalized


class ExpressLeadMatch(BaseModel):
    id: int
    full_name: str
    email: str | None = None
    phone_number: str | None = None
    matched_on: Literal["email", "phone", "both"]
    stage: str
    status_label: str
    source: str | None = None
    source_label: str | None = None
    preferred_country: str | None = None
    academic_summary: str | None = None
    created_at: str | None = None
    record_kind: Literal["lead", "students_master"] = "lead"
    students_master_id: int | None = None
    lead_id: int | None = None
    page_path: str
    page_label: str
    prospects_path: str


class ExpressLeadDuplicateCheckResponse(BaseModel):
    email_match: ExpressLeadMatch | None = None
    phone_match: ExpressLeadMatch | None = None


class ExpressLeadCreated(BaseModel):
    id: int
    full_name: str
    email: str | None = None
    phone_number: str | None = None
    stage: str
    source: str
    target_destination_iso2s: list[str] = Field(default_factory=list)
    target_destinations: list[str] = Field(default_factory=list)
    target_major_ids: list[int] = Field(default_factory=list)
    target_majors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
