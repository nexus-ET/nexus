from __future__ import annotations

import logging
import threading

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)

# Stable advisory lock key for cross-process Meta lead sync exclusion (PostgreSQL).
_LEAD_SYNC_ADVISORY_LOCK_KEY = 84_729_103

_process_lock = threading.Lock()
_lock_engine: Engine | None = None
_lock_raw_conn = None  # dedicated connection holding the session advisory lock
_lock_held = False


def _uses_postgres() -> bool:
    return settings.DATABASE_URL.strip().lower().startswith("postgresql")


def _get_lock_engine() -> Engine:
    global _lock_engine
    if _lock_engine is None:
        # Dedicated NullPool engine so advisory locks are never stranded on a
        # recycled SQLAlchemy SessionLocal pool connection.
        _lock_engine = create_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            future=True,
        )
    return _lock_engine


def _force_clear_orphaned_advisory_locks(conn) -> int:
    """
    Terminate idle backends that still hold our advisory lock when no sync is
    active. This clears stranded locks left by pooled connections that never
    unlocked after a Meta sync finished or crashed.
    """
    rows = conn.execute(
        text(
            """
            SELECT l.pid
            FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory'
              AND l.classid = 0
              AND l.objid = :lock_key
              AND l.granted IS TRUE
              AND l.pid <> pg_backend_pid()
              AND COALESCE(a.state, '') LIKE 'idle%'
            """
        ),
        {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
    ).fetchall()
    cleared = 0
    for row in rows:
        pid = int(row[0])
        try:
            terminated = conn.execute(
                text("SELECT pg_terminate_backend(:pid)"),
                {"pid": pid},
            ).scalar()
            if terminated:
                cleared += 1
                logger.warning(
                    "Terminated idle backend pid=%s holding stranded Meta lead-sync advisory lock.",
                    pid,
                )
        except Exception:
            logger.exception("Failed to terminate stranded lead-sync lock holder pid=%s", pid)
    return cleared


def recover_orphaned_lead_sync_locks(db: Session, *, stale_after_minutes: int = 10) -> dict[str, int]:
    """Mark abandoned IN_PROGRESS sync logs failed and clear stranded advisory locks."""
    from app.services.sync_log_service import recover_stale_sync_logs

    recovered_logs = recover_stale_sync_logs(db, older_than_minutes=stale_after_minutes)
    cleared_locks = 0

    if _uses_postgres():
        from app.models.sync_log import SyncLog
        from app.services.sync_log_service import STATUS_IN_PROGRESS

        active = (
            db.query(SyncLog.id)
            .filter(SyncLog.status == STATUS_IN_PROGRESS)
            .limit(1)
            .first()
        )
        if active is None:
            engine = _get_lock_engine()
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                cleared_locks = _force_clear_orphaned_advisory_locks(conn)

    resolved_exceptions = 0
    if recovered_logs or cleared_locks:
        try:
            from app.services.exception_log_service import auto_resolve_lead_sync_lock_exceptions

            parts = []
            if cleared_locks:
                parts.append(f"cleared {cleared_locks} stranded advisory lock(s)")
            if recovered_logs:
                parts.append(f"marked {recovered_logs} abandoned sync log(s) failed")
            resolved_exceptions = auto_resolve_lead_sync_lock_exceptions(
                db,
                detail="; ".join(parts) + ".",
            )
        except Exception:
            logger.exception("Failed to auto-resolve lead-sync lock exceptions after recovery.")

    return {
        "recovered_logs": int(recovered_logs or 0),
        "cleared_locks": int(cleared_locks or 0),
        "resolved_exceptions": int(resolved_exceptions or 0),
    }


def try_acquire_lead_sync(db: Session) -> bool:
    """
    Ensure only one Meta lead sync runs at a time (per process and across workers).

    Returns False when another sync is already active.
    """
    global _lock_raw_conn, _lock_held

    recover_orphaned_lead_sync_locks(db, stale_after_minutes=10)

    if not _process_lock.acquire(blocking=False):
        return False

    if not _uses_postgres():
        _lock_held = True
        return True

    try:
        engine = _get_lock_engine()
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
        ).scalar()

        if not acquired:
            # No active sync log but lock still held by an idle pool connection.
            from app.models.sync_log import SyncLog
            from app.services.sync_log_service import STATUS_IN_PROGRESS

            active = (
                db.query(SyncLog.id)
                .filter(SyncLog.status == STATUS_IN_PROGRESS)
                .limit(1)
                .first()
            )
            if active is None:
                _force_clear_orphaned_advisory_locks(conn)
                acquired = conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
                ).scalar()

        if acquired:
            _lock_raw_conn = conn
            _lock_held = True
            return True

        conn.close()
    except Exception:
        logger.exception("Failed to acquire PostgreSQL advisory lock for lead sync.")
        try:
            if _lock_raw_conn is not None:
                _lock_raw_conn.close()
        except Exception:
            pass
        _lock_raw_conn = None
        _lock_held = False
        _process_lock.release()
        return False

    _lock_held = False
    _process_lock.release()
    return False


def release_lead_sync(db: Session | None = None) -> None:
    """Release process and database advisory locks acquired by try_acquire_lead_sync."""
    global _lock_raw_conn, _lock_held

    if _uses_postgres() and _lock_raw_conn is not None:
        try:
            _lock_raw_conn.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
            )
        except Exception:
            logger.exception("Failed to release PostgreSQL advisory lock for lead sync.")
        try:
            _lock_raw_conn.close()
        except Exception:
            logger.exception("Failed to close Meta lead-sync lock connection.")
        _lock_raw_conn = None

    if _lock_held or _process_lock.locked():
        try:
            if _process_lock.locked():
                _process_lock.release()
        except RuntimeError:
            logger.exception("Meta lead-sync process lock release failed.")
    _lock_held = False


def lead_sync_lock_status(db: Session) -> dict:
    """Diagnostics for dashboard / support when Sync Now is blocked."""
    from app.models.sync_log import SyncLog
    from app.services.sync_log_service import STATUS_IN_PROGRESS

    in_progress = (
        db.query(SyncLog)
        .filter(SyncLog.status == STATUS_IN_PROGRESS)
        .order_by(SyncLog.id.desc())
        .all()
    )
    advisory_holders: list[dict] = []
    if _uses_postgres():
        try:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT l.pid, a.state, a.query_start,
                               left(COALESCE(a.query, ''), 120) AS query
                        FROM pg_locks l
                        LEFT JOIN pg_stat_activity a ON a.pid = l.pid
                        WHERE l.locktype = 'advisory'
                          AND l.classid = 0
                          AND l.objid = :lock_key
                          AND l.granted IS TRUE
                        """
                    ),
                    {"lock_key": _LEAD_SYNC_ADVISORY_LOCK_KEY},
                )
                .mappings()
                .all()
            )
            advisory_holders = [dict(row) for row in rows]
        except Exception:
            logger.exception("Unable to inspect Meta lead-sync advisory locks.")

    return {
        "process_lock_held": _process_lock.locked() or _lock_held,
        "in_progress_sync_log_ids": [row.id for row in in_progress],
        "advisory_holders": advisory_holders,
    }
