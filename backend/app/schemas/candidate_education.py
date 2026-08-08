from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CandidateEducationInput(BaseModel):
    degree_code: str | None = Field(default=None, max_length=50)
    degree_other: str | None = Field(default=None, max_length=255)
    full_time_study_years: str | None = Field(default=None, max_length=10)
    major: str | None = Field(default=None, max_length=255)
    university_name: str | None = Field(default=None, max_length=255)
    university_affiliation: str | None = Field(default=None, max_length=255)
    graduation_month: int | None = Field(default=None, ge=1, le=12)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    gpa_cgpa_code: str | None = Field(default=None, max_length=50)
    gpa_cgpa_other: str | None = Field(default=None, max_length=255)

    @field_validator("degree_code", "gpa_cgpa_code")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
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

    @field_validator(
        "degree_other",
        "major",
        "university_name",
        "university_affiliation",
        "gpa_cgpa_other",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CandidateEducationOut(BaseModel):
    id: int
    degree_code: str | None
    degree_label: str | None
    degree_other: str | None
    full_time_study_years: str | None
    full_time_study_years_label: str | None = None
    major: str | None
    university_name: str | None
    university_affiliation: str | None
    graduation_month: int | None
    graduation_year: int | None
    gpa_cgpa_code: str | None
    gpa_cgpa_label: str | None
    gpa_cgpa_other: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CandidateEducationsResponse(BaseModel):
    booking_id: int
    lead_id: int | None
    educations: list[CandidateEducationOut]
    saved_at: datetime | None = None
