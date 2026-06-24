from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QuarantineReasonBreakdown(BaseModel):
    reason: str
    label: str
    count: int


class IngestionQualityReport(BaseModel):
    total_received: int
    total_processed: int
    total_pending: int
    total_promoted: int
    total_quarantined: int
    total_reprocessed: int
    clean_ratio_percent: float
    quarantine_ratio_percent: float
    quarantine_reasons: list[QuarantineReasonBreakdown]
    sync_mode_filter: str | None = None


class LeadQuarantineOut(BaseModel):
    id: int
    raw_incoming_lead_id: int | None = None
    meta_leadgen_id: str
    original_payload: dict[str, Any]
    normalized_payload: dict[str, Any]
    error_reason: str
    error_code: str
    source: str
    sync_mode: str
    triggered_by_user: str
    lead_id: int | None = None
    reprocessed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LeadQuarantineListResponse(BaseModel):
    records: list[LeadQuarantineOut]
    total_count: int
    page: int
    limit: int
    total_pages: int


class LeadQuarantineUpdateRequest(BaseModel):
    normalized_payload: dict[str, Any] = Field(default_factory=dict)


class LeadQuarantineReprocessResponse(BaseModel):
    success: bool
    lead_id: int | None = None
    error_reason: str | None = None
    record: LeadQuarantineOut
