from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CounsellingSummarizeRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, max_length=20000)


class CounsellingSummarizeResponse(BaseModel):
    preferred_universities: list[str] = Field(default_factory=list)
    scholarship_interests: str = ""
    career_goals: str = ""
    recommendations: str = ""
    next_follow_up: date | None = None


class CounsellingSessionNoteSaveRequest(BaseModel):
    ai_transcription: str | None = None
    preferred_universities: list[str] = Field(default_factory=list)
    scholarship_interests: str | None = None
    career_goals: str | None = None
    officer_recommendations: str | None = None
    next_follow_up: date | None = None


class CounsellingSessionNoteOut(BaseModel):
    booking_id: int
    ai_transcription: str | None = None
    preferred_universities: list[str] = Field(default_factory=list)
    scholarship_interests: str | None = None
    career_goals: str | None = None
    officer_recommendations: str | None = None
    next_follow_up: date | None = None
    updated_at: str | None = None


class RecommendedInstitutionOption(BaseModel):
    value: str
    label: str
    kind: str
    name: str
    country_id: int | None = None
    country_name: str | None = None
    state_name: str | None = None
    city_name: str | None = None


class RecommendedInstitutionOptionsResponse(BaseModel):
    options: list[RecommendedInstitutionOption] = Field(default_factory=list)
