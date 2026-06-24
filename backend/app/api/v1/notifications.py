from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.notifications import (
    NotificationInboxItem,
    NotificationInboxResponse,
    PushTokenRegisterRequest,
    PushTokenRegisterResponse,
)
from app.services.notification_service import (
    get_active_user_notifications,
    list_user_notification_inbox,
    register_push_token,
    resolve_user_notification,
)

router = APIRouter()


@router.get("/active")
def get_active_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return get_active_user_notifications(db, current_user.id)


@router.post("/{notification_id}/resolve")
def resolve_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    resolved = resolve_user_notification(db, current_user.id, notification_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"status": "resolved", "id": notification_id}


@router.get("/inbox", response_model=NotificationInboxResponse)
@router.get("/inbox/", response_model=NotificationInboxResponse)
def get_notification_inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    items = list_user_notification_inbox(db, current_user.id)
    unread = sum(1 for item in items if item["status"] not in {"resolved"})
    return NotificationInboxResponse(
        notifications=[NotificationInboxItem(**item) for item in items],
        unread_count=unread,
    )


@router.post("/push-token", response_model=PushTokenRegisterResponse)
@router.post("/push-token/", response_model=PushTokenRegisterResponse)
def register_device_push_token(
    payload: PushTokenRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    register_push_token(db, current_user, payload.token)
    return PushTokenRegisterResponse(status="registered", push_supported=True)
