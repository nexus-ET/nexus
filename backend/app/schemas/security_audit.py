from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SecurityCheckResult(BaseModel):
    name: str
    category: str
    passed: bool
    message: str


class SecurityAuditRunOut(BaseModel):
    id: int
    status: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    red_flags: bool
    triggered_by: str
    triggered_by_user_id: int | None = None
    checks: list[SecurityCheckResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class SecurityAuditRunsResponse(BaseModel):
    runs: list[SecurityAuditRunOut]
    latest_status: str | None = None


class SecurityAuditStatusResponse(BaseModel):
    latest_run: SecurityAuditRunOut | None = None
    fortress_healthy: bool = True


class SecurityAuditTriggerResponse(BaseModel):
    run: SecurityAuditRunOut
    alert_sent: bool = False
