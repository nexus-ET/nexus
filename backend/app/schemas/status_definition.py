from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StatusDefinitionOut(BaseModel):
    id: int
    stage_name: str
    category: str
    description: str | None = None
    next_stage_id: int | None = None
    is_terminal: bool = False


class StatusDefinitionsResponse(BaseModel):
    items: list[StatusDefinitionOut]


class LeadStatusHistoryItemOut(BaseModel):
    id: int
    status_definition_id: int
    status_id: int | None = None
    stage_name: str
    category: str
    entered_at: datetime
    notes: str | None = None
    comments: str | None = None
    changed_by_type: str | None = None
    changed_by_user_id: int | None = None
    changed_by_label: str | None = None


class StudentJourneyItemOut(BaseModel):
    id: int
    status_id: int
    stage_name: str
    category: str
    description: str | None = None
    changed_by_type: str
    changed_by_user_id: int | None = None
    changed_by_label: str
    comments: str | None = None
    created_at: datetime


class StudentJourneyResponse(BaseModel):
    student_id: int
    items: list[StudentJourneyItemOut]


class PipelineStatusUpdateRequest(BaseModel):
    status_definition_id: int = Field(ge=1)
    comments: str | None = None


class PipelineStatusUpdateResponse(BaseModel):
    student_id: int
    status_definition_id: int
    stage_name: str | None = None
    history_id: int | None = None
    changed: bool = True


class BookingStatusUpdateRequest(BaseModel):
    status_definition_id: int = Field(ge=1)
    notes: str | None = None


class BookingStatusUpdateResponse(BaseModel):
    lead_id: int | None = None
    status_definition_id: int
    stage_name: str
    history_id: int
    trigger_outreach: bool = False
    booking_id: int | None = None
    booking_status: str | None = None
