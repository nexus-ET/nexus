from typing import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.token import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login"
)

COUNSELLING_ADMIN_ROLE_NAMES = {"Super Admin", "Web Admin"}


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenPayload(sub=int(user_id))
    except (JWTError, ValueError):
        raise credentials_exception

    user = (
        db.query(User)
        .options(joinedload(User.admin_role_ref))
        .filter(User.id == token_data.sub)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    return current_user


def _resolved_role_name(user: User) -> str:
    if user.admin_role_ref and user.admin_role_ref.name:
        return user.admin_role_ref.name
    return ""


def require_internal_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.is_superuser or current_user.admin_role_id:
        return current_user
    raise HTTPException(status_code=403, detail="Internal admin access required.")


def require_counselling_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if current_user.is_superuser:
        return current_user
    if _resolved_role_name(current_user) in COUNSELLING_ADMIN_ROLE_NAMES:
        return current_user
    raise HTTPException(status_code=403, detail="Counselling admin access required.")


def require_super_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Super Admin access required.")
    return current_user


def require_page_access(page_route: str):
    def _dependency(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        from app.services.navigation_rbac import check_page_access

        if check_page_access(db, current_user, page_route):
            return current_user
        raise HTTPException(
            status_code=403,
            detail=f"Access denied for route '{page_route}'.",
        )

    return _dependency


def get_request_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
