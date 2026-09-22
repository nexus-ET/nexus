from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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


class CounselorFollowupItem(BaseModel):
    id: int
    lead_id: int
    counselor_id: str | None = None
    status_id: int
    status_key: str
    status_heading: str
    points_discussed: str
    action_items: str | None = None
    target_completion_date: date | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CounselorFollowupListResponse(BaseModel):
    items: list[CounselorFollowupItem]
    total: int
