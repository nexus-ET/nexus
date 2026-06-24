from __future__ import annotations

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings


def _resolve_storage_uri() -> str:
    redis_url = (settings.REDIS_URL or "").strip()
    if redis_url:
        return redis_url
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_GLOBAL],
    storage_uri=_resolve_storage_uri(),
)

STRICT_RATE_LIMIT = settings.RATE_LIMIT_STRICT

__all__ = ["limiter", "RateLimitExceeded", "_rate_limit_exceeded_handler", "STRICT_RATE_LIMIT"]
