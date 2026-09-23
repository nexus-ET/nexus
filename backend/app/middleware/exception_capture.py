from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

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
# Chrome/Edge DevTools CDP probes hit the API host; logging them floods Exception Report + email.
_SKIP_EXACT_PATHS = frozenset(
    {
        "/json",
        "/json/version",
        "/json/list",
        "/favicon.ico",
        "/robots.txt",
    }
)
# Best-effort background polls — DB/tunnel timeouts must not spam Exception Report.
_SKIP_BEST_EFFORT_PATHS = frozenset(
    {
        "/api/v1/chat/messaging/heartbeat",
    }
)


def _is_benign_audit_body_parse_error(path: str, status_code: int, detail: Any) -> bool:
    """Keepalive/beforeunload audit flushes often abort mid-body → false 400s."""
    if status_code != 400:
        return False
    normalized = (path or "").rstrip("/")
    if normalized not in {"/api/v1/audit-events"}:
        return False
    text = detail if isinstance(detail, str) else str(detail)
    return "error parsing the body" in text.lower()


def _is_db_pool_pressure(detail: Any) -> bool:
    from app.db.database import is_db_pool_pressure_error

    return is_db_pool_pressure_error(detail if isinstance(detail, str) else str(detail))


def _is_db_tunnel_transient(detail: Any) -> bool:
    from app.db.database import is_db_tunnel_transient_error

    if isinstance(detail, BaseException):
        return is_db_tunnel_transient_error(detail)
    return is_db_tunnel_transient_error(str(detail))


def _should_skip_path(path: str) -> bool:
    normalized = (path or "").rstrip("/") or "/"
    if normalized in _SKIP_EXACT_PATHS or normalized.startswith("/json/"):
        return True
    if normalized in _SKIP_BEST_EFFORT_PATHS:
        return True
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
    # Missing/expired Bearer is expected client/auth-gate behavior, not ops ERROR.
    if status_code == 401:
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
    if _is_benign_audit_body_parse_error(request.url.path, status_code, detail_text):
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=getattr(exc, "headers", None) if isinstance(exc, HTTPException) else None,
        )

    # Tunnel pool exhaustion wrapped as HTTP 500 by route handlers — treat as 503.
    if _is_db_pool_pressure(detail_text) or _is_db_tunnel_transient(detail_text):
        logger.warning(
            "DB tunnel/pool transient on %s %s (returning 503, not recording)",
            request.method,
            request.url.path,
        )
        from app.db.database import (
            DB_TEMPORARILY_BUSY_DETAIL,
            db_temporarily_busy_headers,
        )

        return JSONResponse(
            status_code=503,
            content={"detail": DB_TEMPORARILY_BUSY_DETAIL},
            headers=db_temporarily_busy_headers(),
        )

    # Transient unavailability (pool pressure / tunnel) — do not email Exception Report.
    if status_code == 503:
        headers = dict(getattr(exc, "headers", None) or {}) if isinstance(exc, HTTPException) else {}
        if "Retry-After" not in headers:
            from app.db.database import db_temporarily_busy_headers

            headers.update(db_temporarily_busy_headers())
        return JSONResponse(
            status_code=503,
            content={"detail": detail},
            headers=headers or None,
        )

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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse | Response:
    """Catch-all for unexpected backend exceptions across all API routes."""
    if isinstance(exc, RequestValidationError):
        return await validation_exception_handler(request, exc)
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    # Browser abort / timeout mid-request — not an actionable server fault.
    if isinstance(exc, ClientDisconnect):
        logger.debug(
            "ClientDisconnect on %s %s (not recording)",
            request.method,
            request.url.path,
        )
        return Response(status_code=499)

    # SSH-tunnel pool wait / connect pressure / mid-query disconnect —
    # return 503, do not email Exception Report.
    if _is_db_pool_pressure(exc) or _is_db_tunnel_transient(exc):
        logger.warning(
            "DB tunnel/pool transient on %s %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        try:
            from app.db.database import (
                DB_TEMPORARILY_BUSY_DETAIL,
                db_temporarily_busy_headers,
                dispose_db_pool,
                is_ssh_tunnel_database_url,
                should_dispose_pool_for_error,
            )
            from app.config import settings

            if is_ssh_tunnel_database_url(settings.DATABASE_URL) and should_dispose_pool_for_error(
                exc
            ):
                dispose_db_pool(reason=f"tunnel transient {type(exc).__name__}")
            busy_detail = DB_TEMPORARILY_BUSY_DETAIL
            busy_headers = db_temporarily_busy_headers()
        except Exception:
            logger.debug("db pool dispose after tunnel transient skipped", exc_info=True)
            from app.db.database import (
                DB_TEMPORARILY_BUSY_DETAIL,
                db_temporarily_busy_headers,
            )

            busy_detail = DB_TEMPORARILY_BUSY_DETAIL
            busy_headers = db_temporarily_busy_headers()

        return JSONResponse(
            status_code=503,
            content={"detail": busy_detail},
            headers=busy_headers,
        )

    # SSH-tunnel Postgres: drop poisoned pooled sockets so the next request reconnects.
    msg = str(exc).lower()
    if any(
        n in msg
        for n in (
            "connection timeout",
            "timeout expired",
            "server closed the connection",
            "connection refused",
            "could not connect",
        )
    ):
        try:
            from app.db.database import dispose_db_pool, is_ssh_tunnel_database_url
            from app.config import settings

            if is_ssh_tunnel_database_url(settings.DATABASE_URL):
                dispose_db_pool(reason=f"unhandled {type(exc).__name__}")
        except Exception:
            logger.debug("db pool dispose after tunnel error skipped", exc_info=True)

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


class QuietDbTunnelMiddleware:
    """Return 503 for SSH-tunnel drops before Starlette re-raises them.

    ``Exception`` handlers are installed on ServerErrorMiddleware, which always
    re-raises. Uvicorn then prints ``Exception in ASGI application`` plus the
    full SQLAlchemy stack. Catching here keeps the retryable 503 and skips that dump.

    GET/HEAD: buffer the body and retry the ASGI call once after the tunnel
    recovers so a brief flap does not 503 the SPA bootstrap.

    POST bulk-delete is hard-delete idempotent (missing ids are skipped) — retry
    once through the same recover path so Postgres warm-up does not wipe the UX.
    """

    _IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})
    _RETRYABLE_POST_PATHS = frozenset(
        {
            "/api/v1/scanx/documents/bulk-delete",
        }
    )

    def __init__(self, app: Any) -> None:
        self.app = app

    @classmethod
    def _is_retryable(cls, method: str, path: str) -> bool:
        if method in cls._IDEMPOTENT_METHODS:
            return True
        if method == "POST" and path.rstrip("/") in cls._RETRYABLE_POST_PATHS:
            return True
        return False

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "")
        if self._is_retryable(method, path):
            await self._call_with_get_retry(scope, receive, send, method, path)
            return
        await self._call_once(scope, receive, send, method, path)

    async def _call_once(self, scope: Any, receive: Any, send: Any, method: str, path: str) -> None:
        response_started = False

        async def send_wrapper(message: Any) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if not _is_db_tunnel_transient(exc):
                raise
            await self._finish_tunnel_failure(
                scope, receive, send, method, path, exc, response_started, retried=False
            )

    async def _call_with_get_retry(
        self, scope: Any, receive: Any, send: Any, method: str, path: str
    ) -> None:
        replay, reset = await _prepare_replayable_receive(receive)
        if reset is None:
            return

        last_exc: BaseException | None = None
        for attempt in range(1, 3):
            if attempt > 1:
                reset()
            response_started = False

            async def send_wrapper(message: Any) -> None:
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                await send(message)

            try:
                await self.app(scope, replay, send_wrapper)
                return
            except Exception as exc:
                if not _is_db_tunnel_transient(exc) or response_started:
                    raise
                last_exc = exc
                logger.warning(
                    "DB tunnel dropped during %s %s (%s) attempt %s/2; recovering then retrying",
                    method,
                    path,
                    type(exc).__name__,
                    attempt,
                )
                if attempt < 2:
                    recovered = await asyncio.to_thread(
                        _recover_tunnel_for_request, exc, method, path
                    )
                    if recovered:
                        continue
                await self._finish_tunnel_failure(
                    scope, receive, send, method, path, exc, response_started, retried=True
                )
                return
        if last_exc is not None:
            raise last_exc

    async def _finish_tunnel_failure(
        self,
        scope: Any,
        receive: Any,
        send: Any,
        method: str,
        path: str,
        exc: BaseException,
        response_started: bool,
        *,
        retried: bool,
    ) -> None:
        if not retried:
            logger.warning(
                "DB tunnel dropped during %s %s (%s); returning 503",
                method,
                path,
                type(exc).__name__,
            )
        try:
            from app.config import settings
            from app.db.database import (
                dispose_db_pool,
                is_ssh_tunnel_database_url,
                should_dispose_pool_for_error,
            )

            if is_ssh_tunnel_database_url(settings.DATABASE_URL) and should_dispose_pool_for_error(
                exc
            ):
                dispose_db_pool(reason=f"tunnel middleware {type(exc).__name__}")
        except Exception:
            logger.debug("db pool dispose after tunnel middleware skipped", exc_info=True)
        if response_started:
            return
        from app.db.database import (
            DB_TEMPORARILY_BUSY_DETAIL,
            db_temporarily_busy_headers,
        )

        response = JSONResponse(
            status_code=503,
            content={"detail": DB_TEMPORARILY_BUSY_DETAIL},
            headers=db_temporarily_busy_headers(),
        )
        await response(scope, receive, send)


async def _prepare_replayable_receive(receive: Any):
    """Buffer the HTTP request body so a GET can be replayed after reconnect."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        mtype = message.get("type")
        if mtype == "http.disconnect":
            return receive, None
        if mtype == "http.request":
            chunks.append(message.get("body", b"") or b"")
            if not message.get("more_body"):
                break
    body = b"".join(chunks)
    state = {"sent": False}

    async def replay() -> dict:
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    def reset() -> None:
        state["sent"] = False

    return replay, reset


def _recover_tunnel_for_request(exc: BaseException, method: str, path: str) -> bool:
    from app.config import settings
    from app.db.database import (
        dispose_db_pool,
        is_ssh_tunnel_database_url,
        recover_ssh_tunnel,
        should_dispose_pool_for_error,
    )

    if is_ssh_tunnel_database_url(settings.DATABASE_URL) and should_dispose_pool_for_error(exc):
        dispose_db_pool(reason=f"request retry {method} {path} {type(exc).__name__}")
    return recover_ssh_tunnel(reason=f"{method} {path} {type(exc).__name__}")


def register_exception_handlers(app: Any) -> None:
    """Attach Nexus Exception Report handlers to the FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
