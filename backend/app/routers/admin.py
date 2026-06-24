from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from app.services.audit_service import log_action
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
