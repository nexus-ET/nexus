from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.config import settings


def validate_chat_message_length(value: str) -> str:
    limit = settings.CHAT_MAX_CHARS
    if len(value) > limit:
        raise ValueError(f"Message exceeds the {limit} character limit")
    return value


class MessageCreate(BaseModel):
    content: str = Field(min_length=0)

    @field_validator("content")
    @classmethod
    def validate_content_length(cls, value: str) -> str:
        return validate_chat_message_length(value)


class ChatConfigResponse(BaseModel):
    chat_max_chars: int
