from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.models.sync_log import SyncLog
from app.models.user import User
from app.schemas.sync_log import SyncLogOut
from app.services.lead_sync_errors import sanitize_stored_sync_error

SYNC_MODE_AUTOMATED = "AUTOMATED"
SYNC_MODE_MANUAL = "MANUAL"

TRIGGERED_BY_SYSTEM = "SYSTEM_SCHEDULER"
TRIGGERED_BY_WEBHOOK = "META_WEBHOOK"

SOURCE_SCHEDULED = "scheduled"
SOURCE_WEBHOOK = "webhook"
SOURCE_MANUAL_API = "manual_api"
SOURCE_BACKFILL = "backfill"

STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_SUCCESS = "SUCCESS"
STATUS_WARNING = "WARNING"
STATUS_FAILED = "FAILED"

KEY_LAST_RUN_AT = "META_LEAD_SYNC_LAST_RUN_AT"
KEY_LAST_RUN_SUMMARY = "META_LEAD_SYNC_LAST_RUN_SUMMARY"
KEY_SYNC_MODE = "META_LEAD_SYNC_MODE"

_LEGACY_STATUS_MAP = {
    "success": STATUS_SUCCESS,
    "partial": STATUS_WARNING,
    "failed": STATUS_FAILED,
    "running": STATUS_IN_PROGRESS,
}


def normalize_status(raw: str | None) -> str:
    value = (raw or STATUS_IN_PROGRESS).strip().upper()
    if value in {STATUS_IN_PROGRESS, STATUS_SUCCESS, STATUS_WARNING, STATUS_FAILED}:
        return value
    return _LEGACY_STATUS_MAP.get(value.lower(), STATUS_IN_PROGRESS)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_legacy_timestamp(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _build_message(*, fatal_error: str | None, errors: list[str], default: str) -> str:
    if fatal_error:
        return fatal_error
    if errors:
        summary = "; ".join(errors[:3])
        if len(errors) > 3:
            summary += f" (+{len(errors) - 3} more)"
        return summary
    return default


def resolve_transaction_outcome(
    *,
    fatal_error: str | None = None,
    leads_seen: int = 0,
    leads_created: int = 0,
    leads_skipped: int = 0,
    errors: list[str] | None = None,
) -> tuple[str, int, str]:
    """
    Determine audit status, results_count, and message for a completed sync transaction.

    results_count = newly created leads only (what Reports shows as "new records").
    """
    error_items = errors or []
    results_count = leads_created

    if fatal_error:
        return STATUS_FAILED, 0, fatal_error

    if error_items and results_count == 0 and leads_seen == 0:
        return STATUS_FAILED, 0, _build_message(fatal_error=None, errors=error_items, default="Sync failed.")

    if leads_seen == 0:
        return STATUS_WARNING, 0, "Sync completed. 0 new leads (none in sync window)."

    if error_items and results_count == 0 and leads_skipped == 0:
        return STATUS_FAILED, 0, _build_message(fatal_error=None, errors=error_items, default="Sync failed.")

    if error_items:
        summary = f"Sync completed. {results_count} new lead(s)."
        if leads_skipped:
            summary += f" {leads_skipped} existing lead(s) updated."
        return (
            STATUS_WARNING,
            results_count,
            f"{summary} {_build_message(fatal_error=None, errors=error_items, default='').strip()}".strip(),
        )

    if results_count == 0 and leads_skipped > 0:
        return (
            STATUS_WARNING,
            0,
            f"Sync completed. 0 new leads ({leads_skipped} existing lead(s) updated).",
        )

    if results_count == 0:
        return STATUS_WARNING, 0, "Sync completed. 0 new leads."

    summary = f"Sync completed. {results_count} new lead(s)."
    if leads_skipped:
        summary += f" {leads_skipped} existing lead(s) updated."
    return STATUS_SUCCESS, results_count, summary


def seed_sync_logs_from_legacy_settings(db: Session) -> int:
    if db.query(SyncLog).count() > 0:
        return 0

    from app.services.settings_service import get_setting

    last_run_at_raw = get_setting(KEY_LAST_RUN_AT, default="", db=db) or ""
    last_summary_raw = get_setting(KEY_LAST_RUN_SUMMARY, default="", db=db) or ""
    if not last_run_at_raw or not last_summary_raw:
        return 0

    try:
        summary = json.loads(last_summary_raw)
    except json.JSONDecodeError:
        return 0

    if not isinstance(summary, dict):
        return 0

    attempt_at = _parse_legacy_timestamp(last_run_at_raw) or _utcnow_naive()
    mode_raw = (get_setting(KEY_SYNC_MODE, default="automated", db=db) or "automated").strip().lower()
    sync_mode = SYNC_MODE_AUTOMATED if mode_raw in {"automated", "auto"} else SYNC_MODE_MANUAL
    errors = summary.get("errors") or []
    if not isinstance(errors, list):
        errors = [str(errors)]

    leads_seen = int(summary.get("leads_seen") or 0)
    leads_created = int(summary.get("leads_created") or 0)
    leads_skipped = int(summary.get("leads_skipped") or 0)
    status, results_count, message = resolve_transaction_outcome(
        leads_seen=leads_seen,
        leads_created=leads_created,
        leads_skipped=leads_skipped,
        errors=[str(item) for item in errors],
    )

    row = SyncLog(
        sync_mode=sync_mode,
        triggered_by_user=TRIGGERED_BY_SYSTEM,
        triggered_by_user_id=None,
        source=SOURCE_SCHEDULED,
        status=status,
        results_count=results_count,
        message=message,
        forms_processed=int(summary.get("forms_processed") or 0),
        leads_seen=leads_seen,
        leads_created=leads_created,
        leads_skipped=leads_skipped,
        errors_json=json.dumps([str(item) for item in errors]),
        attempt_timestamp=attempt_at,
        completed_at=attempt_at,
    )
    db.add(row)
    db.commit()
    return 1


def format_user_label(user: User | None) -> str:
    if user is None:
        return "UNKNOWN"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip()
    if full_name:
        return full_name
    email = (user.email or "").strip()
    if email:
        return email
    return f"User #{user.id}"


def _runner_label() -> str:
    host = socket.gethostname().split(".")[0]
    return f"{host}:{os.getpid()}"


def begin_sync_transaction(
    db: Session,
    *,
    sync_mode: str,
    triggered_by_user: str,
    triggered_by_user_id: int | None = None,
    source: str,
) -> SyncLog:
    """Create an IN_PROGRESS audit record before any external API work begins."""
    now = _utcnow_naive()
    row = SyncLog(
        sync_mode=sync_mode,
        triggered_by_user=triggered_by_user,
        triggered_by_user_id=triggered_by_user_id,
        source=source,
        status=STATUS_IN_PROGRESS,
        results_count=0,
        message=f"Sync attempt started (runner={_runner_label()}).",
        started_at=now,
        attempt_timestamp=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def finalize_sync_transaction(
    db: Session,
    log_id: int,
    *,
    forms_processed: int = 0,
    leads_seen: int = 0,
    leads_created: int = 0,
    leads_skipped: int = 0,
    errors: list[str] | None = None,
    fatal_error: str | None = None,
    message: str | None = None,
    status: str | None = None,
) -> SyncLog | None:
    row = db.query(SyncLog).filter(SyncLog.id == log_id).first()
    if row is None:
        return None

    if normalize_status(row.status) != STATUS_IN_PROGRESS:
        return row

    error_items = [str(item) for item in (errors or [])]
    if message is None or status is None:
        resolved_status, results_count, resolved_message = resolve_transaction_outcome(
            fatal_error=fatal_error,
            leads_seen=leads_seen,
            leads_created=leads_created,
            leads_skipped=leads_skipped,
            errors=error_items,
        )
        if message is None:
            message = resolved_message
        if status is None:
            status = resolved_status
    else:
        results_count = leads_created

    row.forms_processed = forms_processed
    row.leads_seen = leads_seen
    row.leads_created = leads_created
    row.leads_skipped = leads_skipped
    row.errors_json = json.dumps(error_items)
    row.status = normalize_status(status)
    row.results_count = results_count
    row.message = message
    row.completed_at = _utcnow_naive()
    db.commit()
    db.refresh(row)
    return row


def fail_sync_transaction(db: Session, log_id: int, *, error: str) -> SyncLog | None:
    return finalize_sync_transaction(db, log_id, fatal_error=error)


def record_skipped_sync_transaction(
    db: Session,
    *,
    sync_mode: str,
    triggered_by_user: str,
    source: str,
    reason: str,
) -> SyncLog:
    """Write a completed audit row when a scheduled tick could not start work."""
    row = begin_sync_transaction(
        db,
        sync_mode=sync_mode,
        triggered_by_user=triggered_by_user,
        source=source,
    )
    if normalize_status(row.status) != STATUS_IN_PROGRESS:
        return row
    row.status = STATUS_WARNING
    row.results_count = 0
    row.message = reason
    row.completed_at = _utcnow_naive()
    row.errors_json = json.dumps([])
    db.commit()
    db.refresh(row)
    return row


# Backward-compatible aliases used by existing call sites.
start_sync_log = begin_sync_transaction
complete_sync_log = finalize_sync_transaction
fail_sync_log = fail_sync_transaction


def serialize_sync_log(row: SyncLog) -> SyncLogOut:
    errors: list[str] = []
    if row.errors_json:
        try:
            parsed = json.loads(row.errors_json)
            if isinstance(parsed, list):
                errors = [sanitize_stored_sync_error(str(item)) for item in parsed]
        except json.JSONDecodeError:
            errors = [row.errors_json]

    attempt_ts = getattr(row, "attempt_timestamp", None) or getattr(row, "started_at", None)
    results_count = getattr(row, "results_count", None)
    if results_count is None:
        results_count = int(row.leads_created or 0)

    message = getattr(row, "message", None)
    if not message and errors:
        message = _build_message(fatal_error=None, errors=errors, default="")
    elif not message and normalize_status(row.status) == STATUS_SUCCESS:
        message = "Sync completed successfully."
    elif not message and normalize_status(row.status) == STATUS_WARNING:
        if int(row.leads_created or 0) == 0:
            message = "Sync completed. 0 new leads."
        else:
            message = f"Sync completed. {int(row.leads_created or 0)} new lead(s)."
    elif not message and normalize_status(row.status) == STATUS_FAILED:
        message = "Sync failed."
    elif message and ("SQL:" in message or "[SQL:" in message or "UniqueViolation" in message):
        parts = [part.strip() for part in message.split("; ") if part.strip()]
        message = "; ".join(sanitize_stored_sync_error(part) for part in parts)

    return SyncLogOut(
        id=row.id,
        sync_mode=row.sync_mode,
        triggered_by_user=row.triggered_by_user,
        triggered_by_user_id=row.triggered_by_user_id,
        source=row.source,
        status=normalize_status(row.status),
        results_count=results_count,
        message=message,
        forms_processed=row.forms_processed,
        leads_seen=row.leads_seen,
        leads_created=row.leads_created,
        leads_skipped=row.leads_skipped,
        errors=errors,
        attempt_timestamp=attempt_ts or row.created_at,
        completed_at=row.completed_at,
    )


SYNC_LOG_SORT_FIELDS: dict[str, object] = {
    "attempt_timestamp": SyncLog.attempt_timestamp,
    "sync_mode": SyncLog.sync_mode,
    "source": SyncLog.source,
    "triggered_by_user": SyncLog.triggered_by_user,
    "status": SyncLog.status,
    "results_count": SyncLog.results_count,
    "leads_created": SyncLog.leads_created,
    "leads_seen": SyncLog.leads_seen,
    "leads_skipped": SyncLog.leads_skipped,
    "forms_processed": SyncLog.forms_processed,
    "message": SyncLog.message,
    "id": SyncLog.id,
}

DEFAULT_SYNC_LOG_SORT = "attempt_timestamp"
ALLOWED_SYNC_LOG_LIMITS = frozenset({25, 50, 100})


def _apply_sync_log_date_filters(
    query,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    if start_date is not None:
        query = query.filter(SyncLog.attempt_timestamp >= start_date)
    if end_date is not None:
        query = query.filter(SyncLog.attempt_timestamp <= end_date)
    return query


def list_sync_logs(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = 1,
    limit: int = 25,
    sort_by: str = DEFAULT_SYNC_LOG_SORT,
    sort_order: Literal["asc", "desc"] = "desc",
) -> tuple[list[SyncLogOut], int]:
    """Return a paginated, sortable slice of sync logs and the filtered total_count."""
    safe_page = max(1, int(page))
    safe_limit = int(limit) if int(limit) in ALLOWED_SYNC_LOG_LIMITS else 25
    sort_column = SYNC_LOG_SORT_FIELDS.get(sort_by, SyncLog.attempt_timestamp)
    order_clause = asc(sort_column) if sort_order == "asc" else desc(sort_column)

    filtered = _apply_sync_log_date_filters(
        db.query(SyncLog),
        start_date=start_date,
        end_date=end_date,
    )
    total_count = filtered.with_entities(func.count(SyncLog.id)).scalar() or 0
    offset = (safe_page - 1) * safe_limit
    rows = filtered.order_by(order_clause, desc(SyncLog.id)).offset(offset).limit(safe_limit).all()
    return [serialize_sync_log(row) for row in rows], int(total_count)


MAX_SYNC_LOG_EXPORT_ROWS = 10_000


def list_all_sync_logs_for_export(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    sort_by: str = DEFAULT_SYNC_LOG_SORT,
    sort_order: Literal["asc", "desc"] = "desc",
) -> tuple[list[SyncLogOut], int]:
    """Return all matching sync logs (no pagination) for PDF export."""
    sort_column = SYNC_LOG_SORT_FIELDS.get(sort_by, SyncLog.attempt_timestamp)
    order_clause = asc(sort_column) if sort_order == "asc" else desc(sort_column)

    filtered = _apply_sync_log_date_filters(
        db.query(SyncLog),
        start_date=start_date,
        end_date=end_date,
    )
    total_count = filtered.with_entities(func.count(SyncLog.id)).scalar() or 0
    if total_count > MAX_SYNC_LOG_EXPORT_ROWS:
        raise ValueError(
            f"Export limited to {MAX_SYNC_LOG_EXPORT_ROWS:,} rows; "
            f"{total_count:,} records match. Narrow the date range."
        )

    rows = filtered.order_by(order_clause, desc(SyncLog.id)).all()
    return [serialize_sync_log(row) for row in rows], int(total_count)


def recover_stale_sync_logs(db: Session, *, older_than_minutes: int = 30) -> int:
    """Mark abandoned IN_PROGRESS rows as failed (e.g. after a crashed backend)."""
    from datetime import timedelta

    cutoff = _utcnow_naive() - timedelta(minutes=max(1, older_than_minutes))
    rows = (
        db.query(SyncLog)
        .filter(
            SyncLog.status == STATUS_IN_PROGRESS,
            SyncLog.attempt_timestamp < cutoff,
        )
        .all()
    )
    for row in rows:
        finalize_sync_transaction(
            db,
            row.id,
            fatal_error="Sync interrupted — previous backend process stopped before completion.",
        )
    return len(rows)


def get_sync_log(db: Session, log_id: int) -> SyncLogOut | None:
    row = db.query(SyncLog).filter(SyncLog.id == log_id).first()
    if row is None:
        return None
    return serialize_sync_log(row)
