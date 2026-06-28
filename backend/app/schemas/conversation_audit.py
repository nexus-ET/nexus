from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationAuditLogRead(BaseModel):
    id: int
    lead_id: int
    student_message: str
    ai_reply: str
    ai_model: str
    confidence_score: float | None = None
    escalated: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationAuditListResponse(BaseModel):
    items: list[ConversationAuditLogRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class ConversationAuditCandidateSummary(BaseModel):
    lead_id: int
    student_name: str | None = None
    turn_count: int
    latest_student_message: str
    latest_ai_reply: str
    latest_ai_model: str
    latest_confidence_score: float | None = None
    latest_escalated: bool
    has_escalated: bool
    last_activity_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationAuditCandidateListResponse(BaseModel):
    items: list[ConversationAuditCandidateSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class ConversationAuditQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = None
    status: str | None = Field(default=None, description="all | escalated | ai_active")
    sort_by: str = Field(default="created_at")
    order: str = Field(default="desc")
