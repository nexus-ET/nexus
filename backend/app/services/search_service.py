from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.services.chat_service import serialize_conversation

_SNIPPET_RADIUS = 72
_SIMILARITY_THRESHOLD = 0.22
_WORD_SIMILARITY_THRESHOLD = 0.35


def _build_snippet(content: str, query: str) -> str:
    text_value = (content or "").strip()
    if not text_value:
        return ""

    lowered = text_value.lower()
    query_lower = query.lower().strip()
    match_index = lowered.find(query_lower) if query_lower else -1

    if match_index < 0:
        for token in re.findall(r"\w+", query):
            token_index = lowered.find(token.lower())
            if token_index >= 0:
                match_index = token_index
                query_lower = token.lower()
                break

    if match_index < 0:
        trimmed = text_value[: _SNIPPET_RADIUS * 2]
        return f"{trimmed}..." if len(text_value) > len(trimmed) else trimmed

    start = max(0, match_index - _SNIPPET_RADIUS)
    end = min(len(text_value), match_index + max(len(query_lower), 1) + _SNIPPET_RADIUS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text_value) else ""
    return f"{prefix}{text_value[start:end]}{suffix}"


def search_chat_history(
    db: Session,
    *,
    current_user_id: int,
    query: str,
    limit: int = 30,
) -> list[dict]:
    term = query.strip()
    if not term:
        return []

    rows = db.execute(
        text(
            """
            WITH participant_conversations AS (
                SELECT conversation_id
                FROM conversation_participants
                WHERE admin_id = :user_id
            ),
            ranked AS (
                SELECT
                    im.id AS message_id,
                    im.conversation_id,
                    im.content,
                    im.content_type,
                    im.created_at,
                    GREATEST(
                        COALESCE(
                            ts_rank_cd(
                                im.search_vector,
                                plainto_tsquery('english', :term)
                            ),
                            0
                        ),
                        similarity(im.content, :term),
                        word_similarity(:term, im.content)
                    ) AS rank_score
                FROM internal_messages im
                WHERE im.conversation_id IN (SELECT conversation_id FROM participant_conversations)
                  AND im.content_type = 'text'
                  AND (
                        im.search_vector @@ plainto_tsquery('english', :term)
                        OR im.content ILIKE :like_term
                        OR similarity(im.content, :term) >= :similarity_threshold
                        OR word_similarity(:term, im.content) >= :word_similarity_threshold
                  )
            )
            SELECT message_id, conversation_id, content, content_type, created_at, rank_score
            FROM ranked
            ORDER BY rank_score DESC, created_at DESC
            LIMIT :limit
            """
        ),
        {
            "user_id": current_user_id,
            "term": term,
            "like_term": f"%{term}%",
            "similarity_threshold": _SIMILARITY_THRESHOLD,
            "word_similarity_threshold": _WORD_SIMILARITY_THRESHOLD,
            "limit": limit,
        },
    ).mappings()

    results: list[dict] = []
    for row in rows:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == row["conversation_id"])
            .first()
        )
        if not conversation:
            continue

        if conversation.type == "group":
            conversation_name = conversation.name or "Group chat"
        else:
            conversation_name = serialize_conversation(
                db,
                conversation,
                current_user_id=current_user_id,
            )["display_name"]

        content = row["content"] or ""
        if row["content_type"] == "audio":
            snippet = "Voice note"
        else:
            snippet = _build_snippet(content, term)

        results.append(
            {
                "message_id": int(row["message_id"]),
                "conversation_id": int(row["conversation_id"]),
                "snippet": snippet,
                "timestamp": row["created_at"],
                "conversation_name": conversation_name,
            }
        )

    return results
