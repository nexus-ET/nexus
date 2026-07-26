from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import json

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.user import User
from app.services.exception_log_service import (
    SEVERITY_ERROR,
    record_exception_event_isolated,
)
from app.services.navigation_rbac import (
    RBAC_EXEMPT_PREFIXES,
    RBAC_PUBLIC_AUTH_PREFIXES,
    check_page_access,
    resolve_page_routes_for_api_path,
)


def _record_rbac_denial(
    request: Request,
    *,
    status_code: int,
    detail: str,
    user_label: str = "SYSTEM",
    user_id: int | None = None,
) -> None:
    """Ensure auth/RBAC denials still appear in Exception Report."""
    path = request.url.path
    if path.startswith("/api/v1/reports/exception-logs"):
        return
    record_exception_event_isolated(
        severity=SEVERITY_ERROR,
        source="backend",
        category="rbac_denial" if status_code == 403 else "auth_failure",
        message=f"HTTP {status_code}: {detail}",
        details=[
            f"status={status_code}",
            f"method={request.method}",
            f"path={path}",
            detail,
        ],
        page_path=request.headers.get("x-nexus-page"),
        exception_type=f"HTTP_{status_code}",
        related_resource="api",
        related_id=path[:100],
        triggered_by_user=user_label,
        triggered_by_user_id=user_id,
    )


def _authorize_request(token: str, page_routes: list[str]) -> tuple[JSONResponse | None, str, int | None]:
    user_id = decode_access_token(token)
    if user_id is None:
        return (
            JSONResponse(status_code=401, content={"detail": "Could not validate credentials"}),
            "SYSTEM",
            None,
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return (
                JSONResponse(status_code=401, content={"detail": "User not found"}),
                "SYSTEM",
                int(user_id) if user_id is not None else None,
            )
        if not user.is_active:
            label = (user.email or user.full_name or f"User #{user.id}")[:255]
            return (
                JSONResponse(status_code=403, content={"detail": "Inactive user account"}),
                label,
                int(user.id),
            )

        if not any(check_page_access(db, user, page_route) for page_route in page_routes):
            label = (user.email or user.full_name or f"User #{user.id}")[:255]
            return (
                JSONResponse(
                    status_code=403,
                    content={"detail": f"Access denied for route '{page_routes[0]}'."},
                ),
                label,
                int(user.id),
            )
        return None, (user.email or user.full_name or f"User #{user.id}")[:255], int(user.id)
    finally:
        db.close()


class NavigationRBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if request.method == "OPTIONS":
            return await call_next(request)

        if not path.startswith("/api/v1"):
            return await call_next(request)

        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in RBAC_EXEMPT_PREFIXES):
            return await call_next(request)

        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in RBAC_PUBLIC_AUTH_PREFIXES):
            return await call_next(request)

        page_routes = resolve_page_routes_for_api_path(path)
        if not page_routes:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            detail = "Not authenticated"
            _record_rbac_denial(request, status_code=401, detail=detail)
            return JSONResponse(status_code=401, content={"detail": detail})

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            detail = "Not authenticated"
            _record_rbac_denial(request, status_code=401, detail=detail)
            return JSONResponse(status_code=401, content={"detail": detail})

        denied, user_label, user_id = await asyncio.to_thread(
            _authorize_request, token, page_routes
        )
        if denied is not None:
            detail = f"HTTP {denied.status_code}"
            try:
                body = denied.body
                if body:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and parsed.get("detail"):
                        detail = str(parsed["detail"])
            except Exception:
                pass
            _record_rbac_denial(
                request,
                status_code=int(denied.status_code),
                detail=detail,
                user_label=user_label,
                user_id=user_id,
            )
            return denied

        return await call_next(request)
