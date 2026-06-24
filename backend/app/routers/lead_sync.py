from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.lead_sync import LeadSyncConfigOut, LeadSyncConfigUpdateRequest, LeadSyncRunResponse
from app.services.audit_service import log_action
from app.services.lead_sync_settings import (
    get_lead_sync_config_for_api,
    run_lead_sync_isolated,
    save_lead_sync_config,
)
from app.services.sync_log_service import SOURCE_MANUAL_API, SYNC_MODE_MANUAL, format_user_label

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


@router.post("/settings/lead-sync/run", response_model=LeadSyncRunResponse)
@router.post("/settings/lead-sync/run/", response_model=LeadSyncRunResponse)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("run_lead_sync", "meta_leads")
async def trigger_lead_sync(
    request: Request,
    current_user: User = Depends(deps.require_super_admin),
):
    user_label = format_user_label(current_user)
    user_id = current_user.id
    result = await asyncio.to_thread(
        run_lead_sync_isolated,
        sync_mode=SYNC_MODE_MANUAL,
        triggered_by_user=user_label,
        triggered_by_user_id=user_id,
        source=SOURCE_MANUAL_API,
    )
    return LeadSyncRunResponse(**result)
