from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import SessionLocal, safe_close_session
from app.services.lead_sync_coordinator import release_lead_sync, try_acquire_lead_sync
from app.models.user import User
from app.schemas.meta_leads import MetaLeadsBackfillRequest, MetaLeadsBackfillResponse
from app.services.facebook_leads import backfill_historical_leads, resolve_backfill_credentials
from app.services.lead_sync_settings import _finalize_lead_sync_log
from app.services.leads import resolve_delta_sync_cursor
from app.services.sync_log_service import (
    SOURCE_BACKFILL,
    SYNC_MODE_MANUAL,
    begin_sync_transaction,
    fail_sync_transaction,
    format_user_label,
)

router = APIRouter()


@router.post("/meta/leads/backfill", response_model=MetaLeadsBackfillResponse)
@limiter.limit(STRICT_RATE_LIMIT)
async def trigger_meta_leads_backfill(
    request: Request,
    body: MetaLeadsBackfillRequest,
    current_user: User = Depends(deps.require_super_admin),
) -> MetaLeadsBackfillResponse:
    try:
        page_id, access_token = resolve_backfill_credentials(
            page_id=body.page_id,
            access_token=body.access_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_label = format_user_label(current_user)
    user_id = current_user.id

    def _run_backfill():
        db = SessionLocal()
        if not try_acquire_lead_sync(db):
            safe_close_session(db)
            raise HTTPException(
                status_code=409,
                detail="A Meta lead sync is already in progress. Try again when it finishes.",
            )
        log_row = begin_sync_transaction(
            db,
            sync_mode=SYNC_MODE_MANUAL,
            triggered_by_user=user_label,
            triggered_by_user_id=user_id,
            source=SOURCE_BACKFILL,
        )
        result = None
        try:
            try:
                since = body.since
                delta_label = None
                delta_initial = False
                if since is None:
                    cursor = resolve_delta_sync_cursor(db)
                    since = cursor.since_unix
                    delta_label = cursor.since_label
                    delta_initial = cursor.is_initial_backfill
                result = backfill_historical_leads(
                    db,
                    page_id,
                    access_token,
                    since=since,
                    until=body.until,
                    request_delay_seconds=body.request_delay_seconds,
                    delta_since_label=delta_label,
                    delta_is_initial_backfill=delta_initial,
                    sync_mode=SYNC_MODE_MANUAL,
                    triggered_by_user=user_label,
                    triggered_by_user_id=user_id,
                    source=SOURCE_BACKFILL,
                    sync_log_id=log_row.id,
                )
            except Exception as exc:
                fail_sync_transaction(db, log_row.id, error=str(exc))
                raise
            finally:
                if result is not None:
                    _finalize_lead_sync_log(db, log_row.id, result)
            return result
        finally:
            release_lead_sync(db)
            safe_close_session(db)

    result = await asyncio.to_thread(_run_backfill)
    if result is None:
        raise HTTPException(status_code=500, detail="Backfill did not produce a result.")

    return MetaLeadsBackfillResponse(**result.as_dict())
