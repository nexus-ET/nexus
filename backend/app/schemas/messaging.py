from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.chat import MessageCreate


class AdminSearchResult(BaseModel):
    id: int
    full_name: str
    email: str
    status: str = "offline"
    last_seen_at: datetime | None = None
    last_active_at: datetime | None = None
    away_duration_seconds: int | None = None


class AdminSearchResponse(BaseModel):
    admins: list[AdminSearchResult]


class ConversationParticipantOut(BaseModel):
    admin_id: int
    full_name: str
    email: str
    last_read_at: datetime | None = None
    status: str = "offline"
    last_seen_at: datetime | None = None
    last_active_at: datetime | None = None
    away_duration_seconds: int | None = None


class ConversationOut(BaseModel):
    id: int
    type: str
    name: str | None = None
    last_message_at: datetime | None = None
    display_name: str
    last_message_snippet: str | None = None
    unread_count: int = 0
    participants: list[ConversationParticipantOut] = []


class ConversationsResponse(BaseModel):
    conversations: list[ConversationOut]


class DirectConversationRequest(BaseModel):
    admin_id: int


class GroupConversationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    admin_ids: list[int] = Field(min_length=1)


class ParticipantChangeRequest(BaseModel):
    admin_id: int


class ReplyToMessageOut(BaseModel):
    id: int
    sender_id: int
    sender_name: str
    content: str
    content_type: str


class MessageReactionOut(BaseModel):
    emoji: str
    count: int
    user_ids: list[int]
    reacted_by_me: bool = False


class InternalMessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_name: str
    content: str
    content_type: str
    media_url: str | None = None
    reply_to_message_id: int | None = None
    reply_to: ReplyToMessageOut | None = None
    reactions: list[MessageReactionOut] = []
    created_at: datetime


class MessagesResponse(BaseModel):
    messages: list[InternalMessageOut]


class SendMessageRequest(MessageCreate):
    reply_to_message_id: int | None = None


class MessageReactionRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)


class MarkReadRequest(BaseModel):
    last_read_at: datetime | None = None


class MessagingTypingRequest(BaseModel):
    conversation_id: int
    is_typing: bool = True


class ChatSearchResultOut(BaseModel):
    message_id: int
    conversation_id: int
    snippet: str
    timestamp: datetime
    conversation_name: str


class ChatSearchResponse(BaseModel):
    results: list[ChatSearchResultOut]


class MessageSearchResult(BaseModel):
    id: int
    conversation_id: int
    conversation_name: str
    sender_name: str
    content: str
    content_type: str
    created_at: datetime


class MessageSearchResponse(BaseModel):
    results: list[MessageSearchResult]
