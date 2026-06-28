from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    user_email: str | None = None
    user_name: str | None = None
    action_type: str
    target_resource: str
    resource_id: str | None = None
    details: dict | None = None
    ip_address: str | None = None
    timestamp: datetime
    session_id: str | None = None
    sync_mode: str | None = None
    user_agent: str | None = None
    status: str

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        fraction = f"{value.microsecond:06d}"
        return value.strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction}"


class AuditLogsResponse(BaseModel):
    logs: list[AuditLogOut]
    total_count: int
    page: int
    limit: int
    total_pages: int


class AuditLogRetentionSetting(BaseModel):
    audit_log_retention_days: int = Field(ge=1, le=3650)
