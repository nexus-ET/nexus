from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.exception_log_service import (
    SEVERITY_ERROR,
    SEVERITY_EXCEPTION,
    SEVERITY_WARNING,
    record_exception_event_isolated,
)

logger = logging.getLogger(__name__)

# Only skip the exception-log sink itself (and docs) to avoid recursive reporting.
_SKIP_PATH_PREFIXES = (
    "/api/v1/reports/exception-logs",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _should_skip_path(path: str) -> bool:
    normalized = (path or "").rstrip("/")
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(f"{prefix.rstrip('/')}/")
        for prefix in _SKIP_PATH_PREFIXES
    )


def _is_expected_missing_lookup(path: str, status_code: int) -> bool:
    """Catalog GET 404s (stale wizard program_id) must not flood Exception Report."""
    if status_code != 404:
        return False
    normalized = (path or "").rstrip("/")
    prefixes = (
        "/api/v1/academia/degrees/",
        "/api/v1/academia/courses/",
        "/api/v1/academia/education-majors/",
        "/api/v1/academia/programs/",
    )
    return any(normalized.startswith(prefix) for prefix in prefixes)


def _severity_for_status(status_code: int) -> str:
    if status_code >= 500:
        return SEVERITY_EXCEPTION
    if status_code >= 400:
        return SEVERITY_ERROR
    return SEVERITY_WARNING


def _user_label_from_request(request: Request) -> tuple[str, int | None]:
    user = getattr(request.state, "user", None)
    if user is None:
        return "SYSTEM", None
    user_id = getattr(user, "id", None)
    email = getattr(user, "email", None)
    full_name = getattr(user, "full_name", None)
    if email:
        return str(email)[:255], int(user_id) if user_id is not None else None
    if full_name:
        return str(full_name)[:255], int(user_id) if user_id is not None else None
    if user_id is not None:
        return f"User #{user_id}", int(user_id)
    return "SYSTEM", None


def _record_backend_exception(
    request: Request,
    *,
    severity: str,
    category: str,
    message: str,
    exception_type: str,
    details: list[str] | None = None,
    status_code: int | None = None,
) -> None:
    if _should_skip_path(request.url.path):
        return
    if status_code == 429:
        return
    if status_code is not None and _is_expected_missing_lookup(request.url.path, status_code):
        return

    triggered_by, user_id = _user_label_from_request(request)
    detail_items = list(details or [])
    if status_code is not None:
        detail_items.insert(0, f"status={status_code}")
    detail_items.append(f"method={request.method}")
    detail_items.append(f"path={request.url.path}")

    record_exception_event_isolated(
        severity=severity,
        source="backend",
        category=category,
        message=message[:4000],
        details=detail_items[:20],
        page_path=request.headers.get("x-nexus-page"),
        exception_type=exception_type[:120],
        related_resource="api",
        related_id=request.url.path[:100],
        triggered_by_user=triggered_by,
        triggered_by_user_id=user_id,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log every HTTPException / StarletteHTTPException into Exception Report."""
    status_code = 500
    detail: Any = "Internal server error"
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        status_code = int(exc.status_code)
        detail = exc.detail

    detail_text = detail if isinstance(detail, str) else str(detail)
    _record_backend_exception(
        request,
        severity=_severity_for_status(status_code),
        category="http_exception",
        message=f"HTTP {status_code}: {detail_text}",
        exception_type=type(exc).__name__,
        details=[detail_text[:500]],
        status_code=status_code,
    )

    headers = getattr(exc, "headers", None) if isinstance(exc, HTTPException) else None
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log request validation failures (422) into Exception Report."""
    errors: Any = []
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()

    detail_text = str(errors)[:500] if errors else "Request validation failed"
    _record_backend_exception(
        request,
        severity=SEVERITY_ERROR,
        category="validation_error",
        message=f"HTTP 422: {detail_text}",
        exception_type=type(exc).__name__,
        details=[detail_text],
        status_code=422,
    )
    return JSONResponse(status_code=422, content={"detail": errors})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected backend exceptions across all API routes."""
    if isinstance(exc, RequestValidationError):
        return await validation_exception_handler(request, exc)
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)

    logger.exception("Unhandled backend exception on %s %s", request.method, request.url.path)
    _record_backend_exception(
        request,
        severity=SEVERITY_EXCEPTION,
        category="unhandled_exception",
        message=str(exc) or type(exc).__name__,
        exception_type=type(exc).__name__,
        details=[traceback.format_exc()[-1500:]],
        status_code=500,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: Any) -> None:
    """Attach Nexus Exception Report handlers to the FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
