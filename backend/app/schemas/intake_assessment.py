"""Schemas for Sub-Process 1.1 Intake Session counselor assessment workspace."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatus = Literal["planned", "in_progress", "complete"]


class IntakeAcademicAssessment(BaseModel):
    grading_scale_code: str | None = None
    notes: str = ""
    status: TaskStatus = "planned"


class IntakeEnglishAssessment(BaseModel):
    selected_test_id: int | None = None
    test_name: str | None = "IELTS"
    reading: str | None = None
    writing: str | None = None
    listening: str | None = None
    speaking: str | None = None
    overall: str | None = None
    language_waiver_eligible: bool = False


class IntakeGapAssessment(BaseModel):
    reason: str | None = None
    notes: str = ""


class IntakeGoalsAssessment(BaseModel):
    countries: list[str] = Field(default_factory=list)
    colleges: list[str] = Field(default_factory=list)
    intake_season: str | None = "Fall"
    intake_year: int | None = None


class IntakeFinancialAssessment(BaseModel):
    funding_source: str | None = None
    budget_min: int = 0
    budget_max: int = 40000
    currency: str = "USD"
    notes: str = ""


class IntakeAssessmentPayload(BaseModel):
    academic: IntakeAcademicAssessment = Field(default_factory=IntakeAcademicAssessment)
    english: IntakeEnglishAssessment = Field(default_factory=IntakeEnglishAssessment)
    gap: IntakeGapAssessment = Field(default_factory=IntakeGapAssessment)
    goals: IntakeGoalsAssessment = Field(default_factory=IntakeGoalsAssessment)
    financial: IntakeFinancialAssessment = Field(default_factory=IntakeFinancialAssessment)


class IntakeAssessmentResponse(BaseModel):
    booking_id: int
    lead_id: int | None = None
    assessment: IntakeAssessmentPayload
    profile_snapshot: dict[str, Any] = Field(default_factory=dict)
