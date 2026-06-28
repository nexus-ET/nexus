import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.config import settings
from app.core import security
from app.db.database import get_db
from app.models.user import User as UserModel
from app.schemas.token import Token
from app.services.audit_context import build_auth_audit_details
from app.services.audit_logger import write_audit_log

router = APIRouter()


def _secure_cookie_enabled() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}


@router.post("/login", response_model=Token)
def login_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    user = db.query(UserModel).filter(UserModel.email == form_data.username).first()

    if not user:
        print(f"--- LOGIN DEBUG: User with email '{form_data.username}' not found in database ---")

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        write_audit_log(
            db,
            user_id=user.id if user else None,
            action_type="LOGIN_FAILURE",
            target_resource="auth",
            request=request,
            status="failed",
            details=build_auth_audit_details(
                "LOGIN_FAILURE",
                form_data.username,
                status_code=401,
            ),
            sync_mode="MANUAL",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        write_audit_log(
            db,
            user_id=user.id,
            action_type="LOGIN_FAILURE",
            target_resource="auth",
            request=request,
            status="failed",
            details=build_auth_audit_details(
                "LOGIN_FAILURE",
                form_data.username,
                reason="account_deactivated",
                status_code=403,
            ),
            sync_mode="MANUAL",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    access_token = security.create_access_token(user.id)
    session_id = str(uuid.uuid4())
    secure_cookie = _secure_cookie_enabled()

    response.set_cookie(
        key="nexus_access_token",
        value=access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="nexus_session_id",
        value=session_id,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    write_audit_log(
        db,
        user_id=user.id,
        action_type="LOGIN_SUCCESS",
        target_resource="auth",
        request=request,
        status="success",
        details=build_auth_audit_details("LOGIN_SUCCESS", user.email),
        session_id=session_id,
        sync_mode="MANUAL",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(deps.get_current_user),
):
    write_audit_log(
        db,
        user_id=current_user.id,
        action_type="LOGOUT",
        target_resource="auth",
        request=request,
        status="success",
        details=build_auth_audit_details("LOGOUT", current_user.email),
        sync_mode="MANUAL",
    )

    secure_cookie = _secure_cookie_enabled()
    response.delete_cookie(key="nexus_access_token", path="/", samesite="strict")
    response.delete_cookie(key="nexus_session_id", path="/", samesite="strict")
    if secure_cookie:
        response.delete_cookie(key="nexus_access_token", path="/", secure=True, samesite="strict")
        response.delete_cookie(key="nexus_session_id", path="/", secure=True, samesite="strict")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
