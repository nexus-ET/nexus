from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, ensure_db_connection, safe_close_session
from app.services.lead_sync_coordinator import release_lead_sync, try_acquire_lead_sync
from app.models.dynamic_setting import DynamicSetting
from app.models.sync_log import SyncLog
from app.services.facebook_leads import (
    MetaLeadsBackfillResult,
    backfill_historical_leads,
    resolve_backfill_credentials,
)
from app.services.leads import (
    format_no_new_leads_delta_message,
    resolve_delta_sync_cursor,
)
from app.services.settings_service import clear_settings_cache, get_setting
from app.services.sync_log_service import (
    SOURCE_MANUAL_API,
    STATUS_SUCCESS,
    SYNC_MODE_MANUAL,
    begin_sync_transaction,
    fail_sync_transaction,
    finalize_sync_transaction,
)

logger = logging.getLogger(__name__)

LeadSyncMode = Literal["automated", "manual"]
LeadSyncIntervalUnit = Literal["minutes", "hours", "days", "weeks"]

KEY_MODE = "META_LEAD_SYNC_MODE"
KEY_INTERVAL_VALUE = "META_LEAD_SYNC_INTERVAL_VALUE"
KEY_INTERVAL_UNIT = "META_LEAD_SYNC_INTERVAL_UNIT"
KEY_LAST_RUN_AT = "META_LEAD_SYNC_LAST_RUN_AT"
KEY_LAST_RUN_SUMMARY = "META_LEAD_SYNC_LAST_RUN_SUMMARY"

DEFAULT_MODE: LeadSyncMode = "automated"
DEFAULT_INTERVAL_VALUE = 1
DEFAULT_INTERVAL_UNIT: LeadSyncIntervalUnit = "hours"

INTERVAL_UNIT_LABELS: dict[LeadSyncIntervalUnit, str] = {
    "minutes": "Minutes",
    "hours": "Hours",
    "days": "Days",
    "weeks": "Weeks",
}


def seed_lead_sync_settings(db: Session) -> None:
    """Disabled — lead sync settings are managed via Admin UI, not startup seeds."""
    return


def _upsert_setting(db: Session, key: str, value: str, updated_by_user_id: int | None = None) -> None:
    row = db.query(DynamicSetting).filter(DynamicSetting.key == key).first()
    if row is None:
        row = DynamicSetting(key=key, value=value, updated_by_user_id=updated_by_user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
        row.updated_by_user_id = updated_by_user_id
    db.commit()
    clear_settings_cache()


def _parse_mode(raw: str | None) -> LeadSyncMode:
    normalized = (raw or DEFAULT_MODE).strip().lower()
    if normalized in {"automated", "auto"}:
        return "automated"
    if normalized == "manual":
        return "manual"
    return DEFAULT_MODE


def _parse_interval_unit(raw: str | None) -> LeadSyncIntervalUnit:
    normalized = (raw or DEFAULT_INTERVAL_UNIT).strip().lower()
    if normalized in INTERVAL_UNIT_LABELS:
        return normalized  # type: ignore[return-value]
    return DEFAULT_INTERVAL_UNIT


def _parse_interval_value(raw: str | None) -> int:
    try:
        value = int(str(raw or DEFAULT_INTERVAL_VALUE).strip())
    except ValueError:
        return DEFAULT_INTERVAL_VALUE
    return max(1, value)


def get_lead_sync_config(db: Session) -> dict[str, Any]:
    """Lead sync settings from the database only (no scheduler state)."""
    last_run_at_raw = get_setting(KEY_LAST_RUN_AT, default="", db=db) or ""
    last_summary_raw = get_setting(KEY_LAST_RUN_SUMMARY, default="", db=db) or ""
    last_summary: dict[str, Any] | None = None
    if last_summary_raw:
        try:
            last_summary = json.loads(last_summary_raw)
        except json.JSONDecodeError:
            last_summary = None

    mode = _parse_mode(get_setting(KEY_MODE, default=DEFAULT_MODE, db=db))
    interval_value = _parse_interval_value(
        get_setting(KEY_INTERVAL_VALUE, default=str(DEFAULT_INTERVAL_VALUE), db=db)
    )
    interval_unit = _parse_interval_unit(
        get_setting(KEY_INTERVAL_UNIT, default=DEFAULT_INTERVAL_UNIT, db=db)
    )

    return {
        "mode": mode,
        "interval_value": interval_value,
        "interval_unit": interval_unit,
        "interval_unit_label": INTERVAL_UNIT_LABELS[interval_unit],
        "last_run_at": last_run_at_raw or None,
        "last_run_summary": last_summary,
    }


def get_lead_sync_config_for_api(db: Session) -> dict[str, Any]:
    """Settings plus live scheduler status for Settings / Reports APIs."""
    from app.services.scheduler import get_lead_sync_scheduler_status

    return {**get_lead_sync_config(db), **get_lead_sync_scheduler_status()}


def validate_lead_sync_config(
    *,
    mode: str,
    interval_value: int,
    interval_unit: str,
) -> None:
    if _parse_mode(mode) not in {"automated", "manual"}:
        raise HTTPException(status_code=400, detail="Sync mode must be automated or manual.")
    if interval_value < 1:
        raise HTTPException(status_code=400, detail="Sync interval must be at least 1.")
    if interval_unit not in INTERVAL_UNIT_LABELS:
        raise HTTPException(
            status_code=400,
            detail="Sync interval unit must be minutes, hours, days, or weeks.",
        )


def save_lead_sync_config(
    db: Session,
    *,
    mode: str,
    interval_value: int,
    interval_unit: str,
    updated_by_user_id: int | None = None,
) -> dict[str, Any]:
    validate_lead_sync_config(
        mode=mode,
        interval_value=interval_value,
        interval_unit=interval_unit,
    )
    parsed_mode = _parse_mode(mode)
    parsed_unit = _parse_interval_unit(interval_unit)
    parsed_value = max(1, int(interval_value))

    _upsert_setting(db, KEY_MODE, parsed_mode, updated_by_user_id)
    _upsert_setting(db, KEY_INTERVAL_VALUE, str(parsed_value), updated_by_user_id)
    _upsert_setting(db, KEY_INTERVAL_UNIT, parsed_unit, updated_by_user_id)

    return get_lead_sync_config_for_api(db)


def _finalize_lead_sync_log(db: Session, log_id: int, result: MetaLeadsBackfillResult) -> None:
    """Complete sync audit row, including delta-sync empty success messaging."""
    finalize_kwargs: dict[str, Any] = {
        "forms_processed": result.forms_processed,
        "leads_seen": result.leads_seen,
        "leads_created": result.leads_created,
        "leads_skipped": result.leads_skipped,
        "errors": result.errors,
    }
    since_label = result.delta_since_label or ""
    if result.leads_seen == 0 and not result.errors and since_label:
        finalize_kwargs["status"] = STATUS_SUCCESS
        finalize_kwargs["message"] = format_no_new_leads_delta_message(since_label)
    finalize_sync_transaction(db, log_id, **finalize_kwargs)


def _persist_last_run(db: Session, result: MetaLeadsBackfillResult) -> dict[str, Any]:
    summary = result.as_dict()
    run_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _upsert_setting(db, KEY_LAST_RUN_AT, run_at)
    _upsert_setting(db, KEY_LAST_RUN_SUMMARY, json.dumps(summary))
    return {"run_at": run_at, **summary}


def run_lead_sync(
    db: Session,
    *,
    sync_mode: str = SYNC_MODE_MANUAL,
    triggered_by_user: str = "UNKNOWN",
    triggered_by_user_id: int | None = None,
    source: str = SOURCE_MANUAL_API,
    sync_log_id: int | None = None,
    raise_http_errors: bool = True,
) -> dict[str, Any]:
    """Fetch only Meta leads created after the latest stored Meta lead (delta sync)."""
    logger.info(
        "Meta lead sync starting (mode=%s, triggered_by=%s, log_id=%s)...",
        sync_mode,
        triggered_by_user,
        sync_log_id,
    )

    if sync_log_id is None:
        log_row = begin_sync_transaction(
            db,
            sync_mode=sync_mode,
            triggered_by_user=triggered_by_user,
            triggered_by_user_id=triggered_by_user_id,
            source=source,
        )
    else:
        log_row = db.query(SyncLog).filter(SyncLog.id == sync_log_id).first()
        if log_row is None:
            log_row = begin_sync_transaction(
                db,
                sync_mode=sync_mode,
                triggered_by_user=triggered_by_user,
                triggered_by_user_id=triggered_by_user_id,
                source=source,
            )

    result: MetaLeadsBackfillResult | None = None
    try:
        try:
            page_id, access_token = resolve_backfill_credentials()
        except ValueError as exc:
            logger.warning("Meta lead sync skipped: %s", exc)
            fail_sync_transaction(db, log_row.id, error=str(exc))
            if raise_http_errors:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"sync_log_id": log_row.id, "error": str(exc)}

        delta_cursor = resolve_delta_sync_cursor(db)
        logger.info(
            "Meta delta sync cursor since=%s (%s) initial_backfill=%s",
            delta_cursor.since_unix,
            delta_cursor.since_label,
            delta_cursor.is_initial_backfill,
        )
        try:
            result = backfill_historical_leads(
                db,
                page_id,
                access_token,
                since=delta_cursor.since_unix,
                request_delay_seconds=0.25,
                delta_since_label=delta_cursor.since_label,
                delta_is_initial_backfill=delta_cursor.is_initial_backfill,
                sync_mode=sync_mode,
                triggered_by_user=triggered_by_user,
                triggered_by_user_id=triggered_by_user_id,
                source=source,
                sync_log_id=log_row.id,
            )
        except Exception as exc:
            logger.exception("Meta lead sync failed.")
            fail_sync_transaction(db, log_row.id, error=f"Lead sync failed: {exc}")
            if raise_http_errors:
                raise HTTPException(status_code=500, detail=f"Lead sync failed: {exc}") from exc
            return {"sync_log_id": log_row.id, "error": str(exc)}
    finally:
        if result is not None:
            ensure_db_connection(db)
            _finalize_lead_sync_log(db, log_row.id, result)

    if result is None:
        if raise_http_errors:
            raise HTTPException(status_code=500, detail="Lead sync did not produce a result.")
        return {"sync_log_id": log_row.id, "error": "Lead sync did not produce a result."}

    ensure_db_connection(db)
    payload = _persist_last_run(db, result)
    logger.info(
        "Meta lead sync finished (mode=%s, triggered_by=%s): forms=%s seen=%s saved=%s skipped=%s errors=%s",
        sync_mode,
        triggered_by_user,
        result.forms_processed,
        result.leads_seen,
        result.leads_created,
        result.leads_skipped,
        len(result.errors),
    )
    payload["sync_log_id"] = log_row.id
    return payload


def run_lead_sync_isolated(**kwargs: Any) -> dict[str, Any]:
    """Run lead sync on a dedicated DB session (safe for asyncio.to_thread)."""
    raise_http_errors = bool(kwargs.get("raise_http_errors", True))
    db = SessionLocal()
    if not try_acquire_lead_sync(db):
        safe_close_session(db)
        if raise_http_errors:
            raise HTTPException(
                status_code=409,
                detail="A Meta lead sync is already in progress. Try again when it finishes.",
            )
        return {"skipped": True, "error": "sync already in progress"}
    try:
        return run_lead_sync(db, **kwargs)
    finally:
        release_lead_sync(db)
        safe_close_session(db)
