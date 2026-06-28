from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.settings_service import get_setting
from app.utils.timezone import business_now

logger = logging.getLogger(__name__)

_schema_lock = threading.Lock()
_schema_ready = False

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "confirm_password",
        "old_password",
        "access_token",
        "refresh_token",
        "client_secret",
        "api_key",
        "secret_key",
        "card_number",
        "cvv",
        "auth_token",
        "jwt_token",
        "hashed_password",
    }
)

DEFAULT_RETENTION_DAYS = 90
SETTING_RETENTION_KEY = "AUDIT_LOG_RETENTION_DAYS"


def ensure_audit_logs_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        from app.db.database import migrate_audit_logs_schema

        migrate_audit_logs_schema()
        _schema_ready = True


def scrub_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive keys in dict/list payloads."""
    if isinstance(data, dict):
        scrubbed: dict[str, Any] = {}
        for key, value in data.items():
            if str(key).lower() in SENSITIVE_KEYS:
                scrubbed[key] = "[MASKED]"
            else:
                scrubbed[key] = scrub_sensitive_data(value)
        return scrubbed
    if isinstance(data, list):
        return [scrub_sensitive_data(item) for item in data]
    return data


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host[:64]
    return None


def session_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    cookie_value = request.cookies.get("nexus_session_id")
    if cookie_value:
        return cookie_value[:128]
    header_value = request.headers.get("x-session-id")
    if header_value:
        return header_value.strip()[:128]
    return None


def write_audit_log(
    db: Session,
    *,
    user_id: int | None,
    action_type: str,
    target_resource: str,
    resource_id: str | None = None,
    request: Request | None = None,
    status: str = "success",
    details: dict[str, Any] | str | None = None,
    session_id: str | None = None,
    sync_mode: str | None = "MANUAL",
    commit: bool = True,
) -> AuditLog:
    ensure_audit_logs_schema()
    details_payload: dict[str, Any] | None
    if isinstance(details, dict):
        details_payload = scrub_sensitive_data(details)
    elif isinstance(details, str) and details.strip():
        try:
            parsed = json.loads(details)
            details_payload = scrub_sensitive_data(parsed) if isinstance(parsed, dict) else {"message": details[:2000]}
        except json.JSONDecodeError:
            details_payload = {"message": details[:2000]}
    else:
        details_payload = None

    resolved_session = session_id or session_id_from_request(request)

    entry = AuditLog(
        user_id=user_id,
        action_type=action_type[:100],
        target_resource=target_resource[:100],
        resource_id=str(resource_id)[:100] if resource_id is not None else None,
        details=details_payload,
        ip_address=client_ip(request),
        timestamp=business_now(db),
        user_agent=(request.headers.get("user-agent") or "")[:512] if request else None,
        status=status[:20],
        session_id=resolved_session,
        sync_mode=(sync_mode or "MANUAL")[:20],
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def get_audit_log_retention_days(db: Session | None = None) -> int:
    raw = get_setting(SETTING_RETENTION_KEY, str(DEFAULT_RETENTION_DAYS), db=db)
    try:
        days = int(str(raw or DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    return max(1, min(days, 3650))


def cleanup_old_audit_logs() -> int:
    """Hard-delete audit rows older than the configured retention window."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    deleted_count = 0
    try:
        retention_days = get_audit_log_retention_days(db)
        cutoff = business_now(db) - timedelta(days=retention_days)
        deleted_count = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted_count:
            write_audit_log(
                db,
                user_id=None,
                action_type="AUDIT_LOG_CLEANUP",
                target_resource="audit_logs",
                status="success",
                details={
                    "deleted_count": deleted_count,
                    "retention_days": retention_days,
                    "cutoff": cutoff.isoformat(),
                },
                sync_mode="AUTOMATED",
            )
        logger.info(
            "Audit log cleanup finished. deleted=%s retention_days=%s",
            deleted_count,
            retention_days,
        )
    except Exception:
        logger.exception("Audit log cleanup job failed.")
        db.rollback()
    finally:
        db.close()
    return deleted_count
