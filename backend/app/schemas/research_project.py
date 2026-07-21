from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ResearchProjectType(str, Enum):
    BUSINESS = "BUSINESS"
    CRIME_AND_LAW = "CRIME_AND_LAW"
    DRUGS_AND_DRUG_ABUSE = "DRUGS_AND_DRUG_ABUSE"
    EDUCATION = "EDUCATION"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    HEALTH = "HEALTH"
    MEDIA_AND_COMMUNICATION = "MEDIA_AND_COMMUNICATION"
    OTHERS = "OTHERS"
    POLITICAL_ISSUE = "POLITICAL_ISSUE"
    PSYCHOLOGY = "PSYCHOLOGY"
    RELIGION = "RELIGION"
    SOCIAL_ISSUES = "SOCIAL_ISSUES"
    TECHNOLOGY = "TECHNOLOGY"
    TERRORISM = "TERRORISM"
    WOMEN_AND_GENDER = "WOMEN_AND_GENDER"
    ENGINEERING_PHYSICAL_SCIENCES = "ENGINEERING_PHYSICAL_SCIENCES"
    ART_HUMANITIES = "ART_HUMANITIES"
    DATA_SCIENCE_AI = "DATA_SCIENCE_AI"
    ECONOMICS_FINANCE = "ECONOMICS_FINANCE"


RESEARCH_PROJECT_TYPE_LABELS: dict[ResearchProjectType, str] = {
    ResearchProjectType.BUSINESS: "Businesss",
    ResearchProjectType.CRIME_AND_LAW: "Crime and Law",
    ResearchProjectType.DRUGS_AND_DRUG_ABUSE: "Drugs and Drug Abuse",
    ResearchProjectType.EDUCATION: "Education",
    ResearchProjectType.ENVIRONMENTAL: "Environmental",
    ResearchProjectType.HEALTH: "Health",
    ResearchProjectType.MEDIA_AND_COMMUNICATION: "Media and Communication",
    ResearchProjectType.OTHERS: "Others",
    ResearchProjectType.POLITICAL_ISSUE: "Political Issue",
    ResearchProjectType.PSYCHOLOGY: "Psychology",
    ResearchProjectType.RELIGION: "Religion",
    ResearchProjectType.SOCIAL_ISSUES: "Social Issues",
    ResearchProjectType.TECHNOLOGY: "Technology",
    ResearchProjectType.TERRORISM: "Terrorism",
    ResearchProjectType.WOMEN_AND_GENDER: "Women and Gender",
    ResearchProjectType.ENGINEERING_PHYSICAL_SCIENCES: "Engineering & Physical Sciences",
    ResearchProjectType.ART_HUMANITIES: "Art & Humanities",
    ResearchProjectType.DATA_SCIENCE_AI: "Data Science & AI",
    ResearchProjectType.ECONOMICS_FINANCE: "Economics & Finance",
}


class ResearchProjectTypeOption(BaseModel):
    value: ResearchProjectType
    label: str


def list_research_project_type_options() -> list[ResearchProjectTypeOption]:
    return [
        ResearchProjectTypeOption(value=project_type, label=label)
        for project_type, label in RESEARCH_PROJECT_TYPE_LABELS.items()
    ]


class ResearchProjectInput(BaseModel):
    project_type: ResearchProjectType
    project_title: str | None = Field(default=None, max_length=255)
    project_description: str | None = Field(default=None, max_length=500)
    publication_url: str | None = Field(default=None, max_length=500)
    role: str | None = Field(default=None, max_length=100)

    @field_validator("project_title", "role")
    @classmethod
    def normalize_short_text(cls, value: str | None) -> str | None:
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

    @field_validator("publication_url")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ResearchProjectOut(BaseModel):
    id: int
    project_type: ResearchProjectType
    project_type_label: str
    project_title: str | None
    project_description: str | None
    publication_url: str | None
    role: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResearchProjectsResponse(BaseModel):
    booking_id: int
    lead_id: int | None
    project_types: list[ResearchProjectTypeOption]
    projects: list[ResearchProjectOut]
    saved_at: datetime | None = None
