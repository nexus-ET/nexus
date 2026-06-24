from __future__ import annotations

import logging
import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# Stable advisory lock key for cross-process Meta lead sync exclusion (PostgreSQL).
_LEAD_SYNC_ADVISORY_LOCK_KEY = 84_729_103

_process_lock = threading.Lock()
_advisory_lock_session: Session | None = None


def _uses_postgres() -> bool:
    return settings.DATABASE_URL.strip().lower().startswith("postgresql")


def try_acquire_lead_sync(db: Session) -> bool:
    """
    Ensure only one Meta lead sync runs at a time (per process and across workers).

    Returns False when another sync is already active.
    """
    if not _process_lock.acquire(blocking=False):
        return False

    if not _uses_postgres():
        return True

    global _advisory_lock_session
    try:
        acquired = db.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
        ).scalar()
        if acquired:
            _advisory_lock_session = db
            return True
    except Exception:
        logger.exception("Failed to acquire PostgreSQL advisory lock for lead sync.")
        _process_lock.release()
        return False

    _process_lock.release()
    return False


def release_lead_sync(db: Session) -> None:
    """Release process and database advisory locks acquired by try_acquire_lead_sync."""
    global _advisory_lock_session

    if _uses_postgres() and _advisory_lock_session is db:
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
            )
        except Exception:
            logger.exception("Failed to release PostgreSQL advisory lock for lead sync.")
        _advisory_lock_session = None

    _process_lock.release()
