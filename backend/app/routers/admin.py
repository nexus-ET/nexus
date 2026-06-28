from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.lead_quarantine import (
    LeadQuarantineListResponse,
    LeadQuarantineOut,
    LeadQuarantineReprocessResponse,
    LeadQuarantineUpdateRequest,
)
from app.schemas.audit_log import AuditLogRetentionSetting, AuditLogsResponse
from app.services.audit_log_service import (
    ALLOWED_AUDIT_LOG_LIMITS,
    AUDIT_LOG_SORT_FIELDS,
    audit_logs_total_pages,
    list_audit_logs,
    list_audit_logs_for_export,
    parse_audit_date_param,
)
from app.services.audit_logger import get_audit_log_retention_days
from app.services.audit_service import log_action
from app.services.pdf_generator import generate_audit_logs_pdf
from app.services.leads import SaveLeadResult
from app.services.quarantine_service import (
    delete_quarantine_record,
    get_quarantine_record,
    list_quarantine_records,
    reprocess_quarantine,
    update_quarantine_payload,
)

router = APIRouter()


def _serialize(record) -> LeadQuarantineOut:
    return LeadQuarantineOut(
        id=record.id,
        raw_incoming_lead_id=record.raw_incoming_lead_id,
        meta_leadgen_id=record.meta_leadgen_id,
        original_payload=record.original_payload or {},
        normalized_payload=record.normalized_payload or {},
        error_reason=record.error_reason,
        error_code=record.error_code,
        source=record.source,
        sync_mode=record.sync_mode,
        triggered_by_user=record.triggered_by_user,
        lead_id=record.lead_id,
        reprocessed_at=record.reprocessed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/admin/quarantine", response_model=LeadQuarantineListResponse)
@router.get("/admin/quarantine/", response_model=LeadQuarantineListResponse)
def read_quarantine_records(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    rows, total_count = list_quarantine_records(db, page=page, limit=limit)
    total_pages = max(1, math.ceil(total_count / limit)) if total_count else 1
    return LeadQuarantineListResponse(
        records=[_serialize(row) for row in rows],
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/admin/quarantine/{record_id}", response_model=LeadQuarantineOut)
@router.get("/admin/quarantine/{record_id}/", response_model=LeadQuarantineOut)
def read_quarantine_record(
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    record = get_quarantine_record(db, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Quarantine record not found.")
    return _serialize(record)


@router.put("/admin/quarantine/{record_id}", response_model=LeadQuarantineOut)
@router.put("/admin/quarantine/{record_id}/", response_model=LeadQuarantineOut)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("update_quarantine_record", "lead_quarantine")
def update_quarantine_record(
    request: Request,
    record_id: int,
    payload: LeadQuarantineUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    record = get_quarantine_record(db, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Quarantine record not found.")
    updated = update_quarantine_payload(db, record, payload.normalized_payload)
    return _serialize(updated)


@router.post("/admin/quarantine/{record_id}/reprocess", response_model=LeadQuarantineReprocessResponse)
@router.post("/admin/quarantine/{record_id}/reprocess/", response_model=LeadQuarantineReprocessResponse)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("reprocess_quarantine_record", "lead_quarantine")
def reprocess_quarantine_record(
    request: Request,
    record_id: int,
    payload: LeadQuarantineUpdateRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    record = get_quarantine_record(db, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Quarantine record not found.")

    normalized = payload.normalized_payload if payload else None
    outcome = reprocess_quarantine(db, record, normalized_payload=normalized)

    if isinstance(outcome, SaveLeadResult):
        return LeadQuarantineReprocessResponse(
            success=True,
            lead_id=outcome.lead.id,
            error_reason=None,
            record=_serialize(get_quarantine_record(db, record_id) or record),
        )

    return LeadQuarantineReprocessResponse(
        success=False,
        lead_id=None,
        error_reason=outcome.error_reason,
        record=_serialize(outcome),
    )


@router.delete("/admin/quarantine/{record_id}", status_code=204)
@router.delete("/admin/quarantine/{record_id}/", status_code=204)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("delete_quarantine_record", "lead_quarantine")
def remove_quarantine_record(
    request: Request,
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    record = get_quarantine_record(db, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Quarantine record not found.")
    delete_quarantine_record(db, record)


@router.get("/admin/audit-logs", response_model=AuditLogsResponse)
@router.get("/admin/audit-logs/", response_model=AuditLogsResponse)
def read_audit_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="timestamp"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    if limit not in ALLOWED_AUDIT_LOG_LIMITS:
        raise HTTPException(status_code=400, detail="limit must be one of: 25, 50, 100")
    if sort_by not in AUDIT_LOG_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by. Allowed: {sorted(AUDIT_LOG_SORT_FIELDS)}")

    parsed_start = parse_audit_date_param(start_date)
    parsed_end = parse_audit_date_param(end_date, end_of_day=True)
    logs, total_count = list_audit_logs(
        db,
        page=page,
        limit=limit,
        start_date=parsed_start,
        end_date=parsed_end,
        user_id=user_id,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return AuditLogsResponse(
        logs=logs,
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=audit_logs_total_pages(total_count, limit),
    )


@router.get("/admin/audit-logs/export-pdf")
@router.get("/admin/audit-logs/export-pdf/")
def export_audit_logs_pdf(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="timestamp"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    if sort_by not in AUDIT_LOG_SORT_FIELDS:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by. Allowed: {sorted(AUDIT_LOG_SORT_FIELDS)}")

    parsed_start = parse_audit_date_param(start_date)
    parsed_end = parse_audit_date_param(end_date, end_of_day=True)
    logs = list_audit_logs_for_export(
        db,
        start_date=parsed_start,
        end_date=parsed_end,
        user_id=user_id,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    pdf_bytes = generate_audit_logs_pdf(
        db,
        logs=logs,
        start_date=parsed_start,
        end_date=parsed_end,
        sort_by=sort_by,
        sort_order=sort_order,
        generated_at=datetime.utcnow(),
    )
    filename = f"audit-logs-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/audit-logs/retention", response_model=AuditLogRetentionSetting)
@router.get("/admin/audit-logs/retention/", response_model=AuditLogRetentionSetting)
def read_audit_log_retention(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    return AuditLogRetentionSetting(audit_log_retention_days=get_audit_log_retention_days(db))


@router.put("/admin/audit-logs/retention", response_model=AuditLogRetentionSetting)
@router.put("/admin/audit-logs/retention/", response_model=AuditLogRetentionSetting)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("update_audit_log_retention", "audit_settings")
def update_audit_log_retention(
    request: Request,
    payload: AuditLogRetentionSetting,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    from app.models.dynamic_setting import DynamicSetting
    from app.services.settings_service import clear_settings_cache

    setting = db.query(DynamicSetting).filter(DynamicSetting.key == "AUDIT_LOG_RETENTION_DAYS").first()
    if setting is None:
        setting = DynamicSetting(key="AUDIT_LOG_RETENTION_DAYS", value=str(payload.audit_log_retention_days))
        db.add(setting)
    else:
        setting.value = str(payload.audit_log_retention_days)
    db.commit()
    clear_settings_cache()
    return AuditLogRetentionSetting(audit_log_retention_days=get_audit_log_retention_days(db))
