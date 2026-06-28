from __future__ import annotations

import math
from datetime import datetime, time
from typing import Literal

from sqlalchemy import String, asc, cast, desc, or_
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogOut

ALLOWED_AUDIT_LOG_LIMITS = frozenset({25, 50, 100})
MAX_AUDIT_LOG_EXPORT_ROWS = 5000
AUDIT_LOG_SORT_FIELDS = frozenset(
    {
        "timestamp",
        "action_type",
        "target_resource",
        "user_id",
        "status",
        "sync_mode",
        "ip_address",
    }
)


def _serialize_log(row: AuditLog, user: User | None = None) -> AuditLogOut:
    details = row.details
    if details is None and row.detail:
        details = {"legacy_detail": row.detail}

    user_name = None
    user_email = None
    if user is not None:
        user_email = user.email
        parts = [part for part in [user.first_name, user.last_name] if part]
        user_name = " ".join(parts).strip() or user.email

    return AuditLogOut(
        id=row.id,
        user_id=row.user_id,
        user_email=user_email,
        user_name=user_name,
        action_type=row.action_type,
        target_resource=row.target_resource,
        resource_id=row.resource_id,
        details=details,
        ip_address=row.ip_address,
        timestamp=row.timestamp,
        session_id=row.session_id,
        sync_mode=row.sync_mode,
        user_agent=row.user_agent,
        status=row.status,
    )


def list_audit_logs(
    db: Session,
    *,
    page: int,
    limit: int,
    start_date: datetime | None,
    end_date: datetime | None,
    user_id: int | None,
    keyword: str | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
) -> tuple[list[AuditLogOut], int]:
    query = db.query(AuditLog, User).outerjoin(User, AuditLog.user_id == User.id)

    if start_date is not None:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date is not None:
        query = query.filter(AuditLog.timestamp <= end_date)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if keyword:
        term = f"%{keyword.strip()}%"
        details_text = cast(AuditLog.details, String)
        query = query.filter(
            or_(
                AuditLog.action_type.ilike(term),
                AuditLog.target_resource.ilike(term),
                AuditLog.resource_id.ilike(term),
                AuditLog.ip_address.ilike(term),
                AuditLog.session_id.ilike(term),
                AuditLog.status.ilike(term),
                details_text.ilike(term),
                User.email.ilike(term),
                User.first_name.ilike(term),
                User.last_name.ilike(term),
            )
        )

    total_count = query.count()

    sort_column = {
        "timestamp": AuditLog.timestamp,
        "action_type": AuditLog.action_type,
        "target_resource": AuditLog.target_resource,
        "user_id": AuditLog.user_id,
        "status": AuditLog.status,
        "sync_mode": AuditLog.sync_mode,
        "ip_address": AuditLog.ip_address,
    }.get(sort_by, AuditLog.timestamp)
    ordering = asc(sort_column) if sort_order == "asc" else desc(sort_column)

    offset = (page - 1) * limit
    rows = query.order_by(ordering, desc(AuditLog.id)).offset(offset).limit(limit).all()
    logs = [_serialize_log(audit_row, user_row) for audit_row, user_row in rows]
    return logs, total_count


def list_audit_logs_for_export(
    db: Session,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
    user_id: int | None,
    keyword: str | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
    max_rows: int = MAX_AUDIT_LOG_EXPORT_ROWS,
) -> list[AuditLogOut]:
    logs, _ = list_audit_logs(
        db,
        page=1,
        limit=max_rows,
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return logs


def parse_audit_date_param(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    if end_of_day and parsed.time() == time.min:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def audit_logs_total_pages(total_count: int, limit: int) -> int:
    return max(1, math.ceil(total_count / limit)) if total_count else 1
