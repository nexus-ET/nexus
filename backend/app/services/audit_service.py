from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.audit_context import build_audit_details
from app.services.audit_logger import write_audit_log


def log_action(action_type: str, target_resource: str, resource_id_key: str | None = None) -> Callable:
    """Decorator for explicit audit entries on router handlers."""

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

            api_path = request.url.path if request else ""
            method = request.method if request else "POST"

            def _write(status: str, extra: dict[str, Any] | None = None) -> None:
                if db is None:
                    return
                write_audit_log(
                    db,
                    user_id=current_user.id if current_user else None,
                    action_type=action_type,
                    target_resource=target_resource,
                    resource_id=resource_id,
                    request=request,
                    status=status,
                    details=build_audit_details(
                        method=method,
                        api_path=api_path,
                        status_code=200 if status == "success" else 500,
                        action_type=action_type,
                        referer=request.headers.get("referer") if request else None,
                        ui_page_header=request.headers.get("x-nexus-page") if request else None,
                        extra=extra,
                    ),
                )

            try:
                result = func(*args, **kwargs)
                _write("success")
                return result
            except Exception as exc:
                _write("failed", {"error": str(exc)})
                raise

        return wrapper

    return decorator
