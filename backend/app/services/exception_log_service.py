from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.models.exception_log import ExceptionLog
from app.schemas.exception_log import ExceptionLogOut
from app.services.settings_service import get_setting
from app.utils.timezone import business_now

logger = logging.getLogger(__name__)

SEVERITY_EXCEPTION = "EXCEPTION"
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_OMISSION = "OMISSION"

STATUS_OPEN = "OPEN"
STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_RESOLVED = "RESOLVED"

ALLOWED_SEVERITIES = {
    SEVERITY_EXCEPTION,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_OMISSION,
}
ALLOWED_STATUSES = {STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_RESOLVED}

ALLOWED_EXCEPTION_LOG_LIMITS = {25, 50, 100}
MAX_EXCEPTION_LOG_EXPORT_ROWS = 10_000

SETTING_RETENTION_KEY = "EXCEPTION_LOG_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 90

# Email alert for Exception Report events (same ALERT_EMAIL as uptime monitoring).
EXCEPTION_ALERT_SEVERITIES = {SEVERITY_EXCEPTION, SEVERITY_ERROR, SEVERITY_WARNING}
EXCEPTION_ALERT_DEDUPE_SECONDS = 15 * 60
_exception_alert_lock = threading.Lock()
_recent_exception_alert_keys: dict[str, float] = {}

EXCEPTION_LOG_SORT_FIELDS = {
    "attempt_timestamp": ExceptionLog.attempt_timestamp,
    "severity": ExceptionLog.severity,
    "source": ExceptionLog.source,
    "category": ExceptionLog.category,
    "triggered_by_user": ExceptionLog.triggered_by_user,
    "status": ExceptionLog.status,
    "message": ExceptionLog.message,
    "id": ExceptionLog.id,
}


def _utcnow_naive() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def normalize_severity(raw: str | None) -> str:
    value = (raw or SEVERITY_ERROR).strip().upper()
    if value in ALLOWED_SEVERITIES:
        return value
    if value in {"ERR", "FAIL", "FAILED"}:
        return SEVERITY_ERROR
    if value in {"WARN", "WARNING"}:
        return SEVERITY_WARNING
    if value in {"OMIT", "MISSING", "OMISSION"}:
        return SEVERITY_OMISSION
    if value in {"EXC", "EXCEPTION", "TRACEBACK"}:
        return SEVERITY_EXCEPTION
    return SEVERITY_ERROR


def normalize_status(raw: str | None) -> str:
    value = (raw or STATUS_OPEN).strip().upper()
    if value == STATUS_ACKNOWLEDGED:
        return STATUS_IN_PROGRESS
    return value if value in ALLOWED_STATUSES else STATUS_OPEN


def serialize_exception_log(row: ExceptionLog) -> ExceptionLogOut:
    details: list[str] = []
    if row.details_json:
        try:
            parsed = json.loads(row.details_json)
            if isinstance(parsed, list):
                details = [str(item) for item in parsed]
            elif parsed:
                details = [str(parsed)]
        except json.JSONDecodeError:
            details = [row.details_json]

    return ExceptionLogOut(
        id=row.id,
        severity=normalize_severity(row.severity),
        source=row.source or "backend",
        category=row.category or "general",
        status=normalize_status(row.status),
        triggered_by_user=row.triggered_by_user or "SYSTEM",
        triggered_by_user_id=row.triggered_by_user_id,
        message=row.message or "",
        details=details,
        page_path=row.page_path,
        exception_type=row.exception_type,
        related_resource=row.related_resource,
        related_id=row.related_id,
        attempt_timestamp=row.attempt_timestamp,
        resolved_at=row.resolved_at,
        resolution_comment=row.resolution_comment,
    )


def _should_send_exception_alert(fingerprint: str) -> bool:
    now = time.monotonic()
    with _exception_alert_lock:
        cutoff = now - EXCEPTION_ALERT_DEDUPE_SECONDS
        stale = [key for key, seen_at in _recent_exception_alert_keys.items() if seen_at < cutoff]
        for key in stale:
            _recent_exception_alert_keys.pop(key, None)
        last = _recent_exception_alert_keys.get(fingerprint)
        if last is not None and now - last < EXCEPTION_ALERT_DEDUPE_SECONDS:
            return False
        _recent_exception_alert_keys[fingerprint] = now
        return True


def _exception_row_snapshot(row: ExceptionLog, **extra: Any) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        id=row.id,
        severity=row.severity,
        source=row.source,
        category=row.category,
        status=row.status,
        triggered_by_user=row.triggered_by_user,
        triggered_by_user_id=row.triggered_by_user_id,
        message=row.message,
        details_json=row.details_json,
        page_path=row.page_path,
        exception_type=row.exception_type,
        related_resource=row.related_resource,
        related_id=row.related_id,
        attempt_timestamp=row.attempt_timestamp,
        resolved_at=getattr(row, "resolved_at", None),
        resolution_comment=getattr(row, "resolution_comment", None),
        **extra,
    )


def _alert_recipients() -> list[str]:
    from app.services.settings_service import parse_alert_emails

    return parse_alert_emails(get_setting("ALERT_EMAIL", default="") or "")


def schedule_exception_alert_email(row: ExceptionLog) -> None:
    """Send the exception alert on a daemon thread so request handlers stay fast."""
    snapshot = _exception_row_snapshot(row)
    thread = threading.Thread(
        target=_send_exception_alert_email,
        args=(snapshot,),
        name=f"exception-alert-{row.id}",
        daemon=True,
    )
    thread.start()


def schedule_exception_resolved_email(
    row: ExceptionLog,
    *,
    resolved_by: str,
) -> None:
    """Email ALERT_EMAIL when an exception is auto-resolved."""
    snapshot = _exception_row_snapshot(row, resolved_by=resolved_by)
    thread = threading.Thread(
        target=_send_exception_resolved_email,
        args=(snapshot,),
        name=f"exception-resolved-{row.id}",
        daemon=True,
    )
    thread.start()


def _send_exception_resolved_email(row: Any) -> None:
    """Best-effort SMTP confirmation that an exception was auto-resolved."""
    try:
        exception_id = getattr(row, "id", None)
        resolved_by = str(getattr(row, "resolved_by", "") or RESOLVER_SYSTEM).strip().lower()
        fingerprint = f"resolved|{exception_id}|{resolved_by}"
        if not _should_send_exception_alert(fingerprint):
            logger.info(
                "Skipping duplicate resolution email for exception_log_id=%s.",
                exception_id,
            )
            return

        recipients = _alert_recipients()
        if not recipients:
            logger.warning(
                "Exception #%s auto-resolved but ALERT_EMAIL is empty; no confirmation sent.",
                exception_id,
            )
            return

        from app.services.email_service import send_email

        resolver_label = {
            RESOLVER_CURSOR: "Cursor agent",
            RESOLVER_SERVER_RECOVERY: "Server recovery",
            RESOLVER_PAGE_REFRESH: "Page refresh",
            RESOLVER_SUCCESSFUL_SYNC: "Successful Meta Lead Sync",
            RESOLVER_SYSTEM: "System",
        }.get(resolved_by, resolved_by or "System")

        severity = normalize_severity(getattr(row, "severity", None))
        resolution_comment = (getattr(row, "resolution_comment", None) or "").strip() or "—"
        subject = (
            f"[Nexus] Exception Report #{exception_id} resolved "
            f"({resolver_label})"
        )
        body = (
            "Nexus auto-resolved an Exception Report event.\n\n"
            f"ID: {exception_id}\n"
            f"Resolved by: {resolver_label}\n"
            f"Resolved at (UTC): {getattr(row, 'resolved_at', None)}\n"
            f"Severity: {severity}\n"
            f"Source: {getattr(row, 'source', None) or '—'}\n"
            f"Category: {getattr(row, 'category', None) or '—'}\n"
            f"Occurred (UTC): {getattr(row, 'attempt_timestamp', None)}\n\n"
            f"Original message:\n{getattr(row, 'message', None) or '—'}\n\n"
            f"Resolution comment:\n{resolution_comment}\n\n"
            "Open Reports → Exception Report in Nexus to review the entry.\n"
            "Recipients are configured under Application Settings → Alert emails (ALERT_EMAIL)."
        )
        sent = send_email(recipients, subject, body)
        if sent:
            logger.info(
                "Exception resolution confirmation emailed for exception_log_id=%s to %s.",
                exception_id,
                ", ".join(recipients),
            )
        else:
            logger.warning(
                "Exception resolution confirmation could not be sent for exception_log_id=%s.",
                exception_id,
            )
    except Exception:
        logger.exception(
            "Failed while preparing/sending exception resolution email for exception_log_id=%s.",
            getattr(row, "id", None),
        )


def _send_exception_alert_email(row: Any) -> None:
    """Best-effort SMTP alert to ALERT_EMAIL recipients. Never raises to callers."""
    try:
        severity = normalize_severity(getattr(row, "severity", None))
        if severity not in EXCEPTION_ALERT_SEVERITIES:
            return

        fingerprint = "|".join(
            [
                severity,
                str(getattr(row, "source", "") or "").lower(),
                str(getattr(row, "category", "") or "").lower(),
                str(getattr(row, "exception_type", "") or ""),
                str(getattr(row, "message", "") or "")[:180],
                str(getattr(row, "related_id", "") or ""),
            ]
        )
        if not _should_send_exception_alert(fingerprint):
            logger.info(
                "Skipping duplicate exception alert for exception_log_id=%s within dedupe window.",
                getattr(row, "id", None),
            )
            return

        from app.services.email_service import send_email

        recipients = _alert_recipients()
        if not recipients:
            logger.warning(
                "Exception #%s recorded but ALERT_EMAIL is empty; no notification sent.",
                getattr(row, "id", None),
            )
            return

        details: list[str] = []
        details_json = getattr(row, "details_json", None)
        if details_json:
            try:
                parsed = json.loads(details_json)
                if isinstance(parsed, list):
                    details = [str(item) for item in parsed[:8]]
                elif parsed:
                    details = [str(parsed)]
            except json.JSONDecodeError:
                details = [str(details_json)[:500]]

        detail_block = "\n".join(f"- {item}" for item in details) if details else "- (none)"
        exception_id = getattr(row, "id", None)
        subject = (
            f"[Nexus] Exception Report #{exception_id}: "
            f"{severity} / {getattr(row, 'source', None) or 'backend'}"
        )
        related_resource = getattr(row, "related_resource", None) or "—"
        related_id = getattr(row, "related_id", None)
        body = (
            "Nexus recorded a new Exception Report event.\n\n"
            f"ID: {exception_id}\n"
            f"Severity: {severity}\n"
            f"Source: {getattr(row, 'source', None) or '—'}\n"
            f"Category: {getattr(row, 'category', None) or '—'}\n"
            f"Type: {getattr(row, 'exception_type', None) or '—'}\n"
            f"Triggered by: {getattr(row, 'triggered_by_user', None) or 'SYSTEM'}\n"
            f"Page: {getattr(row, 'page_path', None) or '—'}\n"
            f"Related: {related_resource}"
            f"{f' / {related_id}' if related_id else ''}\n"
            f"Occurred (UTC): {getattr(row, 'attempt_timestamp', None)}\n\n"
            f"Message:\n{getattr(row, 'message', None) or '—'}\n\n"
            f"Details:\n{detail_block}\n\n"
            "Open Reports → Exception Report in Nexus for the full entry and resolution workflow.\n"
            "Recipients are configured under Application Settings → Alert emails (ALERT_EMAIL)."
        )
        sent = send_email(recipients, subject, body)
        if sent:
            logger.info(
                "Exception alert emailed for exception_log_id=%s to %s.",
                exception_id,
                ", ".join(recipients),
            )
        else:
            logger.warning(
                "Exception alert could not be sent for exception_log_id=%s.",
                exception_id,
            )
    except Exception:
        logger.exception(
            "Failed while preparing/sending exception alert for exception_log_id=%s.",
            getattr(row, "id", None),
        )


def record_exception_event(
    db: Session,
    *,
    severity: str,
    source: str,
    message: str,
    category: str = "general",
    status: str = STATUS_OPEN,
    triggered_by_user: str = "SYSTEM",
    triggered_by_user_id: int | None = None,
    details: list[str] | None = None,
    page_path: str | None = None,
    exception_type: str | None = None,
    related_resource: str | None = None,
    related_id: str | None = None,
    commit: bool = True,
    send_alert: bool = True,
) -> ExceptionLog:
    """Persist an operational exception/error/omission for the Exception Report."""
    detail_items = [str(item) for item in (details or []) if str(item).strip()]
    row = ExceptionLog(
        severity=normalize_severity(severity),
        source=(source or "backend")[:50],
        category=(category or "general")[:80],
        status=normalize_status(status),
        triggered_by_user=(triggered_by_user or "SYSTEM")[:255],
        triggered_by_user_id=triggered_by_user_id,
        message=(message or "Unhandled exception")[:4000],
        details_json=json.dumps(detail_items),
        page_path=(page_path or None) and page_path[:255],
        exception_type=(exception_type or None) and exception_type[:120],
        related_resource=(related_resource or None) and related_resource[:100],
        related_id=(related_id or None) and str(related_id)[:100],
        attempt_timestamp=_utcnow_naive(),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()

    logger.warning(
        "Exception report event recorded [%s/%s] %s",
        row.severity,
        row.source,
        row.message[:200],
    )
    if send_alert and commit and row.id is not None:
        schedule_exception_alert_email(row)
    return row


def record_exception_event_isolated(**kwargs: Any) -> ExceptionLog | None:
    """Write an exception row on its own DB session (safe from request/worker threads)."""
    from app.db.database import SessionLocal, safe_close_session

    db = SessionLocal()
    try:
        return record_exception_event(db, commit=True, **kwargs)
    except Exception:
        logger.exception("Failed to record exception report event.")
        return None
    finally:
        safe_close_session(db)


def update_exception_log_status(
    db: Session,
    exception_log_id: int,
    *,
    status: str,
    resolution_comment: str | None = None,
    resolved_by: str | None = None,
    allow_auto_comment: bool = False,
) -> ExceptionLog | None:
    """Update operational workflow status, resolution note, and resolved timestamp."""
    row = db.query(ExceptionLog).filter(ExceptionLog.id == exception_log_id).first()
    if row is None:
        return None

    normalized = normalize_status(status)
    comment = (resolution_comment or "").strip() or None
    resolver = (resolved_by or "").strip().lower() or None
    was_open = normalize_status(row.status) != STATUS_RESOLVED

    if normalized == STATUS_RESOLVED:
        if not comment and allow_auto_comment and resolver:
            comment = build_auto_resolution_comment(resolver)
        if not comment and not (row.resolution_comment or "").strip():
            raise ValueError(
                "A resolution comment is required when marking an exception as Resolved."
            )
        if comment:
            row.resolution_comment = comment[:4000]
        if row.resolved_at is None or row.status != STATUS_RESOLVED:
            row.resolved_at = _utcnow_naive()
    else:
        row.resolved_at = None
        # Keep prior resolution notes when reopening so admins retain history;
        # allow an explicit new note to overwrite (e.g. In Progress investigation notes).
        if comment:
            row.resolution_comment = comment[:4000]

    row.status = normalized
    db.commit()
    db.refresh(row)

    if (
        normalized == STATUS_RESOLVED
        and was_open
        and allow_auto_comment
        and resolver
        and resolver != "admin"
    ):
        schedule_exception_resolved_email(row, resolved_by=resolver)

    return row


RESOLVER_CURSOR = "cursor_agent"
RESOLVER_SERVER_RECOVERY = "server_recovery"
RESOLVER_PAGE_REFRESH = "page_refresh"
RESOLVER_SUCCESSFUL_SYNC = "successful_sync"
RESOLVER_SYSTEM = "system"

AUTO_RESOLUTION_COMMENTS: dict[str, str] = {
    RESOLVER_CURSOR: (
        "Resolved by Cursor during an automated fix session. "
        "The underlying defect was corrected in code or configuration."
    ),
    RESOLVER_SERVER_RECOVERY: (
        "Resolved automatically after server recovery cleared the underlying condition "
        "(for example a stranded Meta lead-sync lock or abandoned sync)."
    ),
    RESOLVER_PAGE_REFRESH: (
        "Resolved automatically after a successful page load/refresh; "
        "the transient client or UI error did not recur."
    ),
    RESOLVER_SUCCESSFUL_SYNC: (
        "Resolved automatically after Meta Lead Sync completed successfully "
        "and the previous failure condition no longer applies."
    ),
    RESOLVER_SYSTEM: "Resolved automatically by the system.",
}

# Transient client/UI categories that can clear on a healthy page refresh.
TRANSIENT_AUTO_RESOLVE_CATEGORIES = {
    "window_onerror",
    "unhandled_rejection",
    "network_error",
    "request_timeout",
}
TRANSIENT_AUTO_RESOLVE_SOURCES = {"ui", "api_client"}

# Message fragments for Meta sync lock / conflict exceptions.
LEAD_SYNC_LOCK_MESSAGE_FRAGMENTS = (
    "already in progress",
    "stranded sync lock",
    "lead sync is already",
)

# Message / category fragments for Meta Graph / lead sync failures.
LEAD_SYNC_FAILURE_MESSAGE_FRAGMENTS = (
    "rate limit",
    "application request limit",
    "#4",
    "meta graph",
    "lead sync failed",
    "page_access_token",
    "could not list accessible pages",
)


def build_auto_resolution_comment(
    resolved_by: str,
    *,
    detail: str | None = None,
) -> str:
    """Build a standard resolution note for automated / agent resolutions."""
    key = (resolved_by or RESOLVER_SYSTEM).strip().lower()
    base = AUTO_RESOLUTION_COMMENTS.get(key, AUTO_RESOLUTION_COMMENTS[RESOLVER_SYSTEM])
    extra = (detail or "").strip()
    if extra:
        return f"{base} {extra}"[:4000]
    return base


def _message_matches_fragments(message: str | None, fragments: tuple[str, ...]) -> bool:
    text = (message or "").lower()
    return any(fragment in text for fragment in fragments)


def resolve_open_exceptions(
    db: Session,
    *,
    resolved_by: str,
    detail: str | None = None,
    exception_ids: list[int] | None = None,
    sources: set[str] | None = None,
    categories: set[str] | None = None,
    message_fragments: tuple[str, ...] | None = None,
    related_resource: str | None = None,
    only_without_comment: bool = False,
    commit: bool = True,
) -> int:
    """
    Mark matching OPEN/IN_PROGRESS exception rows as RESOLVED with an auto comment.

    Returns the number of rows updated.
    """
    comment = build_auto_resolution_comment(resolved_by, detail=detail)
    query = db.query(ExceptionLog).filter(
        ExceptionLog.status.in_([STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_ACKNOWLEDGED])
    )
    if exception_ids:
        query = query.filter(ExceptionLog.id.in_(exception_ids))
    if sources:
        query = query.filter(ExceptionLog.source.in_(sorted(sources)))
    if categories:
        query = query.filter(ExceptionLog.category.in_(sorted(categories)))
    if related_resource:
        query = query.filter(ExceptionLog.related_resource == related_resource)

    rows = query.order_by(ExceptionLog.id.asc()).limit(500).all()
    updated_rows: list[ExceptionLog] = []
    now = _utcnow_naive()
    for row in rows:
        if message_fragments and not _message_matches_fragments(row.message, message_fragments):
            continue
        if only_without_comment and (row.resolution_comment or "").strip():
            continue
        row.status = STATUS_RESOLVED
        row.resolved_at = now
        if not (row.resolution_comment or "").strip():
            row.resolution_comment = comment
        elif detail and detail not in (row.resolution_comment or ""):
            # Keep existing note; do not overwrite Cursor/admin commentary.
            pass
        updated_rows.append(row)

    updated = len(updated_rows)
    if updated and commit:
        db.commit()
        for row in updated_rows:
            db.refresh(row)
            schedule_exception_resolved_email(row, resolved_by=resolved_by)
    elif updated:
        db.flush()

    if updated:
        logger.info(
            "Auto-resolved %s exception log(s) via %s.",
            updated,
            resolved_by,
        )
    return updated


def auto_resolve_lead_sync_lock_exceptions(
    db: Session,
    *,
    detail: str | None = None,
) -> int:
    """Resolve OPEN 'sync already in progress' exceptions after lock recovery."""
    return resolve_open_exceptions(
        db,
        resolved_by=RESOLVER_SERVER_RECOVERY,
        detail=detail
        or "Stranded Meta lead-sync lock or abandoned IN_PROGRESS sync was recovered.",
        message_fragments=LEAD_SYNC_LOCK_MESSAGE_FRAGMENTS,
    )


def auto_resolve_lead_sync_failure_exceptions(
    db: Session,
    *,
    detail: str | None = None,
) -> int:
    """Resolve OPEN Meta lead-sync / Graph failures after a successful sync."""
    comment = build_auto_resolution_comment(RESOLVER_SUCCESSFUL_SYNC, detail=detail)
    rows = (
        db.query(ExceptionLog)
        .filter(ExceptionLog.status.in_([STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_ACKNOWLEDGED]))
        .order_by(ExceptionLog.id.asc())
        .limit(500)
        .all()
    )
    updated_rows: list[ExceptionLog] = []
    now = _utcnow_naive()
    for row in rows:
        source = (row.source or "").strip().lower()
        category = (row.category or "").strip().lower()
        is_sync_failure = source == "meta_lead_sync" and category == "lead_sync_failure"
        is_graph_failure = _message_matches_fragments(
            row.message, LEAD_SYNC_FAILURE_MESSAGE_FRAGMENTS
        )
        if not (is_sync_failure or is_graph_failure):
            continue
        row.status = STATUS_RESOLVED
        row.resolved_at = now
        if not (row.resolution_comment or "").strip():
            row.resolution_comment = comment
        updated_rows.append(row)
    updated = len(updated_rows)
    if updated:
        db.commit()
        for row in updated_rows:
            db.refresh(row)
            schedule_exception_resolved_email(row, resolved_by=RESOLVER_SUCCESSFUL_SYNC)
        logger.info("Auto-resolved %s Meta lead-sync failure exception(s).", updated)
    return updated


def auto_resolve_transient_client_exceptions(
    db: Session,
    *,
    detail: str | None = None,
) -> int:
    """Resolve transient browser/UI exceptions after a healthy authenticated page load."""
    return resolve_open_exceptions(
        db,
        resolved_by=RESOLVER_PAGE_REFRESH,
        detail=detail,
        sources=TRANSIENT_AUTO_RESOLVE_SOURCES,
        categories=TRANSIENT_AUTO_RESOLVE_CATEGORIES,
    )


def auto_resolve_by_cursor(
    db: Session,
    *,
    exception_ids: list[int] | None = None,
    message_fragments: tuple[str, ...] | None = None,
    sources: set[str] | None = None,
    categories: set[str] | None = None,
    detail: str | None = None,
) -> int:
    """Resolve matching exceptions after a Cursor agent fix, with an auto comment."""
    return resolve_open_exceptions(
        db,
        resolved_by=RESOLVER_CURSOR,
        detail=detail,
        exception_ids=exception_ids,
        message_fragments=message_fragments,
        sources=sources,
        categories=categories,
    )


def _apply_filters(
    query,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
):
    if start_date is not None:
        query = query.filter(ExceptionLog.attempt_timestamp >= start_date)
    if end_date is not None:
        query = query.filter(ExceptionLog.attempt_timestamp <= end_date)
    return query


def list_exception_logs(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = 1,
    limit: int = 25,
    sort_by: str = "attempt_timestamp",
    sort_order: str = "desc",
) -> tuple[list[ExceptionLogOut], int]:
    safe_limit = limit if limit in ALLOWED_EXCEPTION_LOG_LIMITS else 25
    sort_column = EXCEPTION_LOG_SORT_FIELDS.get(sort_by, ExceptionLog.attempt_timestamp)
    order_clause = asc(sort_column) if sort_order == "asc" else desc(sort_column)

    filtered = _apply_filters(
        db.query(ExceptionLog),
        start_date=start_date,
        end_date=end_date,
    )
    total_count = filtered.with_entities(func.count(ExceptionLog.id)).scalar() or 0
    offset = max(0, (max(1, page) - 1) * safe_limit)
    rows = (
        filtered.order_by(order_clause, desc(ExceptionLog.id))
        .offset(offset)
        .limit(safe_limit)
        .all()
    )
    return [serialize_exception_log(row) for row in rows], int(total_count)


def list_all_exception_logs_for_export(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    sort_by: str = "attempt_timestamp",
    sort_order: str = "desc",
) -> tuple[list[ExceptionLogOut], int]:
    sort_column = EXCEPTION_LOG_SORT_FIELDS.get(sort_by, ExceptionLog.attempt_timestamp)
    order_clause = asc(sort_column) if sort_order == "asc" else desc(sort_column)

    filtered = _apply_filters(
        db.query(ExceptionLog),
        start_date=start_date,
        end_date=end_date,
    )
    total_count = filtered.with_entities(func.count(ExceptionLog.id)).scalar() or 0
    if total_count > MAX_EXCEPTION_LOG_EXPORT_ROWS:
        raise ValueError(
            f"Too many rows to export ({total_count:,}). "
            f"Narrow the date range (max {MAX_EXCEPTION_LOG_EXPORT_ROWS:,})."
        )
    rows = filtered.order_by(order_clause, desc(ExceptionLog.id)).all()
    return [serialize_exception_log(row) for row in rows], int(total_count)


def get_exception_log_retention_days(db: Session | None = None) -> int:
    raw = get_setting(SETTING_RETENTION_KEY, str(DEFAULT_RETENTION_DAYS), db=db)
    try:
        days = int(str(raw or DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    return max(1, min(days, 3650))


def cleanup_old_exception_logs(db: Session | None = None) -> int:
    """Hard-delete exception rows older than the configured retention window."""
    owns_session = db is None
    if owns_session:
        from app.db.database import SessionLocal

        db = SessionLocal()

    deleted_count = 0
    try:
        retention_days = get_exception_log_retention_days(db)
        cutoff = business_now(db) - timedelta(days=retention_days)
        deleted_count = (
            db.query(ExceptionLog)
            .filter(ExceptionLog.attempt_timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(
            "Exception log cleanup finished. deleted=%s retention_days=%s cutoff=%s",
            deleted_count,
            retention_days,
            cutoff.isoformat(),
        )
    except Exception:
        logger.exception("Exception log cleanup failed.")
        db.rollback()
        if owns_session:
            raise
    finally:
        if owns_session:
            db.close()
    return deleted_count
