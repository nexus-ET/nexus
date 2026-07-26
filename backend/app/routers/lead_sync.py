from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.lead_sync import (
    LeadSyncConfigOut,
    LeadSyncConfigUpdateRequest,
    LeadSyncRunStatusOut,
    LeadSyncStartResponse,
)
from app.services.audit_context import build_audit_details
from app.services.audit_logger import write_audit_log
from app.services.audit_service import log_action
from app.services.lead_sync_settings import (
    get_lead_sync_config_for_api,
    get_manual_lead_sync_status,
    save_lead_sync_config,
    start_manual_lead_sync_background,
)
from app.services.sync_log_service import format_user_label

router = APIRouter()


@router.get("/settings/lead-sync", response_model=LeadSyncConfigOut)
@router.get("/settings/lead-sync/", response_model=LeadSyncConfigOut)
def read_lead_sync_settings(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    from app.services.scheduler import reconcile_lead_sync_scheduler_from_settings

    reconcile_lead_sync_scheduler_from_settings()
    return LeadSyncConfigOut(**get_lead_sync_config_for_api(db))


@router.put("/settings/lead-sync", response_model=LeadSyncConfigOut)
@router.put("/settings/lead-sync/", response_model=LeadSyncConfigOut)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("update_lead_sync_settings", "dynamic_setting")
def update_lead_sync_settings(
    request: Request,
    payload: LeadSyncConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    updated = save_lead_sync_config(
        db,
        mode=payload.mode,
        interval_value=payload.interval_value,
        interval_unit=payload.interval_unit,
        updated_by_user_id=current_user.id,
    )
    from app.services.scheduler import reschedule_lead_sync_job

    reschedule_lead_sync_job(run_immediately=False)
    return LeadSyncConfigOut(**updated)


@router.post("/settings/lead-sync/run", response_model=LeadSyncStartResponse)
@router.post("/settings/lead-sync/run/", response_model=LeadSyncStartResponse)
@limiter.limit(STRICT_RATE_LIMIT)
def trigger_lead_sync(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    """
    Start Meta lead sync in the background and return immediately.

    Long Graph API work continues server-side; clients should poll
    ``GET /settings/lead-sync/runs/{sync_log_id}`` (and Sync Logs) for completion.
    """
    user_label = format_user_label(current_user)
    user_id = current_user.id

    try:
        started = start_manual_lead_sync_background(
            triggered_by_user=user_label,
            triggered_by_user_id=user_id,
        )
    except HTTPException as exc:
        write_audit_log(
            db,
            user_id=user_id,
            action_type="run_lead_sync",
            target_resource="meta_leads",
            request=request,
            status="failed",
            details=build_audit_details(
                method=request.method,
                api_path=str(request.url.path),
                status_code=exc.status_code,
                action_type="run_lead_sync",
                referer=request.headers.get("referer"),
                ui_page_header=request.headers.get("x-nexus-page"),
                extra={"error": str(exc.detail)},
            ),
        )
        raise

    write_audit_log(
        db,
        user_id=user_id,
        action_type="run_lead_sync",
        target_resource="meta_leads",
        resource_id=str(started["sync_log_id"]),
        request=request,
        status="success",
        details=build_audit_details(
            method=request.method,
            api_path=str(request.url.path),
            status_code=202,
            action_type="run_lead_sync",
            referer=request.headers.get("referer"),
            ui_page_header=request.headers.get("x-nexus-page"),
            extra={
                "sync_log_id": started["sync_log_id"],
                "accepted": True,
                "note": "Sync accepted for background execution",
            },
        ),
    )
    return LeadSyncStartResponse(**started)


@router.get("/settings/lead-sync/runs/{sync_log_id}", response_model=LeadSyncRunStatusOut)
@router.get("/settings/lead-sync/runs/{sync_log_id}/", response_model=LeadSyncRunStatusOut)
def read_lead_sync_run_status(
    sync_log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    return LeadSyncRunStatusOut(**get_manual_lead_sync_status(db, sync_log_id))
