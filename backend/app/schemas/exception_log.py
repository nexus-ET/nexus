from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from typing import Literal


class ExceptionLogOut(BaseModel):
    id: int
    severity: str
    source: str
    category: str
    status: str
    triggered_by_user: str
    triggered_by_user_id: int | None = None
    message: str
    details: list[str] = Field(default_factory=list)
    page_path: str | None = None
    exception_type: str | None = None
    related_resource: str | None = None
    related_id: str | None = None
    attempt_timestamp: datetime
    resolved_at: datetime | None = None
    resolution_comment: str | None = None


class ExceptionLogsResponse(BaseModel):
    logs: list[ExceptionLogOut]
    total_count: int
    page: int = 1
    limit: int = 25
    total_pages: int = 1


class ExceptionLogCreateRequest(BaseModel):
    """Client/backend intake for a new exception/omission row."""

    severity: str = "ERROR"
    source: str = "api_client"
    category: str = "general"
    message: str = Field(..., min_length=1, max_length=4000)
    details: list[str] = Field(default_factory=list)
    page_path: str | None = None
    exception_type: str | None = None
    related_resource: str | None = None
    related_id: str | None = None


class ExceptionLogStatusUpdate(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
    resolution_comment: str | None = Field(
        default=None,
        max_length=4000,
        description="How the issue was fixed. Required for manual Resolve unless resolved_by is set.",
    )
    resolved_by: Literal[
        "admin",
        "cursor_agent",
        "server_recovery",
        "page_refresh",
        "successful_sync",
        "system",
    ] | None = Field(
        default=None,
        description=(
            "When set for automated/Cursor resolutions, a standard resolution comment "
            "is filled in if resolution_comment is omitted."
        ),
    )


class ExceptionLogAutoResolveRequest(BaseModel):
    """Bulk auto-resolve open exceptions with a generated resolution comment."""

    mode: Literal[
        "page_refresh",
        "server_recovery",
        "cursor_agent",
        "successful_sync",
        "lead_sync_lock",
        "lead_sync_failure",
        "transient_client",
    ]
    detail: str | None = Field(default=None, max_length=2000)
    exception_ids: list[int] | None = Field(default=None, max_length=200)


class ExceptionLogAutoResolveResponse(BaseModel):
    resolved_count: int
    mode: str
    resolution_comment: str | None = None


class ExceptionLogRetentionSetting(BaseModel):
    exception_log_retention_days: int = Field(ge=1, le=3650)
    deleted_count: int | None = Field(
        default=None,
        description="Rows permanently deleted when retention is saved (PUT only).",
    )
