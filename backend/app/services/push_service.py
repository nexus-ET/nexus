from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_firebase_ready = False
_init_attempted = False


def _initialize_firebase() -> bool:
    global _firebase_ready, _init_attempted
    if _firebase_ready:
        return True
    if _init_attempted:
        return False
    _init_attempted = True

    credentials_json = (settings.FIREBASE_CREDENTIALS_JSON or "").strip()
    credentials_path = (settings.FIREBASE_CREDENTIALS_PATH or "").strip()
    if not credentials_json and not credentials_path:
        logger.info("Firebase credentials not configured; push notifications disabled.")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        try:
            firebase_admin.get_app()
            _firebase_ready = True
            return True
        except ValueError:
            pass

        if credentials_json:
            payload = json.loads(credentials_json)
            cred = credentials.Certificate(payload)
        else:
            cred = credentials.Certificate(credentials_path)

        options: dict[str, Any] | None = None
        if settings.FIREBASE_PROJECT_ID:
            options = {"projectId": settings.FIREBASE_PROJECT_ID}
        firebase_admin.initialize_app(cred, options)
        _firebase_ready = True
        logger.info("Firebase Admin SDK initialized for push notifications.")
        return True
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK.")
        return False


class PushNotificationService:
    def is_available(self) -> bool:
        return _initialize_firebase()

    def send_to_tokens(
        self,
        tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        cleaned_tokens = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned_tokens:
            return False, "skipped"

        if not self.is_available():
            return False, "unavailable"

        try:
            from firebase_admin import messaging

            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data=data or {},
                tokens=cleaned_tokens,
            )
            response = messaging.send_each_for_multicast(message)
            if response.success_count > 0:
                return True, "sent"
            return False, "failed"
        except Exception:
            logger.exception("Failed to send Firebase push notification.")
            return False, "failed"


push_notification_service = PushNotificationService()
