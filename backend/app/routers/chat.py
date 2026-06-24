from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.command_center import (
    AssignLeadRequest,
    ChatMessageOut,
    ChatMessagesResponse,
    ChatReadRequest,
    ChatSendRequest,
    TypingRequest,
)
from app.schemas.chat import ChatConfigResponse
from app.schemas.messaging import (
    ChatSearchResponse,
    ChatSearchResultOut,
    AdminSearchResponse,
    AdminSearchResult,
    ConversationOut,
    ConversationsResponse,
    DirectConversationRequest,
    GroupConversationRequest,
    InternalMessageOut,
    MarkReadRequest,
    MessageReactionRequest,
    MessageSearchResponse,
    MessageSearchResult,
    MessagesResponse,
    MessagingTypingRequest,
    ParticipantChangeRequest,
    SendMessageRequest,
)
from app.services import chat_service, command_center_service, search_service
from app.services.websocket_service import broadcast_unread_count_updates
from app.services.audit_service import log_action
from app.services.websocket_service import broadcast_nexus_event, broadcast_to_users

router = APIRouter()

VOICE_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads" / "voice"
VOICE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _notify_participants(
    db: Session,
    conversation_id: int,
    event_type: str,
    data: dict,
    *,
    exclude_user_id: int | None = None,
) -> None:
    participant_ids = [
        user_id
        for user_id in chat_service.get_participant_ids(db, conversation_id)
        if exclude_user_id is None or user_id != exclude_user_id
    ]
    await broadcast_to_users(
        participant_ids,
        {"type": event_type, "data": data},
    )


async def _notify_participant_ids(
    participant_ids: list[int],
    event_type: str,
    data: dict,
    *,
    exclude_user_id: int | None = None,
) -> None:
    targets = [
        user_id
        for user_id in participant_ids
        if exclude_user_id is None or user_id != exclude_user_id
    ]
    await broadcast_to_users(targets, {"type": event_type, "data": data})


def _schedule_message_delivery(
    background_tasks: BackgroundTasks,
    participant_ids: list[int],
    message: dict,
) -> None:
    """Notify all participants (including sender) and index search off the HTTP path."""
    background_tasks.add_task(
        _notify_participant_ids,
        participant_ids,
        "messaging.message",
        message,
    )
    background_tasks.add_task(
        chat_service.index_message_search,
        message["id"],
        message.get("content") or "",
    )
    background_tasks.add_task(
        broadcast_unread_count_updates,
        participant_ids,
    )


# --- Command Center team chat (legacy) ---


@router.get("/chat/config", response_model=ChatConfigResponse)
@router.get("/chat/config/", response_model=ChatConfigResponse)
def get_chat_config(
    _: User = Depends(deps.get_current_active_user),
):
    return ChatConfigResponse(chat_max_chars=settings.CHAT_MAX_CHARS)


@router.get("/chat/messages", response_model=ChatMessagesResponse)
@router.get("/chat/messages/", response_model=ChatMessagesResponse)
def list_chat_messages(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    messages = command_center_service.list_team_messages(db)
    return ChatMessagesResponse(messages=[ChatMessageOut(**item) for item in messages])


@router.post("/chat/messages", response_model=ChatMessageOut)
@router.post("/chat/messages/", response_model=ChatMessageOut)
@log_action("send_team_chat", "team_chat")
async def send_chat_message(
    request: Request,
    payload: ChatSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    message = command_center_service.create_team_message(
        db,
        sender_user_id=current_user.id,
        text=payload.text,
        lead_id=payload.lead_id,
    )
    await broadcast_nexus_event("chat.message", message, exclude_user_id=current_user.id)
    return ChatMessageOut(**message)


@router.post("/chat/messages/read")
@router.post("/chat/messages/read/")
async def mark_chat_read(
    payload: ChatReadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    count = command_center_service.mark_messages_read(
        db,
        reader_user_id=current_user.id,
        up_to_message_id=payload.up_to_message_id,
    )
    await broadcast_nexus_event(
        "chat.read",
        {"reader_user_id": current_user.id, "up_to_message_id": payload.up_to_message_id},
    )
    return {"marked_read": count}


@router.post("/chat/typing")
@router.post("/chat/typing/")
async def send_typing_indicator(
    payload: TypingRequest,
    current_user: User = Depends(deps.require_counselling_admin),
):
    await broadcast_nexus_event(
        "chat.typing",
        {"user_id": current_user.id, "is_typing": payload.is_typing},
        exclude_user_id=current_user.id,
    )
    return {"status": "ok"}


@router.post("/chat/assign-lead", response_model=ChatMessageOut)
@router.post("/chat/assign-lead/", response_model=ChatMessageOut)
@log_action("assign_lead_from_chat", "lead")
async def assign_lead_quick_action(
    request: Request,
    payload: AssignLeadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    lead = command_center_service.assign_lead_to_admin(
        db,
        lead_id=payload.lead_id,
        admin_id=current_user.id,
    )
    message = command_center_service.create_team_message(
        db,
        sender_user_id=current_user.id,
        text=f"Assigned {lead.full_name} to me.",
        lead_id=lead.id,
        message_type="system",
    )
    await broadcast_nexus_event(
        "lead.assigned",
        {"lead_id": lead.id, "admin_id": current_user.id, "full_name": lead.full_name},
    )
    await broadcast_nexus_event("chat.message", message, exclude_user_id=current_user.id)
    return ChatMessageOut(**message)


@router.post("/chat/voice", response_model=ChatMessageOut)
@router.post("/chat/voice/", response_model=ChatMessageOut)
@log_action("upload_voice_note", "team_chat")
async def upload_voice_note(
    request: Request,
    lead_id: int | None = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    suffix = Path(file.filename or "voice.webm").suffix or ".webm"
    filename = f"{uuid.uuid4().hex}{suffix}"
    destination = VOICE_UPLOAD_DIR / filename
    content = await file.read()
    destination.write_bytes(content)

    media_url = f"/api/v1/chat/voice/{filename}"
    message = command_center_service.create_team_message(
        db,
        sender_user_id=current_user.id,
        text="Voice note",
        lead_id=lead_id,
        message_type="voice",
        media_url=media_url,
        file_name=file.filename or filename,
    )
    await broadcast_nexus_event("chat.message", message, exclude_user_id=current_user.id)
    return ChatMessageOut(**message)


@router.get("/chat/voice/{filename}")
def get_voice_note(
    filename: str,
    _: User = Depends(deps.get_current_active_user),
):
    safe_name = Path(filename).name
    path = VOICE_UPLOAD_DIR / safe_name
    if not path.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Voice note not found.")
    return FileResponse(path)


# --- Internal Messaging Hub ---


@router.get("/chat/admins/search", response_model=AdminSearchResponse)
@router.get("/chat/admins/search/", response_model=AdminSearchResponse)
def search_admins_for_chat(
    q: str = Query(default="", min_length=0, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    admins = chat_service.search_admins(db, query=q, current_user_id=current_user.id)
    return AdminSearchResponse(admins=[AdminSearchResult(**item) for item in admins])


@router.get("/chat/conversations", response_model=ConversationsResponse)
@router.get("/chat/conversations/", response_model=ConversationsResponse)
def list_my_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    conversations = chat_service.list_conversations(db, current_user_id=current_user.id)
    return ConversationsResponse(
        conversations=[ConversationOut(**item) for item in conversations]
    )


@router.post("/chat/conversations/direct", response_model=ConversationOut)
@router.post("/chat/conversations/direct/", response_model=ConversationOut)
@log_action("get_or_create_direct_conversation", "conversation")
def get_or_create_direct_conversation(
    request: Request,
    payload: DirectConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    conversation = chat_service.get_or_create_direct_conversation(
        db,
        current_user_id=current_user.id,
        other_admin_id=payload.admin_id,
    )
    return ConversationOut(
        **chat_service.serialize_conversation(db, conversation, current_user_id=current_user.id)
    )


@router.post("/chat/conversations/group", response_model=ConversationOut)
@router.post("/chat/conversations/group/", response_model=ConversationOut)
@log_action("create_group_conversation", "conversation")
def create_group_conversation(
    request: Request,
    payload: GroupConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    conversation = chat_service.create_group_conversation(
        db,
        creator_id=current_user.id,
        name=payload.name,
        admin_ids=payload.admin_ids,
    )
    return ConversationOut(
        **chat_service.serialize_conversation(db, conversation, current_user_id=current_user.id)
    )


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationOut)
@router.get("/chat/conversations/{conversation_id}/", response_model=ConversationOut)
def read_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    return ConversationOut(
        **chat_service.get_conversation(
            db, conversation_id=conversation_id, current_user_id=current_user.id
        )
    )


@router.get("/chat/conversations/{conversation_id}/messages", response_model=MessagesResponse)
@router.get("/chat/conversations/{conversation_id}/messages/", response_model=MessagesResponse)
def read_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    messages = chat_service.list_messages(
        db, conversation_id=conversation_id, current_user_id=current_user.id
    )
    return MessagesResponse(messages=[InternalMessageOut(**item) for item in messages])


@router.post("/chat/conversations/{conversation_id}/messages", response_model=InternalMessageOut)
@router.post("/chat/conversations/{conversation_id}/messages/", response_model=InternalMessageOut)
async def send_internal_message(
    conversation_id: int,
    payload: SendMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    message = chat_service.send_message(
        db,
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=payload.content,
        content_type="text",
        reply_to_message_id=payload.reply_to_message_id,
    )
    participant_ids = chat_service.get_participant_ids(db, conversation_id)
    _schedule_message_delivery(background_tasks, participant_ids, message)
    return InternalMessageOut(**message)


@router.post(
    "/chat/conversations/{conversation_id}/messages/{message_id}/reactions",
    response_model=InternalMessageOut,
)
@router.post(
    "/chat/conversations/{conversation_id}/messages/{message_id}/reactions/",
    response_model=InternalMessageOut,
)
async def toggle_message_reaction(
    conversation_id: int,
    message_id: int,
    payload: MessageReactionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    message = chat_service.toggle_message_reaction(
        db,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=current_user.id,
        emoji=payload.emoji,
    )
    participant_ids = chat_service.get_participant_ids(db, conversation_id)
    background_tasks.add_task(
        _notify_participant_ids,
        participant_ids,
        "messaging.reaction",
        message,
    )
    return InternalMessageOut(**message)


@router.post("/chat/conversations/{conversation_id}/read")
@router.post("/chat/conversations/{conversation_id}/read/")
async def mark_conversation_read(
    conversation_id: int,
    payload: MarkReadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    last_read_at = chat_service.mark_conversation_read(
        db,
        conversation_id=conversation_id,
        admin_id=current_user.id,
        last_read_at=payload.last_read_at,
    )
    participant_ids = chat_service.get_participant_ids(db, conversation_id)
    background_tasks.add_task(
        _notify_participant_ids,
        participant_ids,
        "messaging.read",
        {
            "conversation_id": conversation_id,
            "user_id": current_user.id,
            "last_read_at": last_read_at.isoformat(),
        },
    )
    background_tasks.add_task(
        broadcast_unread_count_updates,
        participant_ids,
    )
    return {"last_read_at": last_read_at}


@router.post("/chat/conversations/{conversation_id}/participants", response_model=ConversationOut)
@router.post("/chat/conversations/{conversation_id}/participants/", response_model=ConversationOut)
@log_action("add_conversation_participant", "conversation")
def add_conversation_participant(
    request: Request,
    conversation_id: int,
    payload: ParticipantChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    data = chat_service.add_participant(
        db,
        conversation_id=conversation_id,
        actor_id=current_user.id,
        admin_id=payload.admin_id,
    )
    return ConversationOut(**data)


@router.delete("/chat/conversations/{conversation_id}/participants/{admin_id}", response_model=ConversationOut)
@router.delete("/chat/conversations/{conversation_id}/participants/{admin_id}/", response_model=ConversationOut)
@log_action("remove_conversation_participant", "conversation")
def remove_conversation_participant(
    request: Request,
    conversation_id: int,
    admin_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    data = chat_service.remove_participant(
        db,
        conversation_id=conversation_id,
        actor_id=current_user.id,
        admin_id=admin_id,
    )
    return ConversationOut(**data)


@router.post("/chat/conversations/{conversation_id}/voice", response_model=InternalMessageOut)
@router.post("/chat/conversations/{conversation_id}/voice/", response_model=InternalMessageOut)
async def upload_internal_voice_note(
    conversation_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    suffix = Path(file.filename or "voice.webm").suffix or ".webm"
    filename = f"{uuid.uuid4().hex}{suffix}"
    destination = VOICE_UPLOAD_DIR / filename
    content = await file.read()
    destination.write_bytes(content)

    media_url = f"/api/v1/chat/voice/{filename}"
    message = chat_service.send_message(
        db,
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content="Voice note",
        content_type="audio",
        media_url=media_url,
    )
    participant_ids = chat_service.get_participant_ids(db, conversation_id)
    _schedule_message_delivery(background_tasks, participant_ids, message)
    return InternalMessageOut(**message)


@router.post("/chat/messaging/typing")
@router.post("/chat/messaging/typing/")
async def send_messaging_typing(
    payload: MessagingTypingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    chat_service.ensure_conversation_access(
        db, conversation_id=payload.conversation_id, admin_id=current_user.id
    )
    participant_ids = chat_service.get_participant_ids(db, payload.conversation_id)
    background_tasks.add_task(
        _notify_participant_ids,
        participant_ids,
        "messaging.typing",
        {
            "conversation_id": payload.conversation_id,
            "user_id": current_user.id,
            "is_typing": payload.is_typing,
        },
        exclude_user_id=current_user.id,
    )
    return {"status": "ok"}


@router.post("/chat/messaging/presence")
@router.post("/chat/messaging/presence/")
async def send_messaging_presence(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    chat_service.ensure_conversation_access(
        db, conversation_id=conversation_id, admin_id=current_user.id
    )
    await _notify_participants(
        db,
        conversation_id,
        "user_online",
        {"conversation_id": conversation_id, "user_id": current_user.id},
        exclude_user_id=current_user.id,
    )
    return {"status": "ok"}


@router.post("/chat/messaging/heartbeat")
@router.post("/chat/messaging/heartbeat/")
async def messaging_heartbeat(
    current_user: User = Depends(deps.require_internal_admin),
):
    from app.services.presence_service import presence_tracker
    from app.services.websocket_service import broadcast_nexus_event

    presence_tracker.heartbeat(current_user.id)
    await broadcast_nexus_event(
        "presence.updated",
        {"user_id": current_user.id, **presence_tracker.snapshot(current_user.id)},
        exclude_user_id=current_user.id,
    )
    return presence_tracker.snapshot(current_user.id)


@router.get("/chat/search", response_model=ChatSearchResponse)
@router.get("/chat/search/", response_model=ChatSearchResponse)
def intelligent_chat_search(
    query: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    results = search_service.search_chat_history(
        db,
        current_user_id=current_user.id,
        query=query,
    )
    return ChatSearchResponse(results=[ChatSearchResultOut(**item) for item in results])


@router.get("/chat/messages/search", response_model=MessageSearchResponse)
@router.get("/chat/messages/search/", response_model=MessageSearchResponse)
def search_message_history(
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_internal_admin),
):
    results = chat_service.search_messages(db, current_user_id=current_user.id, query=q)
    return MessageSearchResponse(results=[MessageSearchResult(**item) for item in results])
