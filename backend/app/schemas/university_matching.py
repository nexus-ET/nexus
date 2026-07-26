"""Pydantic schemas for Phase 1 university shortlisting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FitBand = Literal["safe", "target", "reach"]
ShortlistRunStatus = Literal["completed", "failed", "insufficient_data"]


class MatchingWeightProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    weight_academic: Decimal
    weight_profile: Decimal
    weight_aspirations: Decimal
    weight_safety: Decimal
    is_default: bool
    is_active: bool


class UniversityShortlistGenerateRequest(BaseModel):
    weight_profile_code: str | None = Field(
        default=None,
        description="Optional weight profile code (default | research_masters).",
    )
    limit: int = Field(default=40, ge=1, le=100)


class MatchedAcademicPathwayOut(BaseModel):
    offering_id: int | None = None
    program_code: str | None = None
    program_name: str | None = None
    major_code: str | None = None
    major_name: str | None = None
    course_id: int | None = None
    course_code: str | None = None
    course_label: str | None = None
    course_level: str | None = None
    match_score: float | None = None
    match_reason: str | None = None


class LabeledCatalogRef(BaseModel):
    code: str | None = None
    name: str | None = None


class DerivedAcademicSummaryOut(BaseModel):
    student_preferences: dict[str, Any] = Field(default_factory=dict)
    matched_programs: list[LabeledCatalogRef] = Field(default_factory=list)
    matched_majors: list[LabeledCatalogRef] = Field(default_factory=list)
    matched_courses: list[LabeledCatalogRef] = Field(default_factory=list)
    source: str | None = None


class UniversityShortlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_id: int
    institution_name: str | None = None
    institution_country_iso2: str | None = None
    ranking_tier_global: str | None = None
    institution_type: str | None = None
    offering_id: int | None = None
    program_code: str | None = None
    program_name: str | None = None
    major_code: str | None = None
    major_name: str | None = None
    course_code: str | None = None
    course_label: str | None = None
    course_level: str | None = None
    matched_pathways: list[MatchedAcademicPathwayOut] = Field(default_factory=list)
    rank: int
    consolidated_score: Decimal
    s_academic: Decimal
    s_profile: Decimal
    s_aspirations: Decimal
    s_safety: Decimal
    fit_band: FitBand
    explanation: dict[str, Any] | None = None


class UniversityShortlistRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int | None = None
    booking_id: int | None = None
    students_master_id: int | None = None
    algorithm_version: str
    status: ShortlistRunStatus
    classification_mode: str
    item_count: int
    weight_profile: MatchingWeightProfileOut | None = None
    notes: str | None = None
    disclaimer: str = (
        "Phase 1 fit confidence only. Safe/Target/Reach are heuristics from "
        "existing profile and catalog data — not admission probability."
    )
    created_at: datetime
    derived_academic: DerivedAcademicSummaryOut | None = None
    items: list[UniversityShortlistItemOut] = Field(default_factory=list)


class UniversityShortlistResponse(BaseModel):
    booking_id: int
    run: UniversityShortlistRunOut | None = None
