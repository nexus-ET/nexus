from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCompleteRequest(BaseModel):
    outcome_key: str = Field(min_length=1, max_length=50)
    next_stage: str = Field(min_length=1, max_length=50)
    notes: str | None = None
    action_items: list[str] = Field(default_factory=list)


class SessionCompleteResponse(BaseModel):
    booking_id: int
    status: str
    outcome_key: str
    next_stage: str
    candidate_id: int | None = None
    tasks_created: int
    completed_at: datetime | None = None


class PipelineStageOut(BaseModel):
    key: str
    label: str
    category: str | None = None


class PipelineOutcomeOut(BaseModel):
    key: str
    label: str
    default_next_stage: str
    action_items: list[str]


class PipelineConfigResponse(BaseModel):
    stages: list[PipelineStageOut]
    outcomes: list[PipelineOutcomeOut]


class CounsellorConversionOut(BaseModel):
    counsellor_id: int
    counsellor_name: str
    counselling_sessions: int
    moved_to_applied: int
    conversion_rate: float


class StalledCandidateOut(BaseModel):
    lead_id: int
    full_name: str
    days_in_stage: int | None = None
    admission_stage: str | None = None


class OutcomeFrequencyOut(BaseModel):
    outcome_key: str
    label: str
    count: int


class PipelineAnalyticsResponse(BaseModel):
    conversion_by_counsellor: list[CounsellorConversionOut]
    overall_counselling_moves: int
    average_days_in_stage: dict[str, float]
    stalled_candidates: list[StalledCandidateOut]
    outcome_frequency: list[OutcomeFrequencyOut]
    awaiting_docs_reminder_pending: int
