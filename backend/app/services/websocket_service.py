from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from app.services.presence_service import presence_tracker

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        previous = self._connections.get(user_id)
        if previous is not None:
            try:
                await previous.close()
            except Exception:
                pass
        self._connections[user_id] = websocket
        presence_tracker.user_connected(user_id)
        await self.broadcast(
            {
                "type": "presence.online",
                "user_id": user_id,
                "online_user_ids": list(self._connections.keys()),
            },
            exclude_user_id=user_id,
        )

    def disconnect(self, user_id: int) -> None:
        presence_tracker.user_disconnected(user_id)
        self._connections.pop(user_id, None)

    async def send_personal(self, user_id: int, payload: dict[str, Any]) -> None:
        websocket = self._connections.get(user_id)
        if websocket is None:
            return
        try:
            await websocket.send_text(json.dumps(payload, default=str))
        except Exception:
            logger.debug("Failed to send websocket message to user %s", user_id)

    async def broadcast(
        self,
        payload: dict[str, Any],
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        dead: list[int] = []
        for user_id, websocket in self._connections.items():
            if exclude_user_id is not None and user_id == exclude_user_id:
                continue
            try:
                await websocket.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(user_id)
        for user_id in dead:
            self.disconnect(user_id)

    def online_user_ids(self) -> list[int]:
        return list(self._connections.keys())


nexus_ws_manager = WebSocketManager()


async def broadcast_nexus_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    exclude_user_id: int | None = None,
) -> None:
    await nexus_ws_manager.broadcast(
        {"type": event_type, "data": data or {}},
        exclude_user_id=exclude_user_id,
    )


async def broadcast_to_users(user_ids: list[int], payload: dict[str, Any]) -> None:
    for user_id in user_ids:
        await nexus_ws_manager.send_personal(user_id, payload)


async def broadcast_unread_count_updates(participant_ids: list[int]) -> None:
    """Push refreshed unread totals to each participant after message activity."""
    from app.db.database import SessionLocal
    from app.services import chat_service

    if not participant_ids:
        return

    db = SessionLocal()
    try:
        unique_ids = sorted({int(user_id) for user_id in participant_ids})
        for admin_id in unique_ids:
            count = chat_service.total_unread_message_count(db, admin_id=admin_id)
            await nexus_ws_manager.send_personal(
                admin_id,
                {
                    "type": "unread_count_update",
                    "data": {"unread_message_count": count},
                },
            )
    finally:
        db.close()
