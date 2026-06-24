from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SyncLogOut(BaseModel):
    id: int
    sync_mode: str
    triggered_by_user: str
    triggered_by_user_id: int | None = None
    source: str
    status: str
    results_count: int
    message: str | None = None
    forms_processed: int
    leads_seen: int
    leads_created: int
    leads_skipped: int
    errors: list[str] = Field(default_factory=list)
    attempt_timestamp: datetime
    completed_at: datetime | None = None


class SyncLogsResponse(BaseModel):
    logs: list[SyncLogOut]
    total_count: int
    page: int = 1
    limit: int = 25
    total_pages: int = 1


class ReportsSyncScheduleOut(BaseModel):
    mode: str
    interval_value: int
    interval_unit: str
    interval_label: str
    configured_schedule: str | None = None
    scheduler_enabled: bool = True
    scheduler_active: bool = False
    scheduler_is_leader: bool = False
    next_scheduled_run_at: str | None = None
    help_text: str
