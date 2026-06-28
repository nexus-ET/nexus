from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from starlette.requests import Request as StarletteRequest

from app.config import settings
from app.db.database import SessionLocal
from app.models.user import User
from app.services.audit_context import build_audit_details, should_skip_middleware_audit
from app.services.audit_logger import scrub_sensitive_data, session_id_from_request, write_audit_log

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = (
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/login",
    "/api/v1/logout",
    "/api/v1/audit-events",
    "/api/v1/admin/audit-logs",
    "/api/v1/webhooks",
    "/api/webhook",
)

_MUTATION_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def _should_skip_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    for prefix in _SKIP_PREFIXES:
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def _target_resource_from_path(path: str) -> str:
    parts = [segment for segment in path.strip("/").split("/") if segment not in {"api", "v1"}]
    if not parts:
        return "unknown"
    if parts[0] in {"admin", "settings", "reports", "security-audit"} and len(parts) > 1:
        return parts[1].replace("-", "_")
    return parts[0].replace("-", "_")


def _resource_id_from_path(path: str) -> str | None:
    parts = [segment for segment in path.strip("/").split("/") if segment not in {"api", "v1"}]
    if parts and parts[-1].isdigit():
        return parts[-1]
    return None


def _action_type_from_request(method: str, path: str) -> str:
    verb = method.upper()
    if verb == "POST":
        return "CREATE"
    if verb in {"PUT", "PATCH"}:
        return "UPDATE"
    if verb == "DELETE":
        return "DELETE"
    return verb


def _user_id_from_request(request: StarletteRequest) -> int | None:
    token = request.cookies.get("nexus_access_token")
    if not token:
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, TypeError, ValueError):
        return None


def _parse_request_body(body: bytes, content_type: str | None) -> dict[str, Any] | None:
    if not body:
        return None
    if content_type and "application/json" in content_type:
        try:
            parsed = json.loads(body.decode("utf-8"))
            if isinstance(parsed, dict):
                return scrub_sensitive_data(parsed)
            return {"payload": scrub_sensitive_data(parsed)}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw_body": "[unparseable]"}
    if content_type and "application/x-www-form-urlencoded" in content_type:
        try:
            from urllib.parse import parse_qs

            parsed = parse_qs(body.decode("utf-8"))
            flat = {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}
            return scrub_sensitive_data(flat)
        except UnicodeDecodeError:
            return {"raw_body": "[unparseable]"}
    return None


def _persist_mutation_audit(
    *,
    method: str,
    path: str,
    status_code: int,
    user_id: int | None,
    request: StarletteRequest,
    body_details: dict[str, Any] | None,
) -> None:
    db = SessionLocal()
    try:
        user: User | None = None
        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
        write_audit_log(
            db,
            user_id=user.id if user else user_id,
            action_type=_action_type_from_request(method, path),
            target_resource=_target_resource_from_path(path),
            resource_id=_resource_id_from_path(path),
            request=Request(request.scope, request.receive),
            status="success" if status_code < 400 else "failed",
            details=build_audit_details(
                method=method,
                api_path=path,
                status_code=status_code,
                action_type=_action_type_from_request(method, path),
                referer=request.headers.get("referer"),
                ui_page_header=request.headers.get("x-nexus-page"),
                request_body=body_details,
            ),
            session_id=session_id_from_request(Request(request.scope, request.receive)),
            sync_mode="MANUAL",
        )
    except Exception:
        logger.exception("Failed to persist mutation audit log for %s %s", method, path)
        db.rollback()
    finally:
        db.close()


async def audit_middleware(request: Request, call_next):
    method = request.method.upper()
    path = request.url.path

    if method not in _MUTATION_METHODS or not path.startswith("/api/") or _should_skip_path(path):
        return await call_next(request)

    if should_skip_middleware_audit(path):
        return await call_next(request)

    body = await request.body()
    content_type = request.headers.get("content-type")
    body_details = _parse_request_body(body, content_type)
    user_id = _user_id_from_request(request)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    wrapped_request = Request(request.scope, receive)
    response = await call_next(wrapped_request)

    try:
        _persist_mutation_audit(
            method=method,
            path=path,
            status_code=response.status_code,
            user_id=user_id,
            request=request,
            body_details=body_details,
        )
    except Exception:
        logger.exception("Audit middleware post-processing failed for %s %s", method, path)

    return response
