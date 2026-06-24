from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.user import User
from app.services.presence_service import presence_tracker
from app.services.websocket_service import broadcast_nexus_event, nexus_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _authenticate_ws(token: str | None) -> User | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    db: Session = SessionLocal()
    try:
        user = (
            db.query(User)
            .options(joinedload(User.admin_role_ref))
            .filter(User.id == user_id)
            .first()
        )
        if not user or not user.is_active:
            return None
        if user.is_superuser or user.admin_role_id:
            return user
        return None
    finally:
        db.close()


@router.websocket("/ws/nexus")
async def nexus_command_center_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
):
    user = _authenticate_ws(token)
    if user is None:
        await websocket.accept()
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await nexus_ws_manager.connect(user.id, websocket)
    await broadcast_nexus_event(
        "presence.updated",
        {"user_id": user.id, **presence_tracker.snapshot(user.id)},
    )
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connection.ready",
                    "data": {
                        "user_id": user.id,
                        "online_user_ids": nexus_ws_manager.online_user_ids(),
                    },
                },
                default=str,
            )
        )
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event_type = payload.get("type")
            if event_type == "ping":
                presence_tracker.heartbeat(user.id)
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("Nexus websocket disconnected for user %s", user.id, exc_info=True)
    finally:
        nexus_ws_manager.disconnect(user.id)
        await broadcast_nexus_event(
            "presence.updated",
            {"user_id": user.id, **presence_tracker.snapshot(user.id)},
        )
        await nexus_ws_manager.broadcast(
            {
                "type": "presence.offline",
                "user_id": user.id,
                "online_user_ids": nexus_ws_manager.online_user_ids(),
            }
        )
