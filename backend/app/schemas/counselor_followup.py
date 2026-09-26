from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CounselorStatusMasterItem(BaseModel):
    id: int
    status_key: str
    status_heading: str
    default_description: str
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class CounselorStatusMasterListResponse(BaseModel):
    items: list[CounselorStatusMasterItem]


class CounselorFollowupCreate(BaseModel):
    status_id: int
    points_discussed: str = Field(..., min_length=1, max_length=20000)
    action_items: str | None = Field(default=None, max_length=20000)
    target_completion_date: date | None = None
    send_document_checklist_email: bool = False
    checklist_program_level: str | None = Field(default=None, max_length=50)
    checklist_scope: str | None = Field(default=None, max_length=32)
    checklist_country_id: int | None = None

    @field_validator("checklist_program_level", mode="before")
    @classmethod
    def strip_checklist_level(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("checklist_scope", mode="before")
    @classmethod
    def strip_checklist_scope(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def checklist_fields_when_sending(self) -> CounselorFollowupCreate:
        if not self.send_document_checklist_email:
            return self
        if not self.checklist_program_level:
            raise ValueError(
                "Select a program level before sending the document checklist email."
            )
        scope = (self.checklist_scope or "global").strip().lower()
        if scope in {"country_specific", "country-specific", "country"}:
            if self.checklist_country_id is None:
                raise ValueError(
                    "Select a country before sending a country-specific document checklist."
                )
        return self


class CounselorFollowupUpdate(BaseModel):
    """Four fields the Notes page edits on the latest counselor note."""

    status_id: int
    points_discussed: str = Field(..., min_length=1, max_length=20000)
    action_items: str | None = Field(default=None, max_length=20000)
    target_completion_date: date | None = None


class CounselorFollowupSentDocument(BaseModel):
    label: str
    url: str | None = None
    link_unavailable: bool = False


class CounselorFollowupItem(BaseModel):
    id: int
    lead_id: int
    counselor_id: str | None = None
    counselor_name: str | None = None
    status_id: int
    status_key: str
    status_heading: str
    points_discussed: str
    action_items: str | None = None
    target_completion_date: date | None = None
    created_at: datetime
    email_sent: bool | None = None
    email_error: str | None = None
    checklist_email_to: str | None = None
    checklist_email_sent_at: datetime | None = None
    checklist_sent_documents: list[CounselorFollowupSentDocument] | None = None

    model_config = ConfigDict(from_attributes=True)


class CounselorFollowupListResponse(BaseModel):
    items: list[CounselorFollowupItem]
    total: int
