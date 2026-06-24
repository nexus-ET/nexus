from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host[:64]
    return None


def write_audit_log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    request: Request | None = None,
    status: str = "success",
    detail: dict[str, Any] | str | None = None,
) -> None:
    detail_text: str | None
    if isinstance(detail, dict):
        detail_text = json.dumps(detail, default=str)[:4000]
    else:
        detail_text = (detail or "")[:4000] or None

    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            ip_address=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512] if request else None,
            status=status,
            detail=detail_text,
        )
    )
    db.commit()


def log_action(action: str, resource: str, resource_id_key: str | None = None) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            db: Session | None = kwargs.get("db")
            request: Request | None = kwargs.get("request")
            current_user: User | None = kwargs.get("current_user")
            if current_user is None:
                current_user = kwargs.get("_")

            resource_id: str | None = None
            if resource_id_key and resource_id_key in kwargs:
                resource_id = str(kwargs[resource_id_key])
            elif "payload" in kwargs and hasattr(kwargs["payload"], "booking_id"):
                resource_id = str(kwargs["payload"].booking_id)
            elif "payload" in kwargs and hasattr(kwargs["payload"], "key"):
                resource_id = str(kwargs["payload"].key)

            try:
                result = func(*args, **kwargs)
                if db is not None:
                    write_audit_log(
                        db,
                        user_id=current_user.id if current_user else None,
                        action=action,
                        resource=resource,
                        resource_id=resource_id,
                        request=request,
                        status="success",
                    )
                return result
            except Exception as exc:
                if db is not None:
                    write_audit_log(
                        db,
                        user_id=current_user.id if current_user else None,
                        action=action,
                        resource=resource,
                        resource_id=resource_id,
                        request=request,
                        status="failed",
                        detail={"error": str(exc)},
                    )
                raise

        return wrapper

    return decorator
