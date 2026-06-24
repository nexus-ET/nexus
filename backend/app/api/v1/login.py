import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.db.database import get_db
from app.models.user import User as UserModel
from app.schemas.token import Token

router = APIRouter()


@router.post("/login", response_model=Token)
def login_access_token(
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    user = db.query(UserModel).filter(UserModel.email == form_data.username).first()

    if not user:
        print(f"--- LOGIN DEBUG: User with email '{form_data.username}' not found in database ---")

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    access_token = security.create_access_token(user.id)
    secure_cookie = os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}

    response.set_cookie(
        key="nexus_access_token",
        value=access_token,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
