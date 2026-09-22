from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from app.services.presence_service import presence_tracker

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Multi-tab safe: one user may have several open Nexus sockets."""

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        bucket = self._connections.setdefault(user_id, [])
        bucket.append(websocket)
        presence_tracker.user_connected(user_id)
        await self.broadcast(
            {
                "type": "presence.online",
                "user_id": user_id,
                "online_user_ids": list(self._connections.keys()),
            },
            exclude_user_id=user_id,
        )

    def disconnect(self, user_id: int, websocket: WebSocket | None = None) -> bool:
        """Remove one socket (or all). Returns True when the user is now offline."""
        bucket = self._connections.get(user_id)
        if not bucket:
            presence_tracker.user_disconnected(user_id)
            return True

        if websocket is None:
            self._connections.pop(user_id, None)
        else:
            remaining = [ws for ws in bucket if ws is not websocket]
            if remaining:
                self._connections[user_id] = remaining
                return False
            self._connections.pop(user_id, None)

        presence_tracker.user_disconnected(user_id)
        return True

    def connection_count(self, user_id: int) -> int:
        return len(self._connections.get(user_id) or ())

    async def send_personal(self, user_id: int, payload: dict[str, Any]) -> None:
        bucket = list(self._connections.get(user_id) or ())
        if not bucket:
            return
        text = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for websocket in bucket:
            try:
                await websocket.send_text(text)
            except Exception:
                logger.debug("Failed to send websocket message to user %s", user_id)
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(user_id, websocket)

    async def broadcast(
        self,
        payload: dict[str, Any],
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        text = json.dumps(payload, default=str)
        dead: list[tuple[int, WebSocket]] = []
        for user_id, bucket in list(self._connections.items()):
            if exclude_user_id is not None and user_id == exclude_user_id:
                continue
            for websocket in list(bucket):
                try:
                    await websocket.send_text(text)
                except Exception:
                    dead.append((user_id, websocket))
        for user_id, websocket in dead:
            self.disconnect(user_id, websocket)

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
        from app.db.database import safe_close_session

        safe_close_session(db)
