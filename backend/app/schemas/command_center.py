from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import validate_chat_message_length


class OperationalPulseResponse(BaseModel):
    pending_review: int
    stalled_candidates: int
    open_tasks: int
    scheduled_sessions: int
    awaiting_docs_reminders: int
    security_status: str
    security_healthy: bool
    security_run_id: int | None = None
    security_checked_at: datetime | None = None


class PipelineCardOut(BaseModel):
    lead_id: int
    full_name: str
    email: str | None = None
    phone_number: str | None = None
    admission_stage: str
    assigned_advisor_id: int | None = None
    is_stalled: bool = False
    latest_booking_id: int | None = None
    updated_at: datetime | None = None


class PipelineBoardResponse(BaseModel):
    stages: list[dict]
    columns: dict[str, list[PipelineCardOut]]


class TaskItemOut(BaseModel):
    id: int
    lead_id: int
    booking_id: int | None = None
    title: str
    status: str
    candidate_name: str
    created_at: datetime


class TasksResponse(BaseModel):
    tasks: list[TaskItemOut]


class PipelineMoveRequest(BaseModel):
    lead_id: int
    stage: str = Field(min_length=1, max_length=50)


class AssignLeadRequest(BaseModel):
    lead_id: int


class ChatMessageOut(BaseModel):
    id: int
    sender_user_id: int
    sender_name: str
    text: str
    lead_id: int | None = None
    media_url: str | None = None
    file_name: str | None = None
    message_type: str
    delivery_status: str
    read_at: datetime | None = None
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    messages: list[ChatMessageOut]


class ChatSendRequest(BaseModel):
    text: str = Field(min_length=0)
    lead_id: int | None = None

    @field_validator("text")
    @classmethod
    def validate_text_length(cls, value: str) -> str:
        return validate_chat_message_length(value)


class ChatReadRequest(BaseModel):
    up_to_message_id: int


class TypingRequest(BaseModel):
    is_typing: bool = True
