from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class WorkProjectInput(BaseModel):
    id: int | None = None
    project_name: str | None = Field(default=None, max_length=255)
    project_description: str | None = None

    @field_validator("project_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("project_description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class WorkExperienceInput(BaseModel):
    id: int | None = None
    company_name: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    projects: list[WorkProjectInput] = Field(default_factory=list)

    @field_validator("company_name", "job_title")
    @classmethod
    def normalize_short_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_dates(self) -> WorkExperienceInput:
        if self.is_current:
            self.end_date = None
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")
        return self


class WorkExperienceSaveRequest(BaseModel):
    experiences: list[WorkExperienceInput] = Field(default_factory=list)


class WorkProjectOut(BaseModel):
    id: int
    project_name: str | None
    project_description: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class WorkExperienceOut(BaseModel):
    id: int
    company_name: str | None
    job_title: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    description: str | None
    sort_order: int
    projects: list[WorkProjectOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WorkExperiencesResponse(BaseModel):
    booking_id: int
    lead_id: int | None
    experiences: list[WorkExperienceOut]
    saved_at: datetime | None = None
