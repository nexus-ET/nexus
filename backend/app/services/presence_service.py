from __future__ import annotations

from datetime import datetime, timedelta

AWAY_THRESHOLD = timedelta(minutes=5)


class PresenceTracker:
    def __init__(self) -> None:
        self._connected: set[int] = set()
        self._last_active: dict[int, datetime] = {}
        self._last_seen: dict[int, datetime] = {}

    def user_connected(self, user_id: int) -> None:
        now = datetime.utcnow()
        self._connected.add(user_id)
        self._last_active[user_id] = now

    def user_disconnected(self, user_id: int) -> None:
        now = datetime.utcnow()
        self._connected.discard(user_id)
        self._last_seen[user_id] = self._last_active.get(user_id, now)

    def heartbeat(self, user_id: int) -> None:
        self._last_active[user_id] = datetime.utcnow()
        self._connected.add(user_id)

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._connected

    def snapshot(self, user_id: int) -> dict:
        now = datetime.utcnow()
        if user_id not in self._connected:
            last_seen = self._last_seen.get(user_id) or self._last_active.get(user_id)
            away_seconds = int((now - last_seen).total_seconds()) if last_seen else None
            return {
                "status": "offline",
                "last_seen_at": last_seen,
                "away_duration_seconds": away_seconds,
            }

        last_active = self._last_active.get(user_id, now)
        idle_seconds = int((now - last_active).total_seconds())
        if now - last_active > AWAY_THRESHOLD:
            return {
                "status": "away",
                "last_active_at": last_active,
                "away_duration_seconds": idle_seconds,
            }

        return {
            "status": "online",
            "last_active_at": last_active,
            "away_duration_seconds": 0,
        }

    def snapshot_many(self, user_ids: list[int]) -> dict[int, dict]:
        return {user_id: self.snapshot(user_id) for user_id in user_ids}


presence_tracker = PresenceTracker()
