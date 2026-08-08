from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.conversation_participant import ConversationParticipant
from app.models.internal_message import InternalMessage
from app.models.message_reaction import MessageReaction
from app.models.user import User
from app.services.presence_service import presence_tracker
from app.utils.timezone import utc_now


def _format_user_name(user: User | None) -> str:
    if not user:
        return "Admin"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email


def _ensure_participant(db: Session, *, conversation_id: int, admin_id: int) -> ConversationParticipant:
    participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.admin_id == admin_id,
        )
        .first()
    )
    if not participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation.")
    return participant


def ensure_conversation_access(db: Session, *, conversation_id: int, admin_id: int) -> ConversationParticipant:
    return _ensure_participant(db, conversation_id=conversation_id, admin_id=admin_id)


def search_admins(db: Session, *, query: str, current_user_id: int, limit: int = 20) -> list[dict]:
    term = query.strip()
    base_query = db.query(User).filter(
        User.is_active.is_(True),
        User.id != current_user_id,
        User.admin_role_id.isnot(None),
    )
    if term:
        pattern = f"%{term.lower()}%"
        base_query = base_query.filter(
            or_(
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(User.first_name, "")).like(pattern),
                func.lower(func.coalesce(User.last_name, "")).like(pattern),
            )
        )
    rows = (
        base_query.order_by(User.first_name.asc(), User.last_name.asc(), User.email.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": user.id,
            "full_name": _format_user_name(user),
            "email": user.email,
            **presence_tracker.snapshot(user.id),
        }
        for user in rows
    ]


def _find_direct_conversation(db: Session, user_a: int, user_b: int) -> Conversation | None:
    if user_a == user_b:
        return None

    first_id, second_id = sorted((user_a, user_b))
    rows = (
        db.query(ConversationParticipant.conversation_id, ConversationParticipant.admin_id)
        .join(Conversation, Conversation.id == ConversationParticipant.conversation_id)
        .filter(Conversation.type == "direct", ConversationParticipant.admin_id.in_([user_a, user_b]))
        .all()
    )
    by_conversation: dict[int, set[int]] = {}
    for conversation_id, admin_id in rows:
        by_conversation.setdefault(conversation_id, set()).add(admin_id)

    for conversation_id, participant_ids in by_conversation.items():
        if participant_ids == {first_id, second_id}:
            return db.query(Conversation).filter(Conversation.id == conversation_id).first()
    return None


def get_or_create_direct_conversation(db: Session, *, current_user_id: int, other_admin_id: int) -> Conversation:
    if current_user_id == other_admin_id:
        raise HTTPException(status_code=400, detail="Cannot start a conversation with yourself.")
    other = (
        db.query(User)
        .filter(User.id == other_admin_id, User.is_active.is_(True), User.admin_role_id.isnot(None))
        .first()
    )
    if not other:
        raise HTTPException(status_code=404, detail="Admin not found.")

    existing = _find_direct_conversation(db, current_user_id, other_admin_id)
    if existing:
        return existing

    conversation = Conversation(type="direct", last_message_at=None)
    db.add(conversation)
    db.flush()
    for admin_id in (current_user_id, other_admin_id):
        db.add(ConversationParticipant(conversation_id=conversation.id, admin_id=admin_id))
    db.commit()
    db.refresh(conversation)
    return conversation


def create_group_conversation(
    db: Session,
    *,
    creator_id: int,
    name: str,
    admin_ids: list[int],
) -> Conversation:
    unique_ids = sorted(set(admin_ids + [creator_id]))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=400, detail="A group needs at least two participants.")

    users = (
        db.query(User)
        .filter(User.id.in_(unique_ids), User.is_active.is_(True), User.admin_role_id.isnot(None))
        .all()
    )
    if len(users) != len(unique_ids):
        raise HTTPException(status_code=400, detail="One or more admins are invalid.")

    conversation = Conversation(type="group", name=name.strip(), last_message_at=None)
    db.add(conversation)
    db.flush()
    for admin_id in unique_ids:
        db.add(ConversationParticipant(conversation_id=conversation.id, admin_id=admin_id))
    db.commit()
    db.refresh(conversation)
    return conversation


def _last_message_snippet(db: Session, conversation_id: int) -> str | None:
    row = (
        db.query(InternalMessage)
        .filter(InternalMessage.conversation_id == conversation_id)
        .order_by(InternalMessage.created_at.desc(), InternalMessage.id.desc())
        .first()
    )
    if not row:
        return None
    if row.content_type == "audio":
        return "Voice note"
    return (row.content or "")[:120] or None


def _unread_count(db: Session, *, conversation_id: int, admin_id: int, last_read_at: datetime | None) -> int:
    query = db.query(InternalMessage).filter(
        InternalMessage.conversation_id == conversation_id,
        InternalMessage.sender_id != admin_id,
    )
    if last_read_at is not None:
        query = query.filter(InternalMessage.created_at > last_read_at)
    return query.count()


def serialize_conversation(
    db: Session,
    conversation: Conversation,
    *,
    current_user_id: int,
) -> dict:
    participants = (
        db.query(ConversationParticipant, User)
        .join(User, User.id == ConversationParticipant.admin_id)
        .filter(ConversationParticipant.conversation_id == conversation.id)
        .all()
    )
    participant_payload = [
        {
            "admin_id": user.id,
            "full_name": _format_user_name(user),
            "email": user.email,
            "last_read_at": row.last_read_at,
            **presence_tracker.snapshot(user.id),
        }
        for row, user in participants
    ]
    my_participant = next((row for row, user in participants if user.id == current_user_id), None)
    my_last_read = my_participant.last_read_at if my_participant else None

    if conversation.type == "group":
        display_name = conversation.name or "Group chat"
    else:
        other = next((user for _, user in participants if user.id != current_user_id), None)
        display_name = _format_user_name(other)

    return {
        "id": conversation.id,
        "type": conversation.type,
        "name": conversation.name,
        "last_message_at": conversation.last_message_at,
        "display_name": display_name,
        "last_message_snippet": _last_message_snippet(db, conversation.id),
        "unread_count": _unread_count(
            db,
            conversation_id=conversation.id,
            admin_id=current_user_id,
            last_read_at=my_last_read,
        ),
        "participants": participant_payload,
    }


def list_conversations(db: Session, *, current_user_id: int) -> list[dict]:
    conversation_ids = (
        db.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.admin_id == current_user_id)
    )
    rows = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conversation_ids))
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
        .all()
    )
    return [serialize_conversation(db, row, current_user_id=current_user_id) for row in rows]


def total_unread_message_count(db: Session, *, admin_id: int) -> int:
    participants = (
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.admin_id == admin_id)
        .all()
    )
    total = 0
    for participant in participants:
        total += _unread_count(
            db,
            conversation_id=participant.conversation_id,
            admin_id=admin_id,
            last_read_at=participant.last_read_at,
        )
    return total


def get_conversation(db: Session, *, conversation_id: int, current_user_id: int) -> dict:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=current_user_id)
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return serialize_conversation(db, conversation, current_user_id=current_user_id)


def _reply_preview(db: Session, message: InternalMessage | None) -> dict | None:
    if not message:
        return None
    sender = db.query(User).filter(User.id == message.sender_id).first()
    content = message.content or ""
    if message.content_type == "audio":
        content = "Voice note"
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": _format_user_name(sender),
        "content": content,
        "content_type": message.content_type,
    }


def _reaction_summaries(
    db: Session, message_ids: list[int], current_user_id: int
) -> dict[int, list[dict]]:
    if not message_ids:
        return {}
    rows = (
        db.query(MessageReaction)
        .filter(MessageReaction.message_id.in_(message_ids))
        .order_by(MessageReaction.id.asc())
        .all()
    )
    grouped: dict[int, dict[str, dict]] = {}
    for row in rows:
        per_message = grouped.setdefault(row.message_id, {})
        bucket = per_message.setdefault(
            row.emoji,
            {"emoji": row.emoji, "count": 0, "user_ids": [], "reacted_by_me": False},
        )
        bucket["count"] += 1
        bucket["user_ids"].append(row.user_id)
        if row.user_id == current_user_id:
            bucket["reacted_by_me"] = True
    return {message_id: list(emojis.values()) for message_id, emojis in grouped.items()}


def serialize_message(
    db: Session,
    message: InternalMessage,
    sender: User,
    *,
    current_user_id: int,
    reply_to: InternalMessage | None = None,
    reactions: list[dict] | None = None,
) -> dict:
    preview = _reply_preview(db, reply_to) if reply_to else None
    if preview is None and message.reply_to_message_id:
        parent = (
            db.query(InternalMessage)
            .filter(InternalMessage.id == message.reply_to_message_id)
            .first()
        )
        preview = _reply_preview(db, parent)
    if reactions is None:
        reactions = _reaction_summaries(db, [message.id], current_user_id).get(message.id, [])
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "sender_name": _format_user_name(sender),
        "content": message.content,
        "content_type": message.content_type,
        "media_url": message.media_url,
        "reply_to_message_id": message.reply_to_message_id,
        "reply_to": preview,
        "reactions": reactions,
        "created_at": message.created_at,
    }


def list_messages(
    db: Session,
    *,
    conversation_id: int,
    current_user_id: int,
    limit: int = 100,
) -> list[dict]:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=current_user_id)
    rows = (
        db.query(InternalMessage, User)
        .join(User, User.id == InternalMessage.sender_id)
        .filter(InternalMessage.conversation_id == conversation_id)
        .order_by(InternalMessage.created_at.desc(), InternalMessage.id.desc())
        .limit(limit)
        .all()
    )
    ordered = list(reversed(rows))
    message_ids = [message.id for message, _ in ordered]
    reply_ids = [
        message.reply_to_message_id
        for message, _ in ordered
        if message.reply_to_message_id
    ]
    reply_map: dict[int, InternalMessage] = {}
    if reply_ids:
        for parent in db.query(InternalMessage).filter(InternalMessage.id.in_(reply_ids)).all():
            reply_map[parent.id] = parent
    reaction_map = _reaction_summaries(db, message_ids, current_user_id)
    return [
        serialize_message(
            db,
            message,
            sender,
            current_user_id=current_user_id,
            reply_to=reply_map.get(message.reply_to_message_id) if message.reply_to_message_id else None,
            reactions=reaction_map.get(message.id, []),
        )
        for message, sender in ordered
    ]


def _update_search_vector(db: Session, message_id: int, content: str) -> None:
    db.execute(
        text(
            "UPDATE internal_messages "
            "SET search_vector = to_tsvector('english', :content) "
            "WHERE id = :message_id"
        ),
        {"content": content or "", "message_id": message_id},
    )


def index_message_search(message_id: int, content: str) -> None:
    """Background full-text index update — kept off the send hot path."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        _update_search_vector(db, message_id, content)
        db.commit()
    finally:
        db.close()


def send_message(
    db: Session,
    *,
    conversation_id: int,
    sender_id: int,
    content: str,
    content_type: str = "text",
    media_url: str | None = None,
    reply_to_message_id: int | None = None,
) -> dict:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=sender_id)
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    reply_to: InternalMessage | None = None
    if reply_to_message_id is not None:
        reply_to = (
            db.query(InternalMessage)
            .filter(
                InternalMessage.id == reply_to_message_id,
                InternalMessage.conversation_id == conversation_id,
            )
            .first()
        )
        if not reply_to:
            raise HTTPException(status_code=404, detail="Reply target message not found.")

    now = utc_now()
    message = InternalMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=content.strip() if content_type == "text" else (content or "Voice note"),
        content_type=content_type,
        media_url=media_url,
        reply_to_message_id=reply_to_message_id,
    )
    db.add(message)
    conversation.last_message_at = now
    db.flush()
    sender = db.query(User).filter(User.id == sender_id).first()
    db.commit()
    db.refresh(message)

    return serialize_message(
        db,
        message,
        sender,
        current_user_id=sender_id,
        reply_to=reply_to,
        reactions=[],
    )


def toggle_message_reaction(
    db: Session,
    *,
    conversation_id: int,
    message_id: int,
    user_id: int,
    emoji: str,
) -> dict:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=user_id)
    message = (
        db.query(InternalMessage)
        .filter(
            InternalMessage.id == message_id,
            InternalMessage.conversation_id == conversation_id,
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    normalized_emoji = emoji.strip()
    if not normalized_emoji:
        raise HTTPException(status_code=400, detail="Emoji is required.")

    existing = (
        db.query(MessageReaction)
        .filter(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user_id,
            MessageReaction.emoji == normalized_emoji,
        )
        .first()
    )
    if existing:
        db.delete(existing)
    else:
        db.add(
            MessageReaction(
                message_id=message_id,
                user_id=user_id,
                emoji=normalized_emoji,
            )
        )
    db.commit()

    sender = db.query(User).filter(User.id == message.sender_id).first()
    reply_to = None
    if message.reply_to_message_id:
        reply_to = (
            db.query(InternalMessage)
            .filter(InternalMessage.id == message.reply_to_message_id)
            .first()
        )
    return serialize_message(
        db,
        message,
        sender,
        current_user_id=user_id,
        reply_to=reply_to,
    )


def mark_conversation_read(
    db: Session,
    *,
    conversation_id: int,
    admin_id: int,
    last_read_at: datetime | None = None,
) -> datetime:
    participant = _ensure_participant(db, conversation_id=conversation_id, admin_id=admin_id)
    now = last_read_at or utc_now()
    participant.last_read_at = now
    db.commit()
    return now


def add_participant(
    db: Session,
    *,
    conversation_id: int,
    actor_id: int,
    admin_id: int,
) -> dict:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=actor_id)
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    existing = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.admin_id == admin_id,
        )
        .first()
    )
    if existing:
        return serialize_conversation(db, conversation, current_user_id=actor_id)

    target = (
        db.query(User)
        .filter(User.id == admin_id, User.is_active.is_(True), User.admin_role_id.isnot(None))
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found.")

    if conversation.type == "direct":
        conversation.type = "group"
        if not conversation.name:
            conversation.name = "Team chat"

    db.add(ConversationParticipant(conversation_id=conversation_id, admin_id=admin_id))
    db.commit()
    db.refresh(conversation)
    return serialize_conversation(db, conversation, current_user_id=actor_id)


def remove_participant(
    db: Session,
    *,
    conversation_id: int,
    actor_id: int,
    admin_id: int,
) -> dict:
    _ensure_participant(db, conversation_id=conversation_id, admin_id=actor_id)
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if conversation.type == "direct":
        raise HTTPException(status_code=400, detail="Cannot remove participants from a direct chat.")

    participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.admin_id == admin_id,
        )
        .first()
    )
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found.")

    remaining = (
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.conversation_id == conversation_id)
        .count()
    )
    if remaining <= 2:
        raise HTTPException(status_code=400, detail="A group must keep at least two participants.")

    db.delete(participant)
    db.commit()
    db.refresh(conversation)
    return serialize_conversation(db, conversation, current_user_id=actor_id)


def get_participant_ids(db: Session, conversation_id: int) -> list[int]:
    rows = (
        db.query(ConversationParticipant.admin_id)
        .filter(ConversationParticipant.conversation_id == conversation_id)
        .all()
    )
    return [admin_id for (admin_id,) in rows]


def search_messages(
    db: Session,
    *,
    current_user_id: int,
    query: str,
    limit: int = 30,
) -> list[dict]:
    term = query.strip()
    if not term:
        return []

    participant_conversation_ids = (
        db.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.admin_id == current_user_id)
        .subquery()
    )

    rows = (
        db.query(InternalMessage, User, Conversation)
        .join(User, User.id == InternalMessage.sender_id)
        .join(Conversation, Conversation.id == InternalMessage.conversation_id)
        .filter(
            InternalMessage.conversation_id.in_(participant_conversation_ids),
            InternalMessage.search_vector.op("@@")(func.plainto_tsquery("english", term)),
        )
        .order_by(InternalMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    results: list[dict] = []
    for message, sender, conversation in rows:
        if conversation.type == "group":
            conversation_name = conversation.name or "Group chat"
        else:
            conversation_name = serialize_conversation(db, conversation, current_user_id=current_user_id)[
                "display_name"
            ]
        results.append(
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "conversation_name": conversation_name,
                "sender_name": _format_user_name(sender),
                "content": message.content,
                "content_type": message.content_type,
                "created_at": message.created_at,
            }
        )
    return results
