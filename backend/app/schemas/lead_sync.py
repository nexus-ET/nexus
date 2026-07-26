from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

LeadSyncMode = Literal["automated", "manual"]
LeadSyncIntervalUnit = Literal["minutes", "hours", "days", "weeks"]


class LeadSyncConfigOut(BaseModel):
    mode: LeadSyncMode
    interval_value: int
    interval_unit: LeadSyncIntervalUnit
    interval_unit_label: str
    last_run_at: str | None = None
    last_run_summary: dict[str, Any] | None = None
    scheduler_enabled: bool = True
    scheduler_active: bool = False
    scheduler_is_leader: bool = False
    configured_interval: str | None = None
    configured_schedule: str | None = None
    active_job_interval: str | None = None
    next_scheduled_run_at: str | None = None


class LeadSyncConfigUpdateRequest(BaseModel):
    mode: LeadSyncMode
    interval_value: int = Field(default=1, ge=1, le=10_000)
    interval_unit: LeadSyncIntervalUnit = "hours"


class LeadSyncRunResponse(BaseModel):
    run_at: str
    forms_processed: int
    leads_seen: int
    leads_created: int
    leads_skipped: int
    errors: list[str]
    sync_log_id: int | None = None
    delta_since_unix: str | None = None
    delta_since_label: str | None = None
    delta_is_initial_backfill: bool = False


class LeadSyncStartResponse(BaseModel):
    """Immediate ack when Sync Now is accepted as a background job."""

    accepted: bool = True
    status: str = "IN_PROGRESS"
    sync_log_id: int
    message: str = "Meta lead sync started. Poll status until the run completes."


class LeadSyncRunStatusOut(BaseModel):
    sync_log_id: int
    status: str
    message: str | None = None
    forms_processed: int = 0
    leads_seen: int = 0
    leads_created: int = 0
    leads_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    run_at: str | None = None
    completed_at: str | None = None
