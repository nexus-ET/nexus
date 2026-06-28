from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ClientAuditActionType = Literal[
    "PAGE_VIEW",
    "UI_CLICK",
    "UI_FIELD_CHANGE",
    "API_READ",
]


class ClientAuditEventIn(BaseModel):
    action_type: ClientAuditActionType
    page: str = Field(max_length=500)
    menu: str | None = Field(default=None, max_length=200)
    action: str = Field(max_length=300)
    target_resource: str = Field(default="ui_activity", max_length=100)
    resource_id: str | None = Field(default=None, max_length=100)
    element_type: str | None = Field(default=None, max_length=50)
    element_label: str | None = Field(default=None, max_length=300)
    metadata: dict[str, Any] | None = None


class ClientAuditEventsBatchIn(BaseModel):
    events: list[ClientAuditEventIn] = Field(min_length=1, max_length=100)
