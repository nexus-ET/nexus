from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class ActivityCategory(str, Enum):
    ARTS_AND_CULTURE = "ARTS_AND_CULTURE"
    EVENT_ORGANIZING = "EVENT_ORGANIZING"
    EXTRACURRICULAR_CLUBS_TEAMS = "EXTRACURRICULAR_CLUBS_TEAMS"
    GOVERNMENT = "GOVERNMENT"
    HOBBIES = "HOBBIES"
    LANGUAGE_AND_LINGUISTICS = "LANGUAGE_AND_LINGUISTICS"
    LEADERSHIP = "LEADERSHIP"
    MAINSTREAM_MEDIA_AND_SOCIAL_MEDIA = "MAINSTREAM_MEDIA_AND_SOCIAL_MEDIA"
    MUSIC = "MUSIC"
    OTHERS = "OTHERS"
    PART_TIME_OR_SUMMER_JOBS = "PART_TIME_OR_SUMMER_JOBS"
    PERFORMANCE_ART = "PERFORMANCE_ART"
    POLITICAL_CAMPAIGNS = "POLITICAL_CAMPAIGNS"
    RELIGIOUS = "RELIGIOUS"
    SOCIAL_ACTIVISM = "SOCIAL_ACTIVISM"
    SPORTS_AND_RECREATION = "SPORTS_AND_RECREATION"
    STUDENT_BODY = "STUDENT_BODY"
    TECHNOLOGY = "TECHNOLOGY"
    TRAININGS = "TRAININGS"
    TRAVELING = "TRAVELING"
    VOLUNTARY_WORK_COMMUNITY_SERVICE = "VOLUNTARY_WORK_COMMUNITY_SERVICE"
    WORKSHOPS = "WORKSHOPS"


ACTIVITY_CATEGORY_LABELS: dict[ActivityCategory, str] = {
    ActivityCategory.ARTS_AND_CULTURE: "Arts and Culture",
    ActivityCategory.EVENT_ORGANIZING: "Event Organizing",
    ActivityCategory.EXTRACURRICULAR_CLUBS_TEAMS: "Extracurricular clubs/teams",
    ActivityCategory.GOVERNMENT: "Government",
    ActivityCategory.HOBBIES: "Hobbies",
    ActivityCategory.LANGUAGE_AND_LINGUISTICS: "Language and Linguistics",
    ActivityCategory.LEADERSHIP: "Leadership",
    ActivityCategory.MAINSTREAM_MEDIA_AND_SOCIAL_MEDIA: "Mainstream Media and Social Media",
    ActivityCategory.MUSIC: "Music",
    ActivityCategory.OTHERS: "Others",
    ActivityCategory.PART_TIME_OR_SUMMER_JOBS: "Part-time or summer jobs",
    ActivityCategory.PERFORMANCE_ART: "Performance Art",
    ActivityCategory.POLITICAL_CAMPAIGNS: "Political Campaigns",
    ActivityCategory.RELIGIOUS: "Religious",
    ActivityCategory.SOCIAL_ACTIVISM: "Social Activism",
    ActivityCategory.SPORTS_AND_RECREATION: "Sports and Recreation",
    ActivityCategory.STUDENT_BODY: "Student Body",
    ActivityCategory.TECHNOLOGY: "Technology",
    ActivityCategory.TRAININGS: "Trainings",
    ActivityCategory.TRAVELING: "Traveling",
    ActivityCategory.VOLUNTARY_WORK_COMMUNITY_SERVICE: "Voluntary Work / Community Service",
    ActivityCategory.WORKSHOPS: "Workshops",
}


class ActivityCategoryOption(BaseModel):
    value: ActivityCategory
    label: str


def list_activity_category_options() -> list[ActivityCategoryOption]:
    return [
        ActivityCategoryOption(value=category, label=label)
        for category, label in ACTIVITY_CATEGORY_LABELS.items()
    ]


class NonAcademicActivityInput(BaseModel):
    activity_category: ActivityCategory | None = None
    activity_name: str | None = Field(default=None, max_length=255)
    role_or_title: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = Field(default=None, max_length=500)

    @field_validator("activity_name", "role_or_title")
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
    def validate_dates(self) -> NonAcademicActivityInput:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date.")
        return self


class NonAcademicActivityOut(BaseModel):
    id: int
    activity_category: ActivityCategory | None
    activity_category_label: str | None
    activity_name: str | None
    role_or_title: str | None
    start_date: date | None
    end_date: date | None
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NonAcademicActivitiesResponse(BaseModel):
    booking_id: int
    lead_id: int | None
    activity_categories: list[ActivityCategoryOption]
    activities: list[NonAcademicActivityOut]
    saved_at: datetime | None = None
