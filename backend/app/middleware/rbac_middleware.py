from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.user import User
from app.services.navigation_rbac import (
    RBAC_EXEMPT_PREFIXES,
    RBAC_PUBLIC_AUTH_PREFIXES,
    check_page_access,
    resolve_page_routes_for_api_path,
)


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
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        user_id = decode_access_token(token)
        if user_id is None:
            return JSONResponse(status_code=401, content={"detail": "Could not validate credentials"})

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return JSONResponse(status_code=401, content={"detail": "User not found"})
            if not user.is_active:
                return JSONResponse(status_code=403, content={"detail": "Inactive user account"})

            if not any(check_page_access(db, user, page_route) for page_route in page_routes):
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Access denied for route '{page_routes[0]}'."},
                )
        finally:
            db.close()

        return await call_next(request)
