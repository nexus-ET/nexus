from datetime import datetime

from pydantic import BaseModel, Field


class NotificationInboxItem(BaseModel):
    id: int
    title: str
    message: str
    channel: str
    status: str
    priority: str
    sent_at: datetime
    booking_id: int | None = None


class NotificationInboxResponse(BaseModel):
    notifications: list[NotificationInboxItem]
    unread_count: int


class PushTokenRegisterRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class PushTokenRegisterResponse(BaseModel):
    status: str
    push_supported: bool = True
