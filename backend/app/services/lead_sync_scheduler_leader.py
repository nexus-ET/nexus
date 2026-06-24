from __future__ import annotations

import logging
import os
import socket

from sqlalchemy import text

from app.config import settings
from app.db.database import engine

logger = logging.getLogger(__name__)

_SCHEDULER_LEADER_LOCK_KEY = 84_729_104
_leader_connection = None
_leader_pid: int | None = None


def get_scheduler_leader_label() -> str | None:
    """Human-readable identity of the process holding the scheduler advisory lock."""
    if _leader_pid is None:
        return None
    host = socket.gethostname().split(".")[0]
    return f"{host}:{_leader_pid}"


def _uses_postgres() -> bool:
    return settings.DATABASE_URL.strip().lower().startswith("postgresql")


def _reset_leader_connection() -> None:
    global _leader_connection, _leader_pid

    if _leader_connection is not None:
        try:
            _leader_connection.close()
        except Exception:
            pass
    _leader_connection = None
    _leader_pid = None


def _leader_connection_alive() -> bool:
    if _leader_connection is None:
        return False
    try:
        _leader_connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning(
            "Meta lead sync scheduler leader connection lost in pid=%s; will reclaim.",
            os.getpid(),
        )
        _reset_leader_connection()
        return False


def claim_scheduler_leadership() -> bool:
    """
    Ensure only one NEXUS backend process runs the Meta lead sync scheduler.

    Uses a PostgreSQL advisory lock on a dedicated connection (released on shutdown).
    """
    global _leader_connection, _leader_pid

    if not _uses_postgres():
        _leader_pid = os.getpid()
        return True

    if _leader_connection is not None and _leader_connection_alive():
        return True

    _reset_leader_connection()

    conn = engine.connect()
    try:
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": _SCHEDULER_LEADER_LOCK_KEY},
        ).scalar()
    except Exception:
        logger.exception("Failed to claim Meta lead sync scheduler leadership.")
        conn.close()
        return False

    if not acquired:
        conn.close()
        logger.warning(
            "Meta lead sync scheduler NOT started in pid=%s — another NEXUS backend "
            "process already holds the scheduler lock. Stop duplicate backends.",
            os.getpid(),
        )
        return False

    _leader_connection = conn
    _leader_pid = os.getpid()
    logger.info(
        "Meta lead sync scheduler leader claimed (runner=%s).",
        get_scheduler_leader_label(),
    )
    return True


def ensure_scheduler_leadership() -> bool:
    """Keep or reclaim scheduler leadership after Neon idle disconnects or duplicate restarts."""
    if not _uses_postgres():
        if _leader_pid is None:
            _leader_pid = os.getpid()
        return True

    if _leader_connection is not None and _leader_connection_alive():
        return True

    return claim_scheduler_leadership()


def is_scheduler_leader() -> bool:
    if not _uses_postgres():
        return True
    return _leader_connection is not None and _leader_connection_alive()


def release_scheduler_leadership() -> None:
    global _leader_connection, _leader_pid

    if _leader_connection is None:
        _leader_pid = None
        return

    try:
        _leader_connection.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": _SCHEDULER_LEADER_LOCK_KEY},
        )
    except Exception:
        logger.exception("Failed to release Meta lead sync scheduler leadership.")
    finally:
        _reset_leader_connection()
