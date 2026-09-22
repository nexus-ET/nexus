"""Enqueue ScanX parse jobs on Redis+RQ, with in-process fallback for local dev."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db.database import is_ssh_tunnel_database_url

logger = logging.getLogger(__name__)

QUEUE_NAME_DEFAULT = "scanx"
# Treat RQ worker registrations older than this as dead (ghost workers).
_WORKER_HEARTBEAT_MAX_AGE_SECONDS = 45
# Cap in-process parse threads so multi-upload does not thrash memory/CPU.
# Extra jobs still get a daemon thread immediately but wait for a slot.
# SSH tunnel: 2 jobs so OCR resume cannot take the whole 5+5 pool from the SPA.
_THREAD_PARSE_SLOTS = threading.Semaphore(
    2 if is_ssh_tunnel_database_url(settings.DATABASE_URL) else 4
)
# Bound Redis so enqueue/rescue never hangs a request thread for minutes.
_REDIS_SOCKET_CONNECT_TIMEOUT_S = 2.0
_REDIS_SOCKET_TIMEOUT_S = 3.0


def _redis_from_url(redis_url: str):
    from redis import Redis

    return Redis.from_url(
        redis_url,
        socket_connect_timeout=_REDIS_SOCKET_CONNECT_TIMEOUT_S,
        socket_timeout=_REDIS_SOCKET_TIMEOUT_S,
    )


def _queue_name() -> str:
    return (settings.SCANX_WORKER_QUEUE or QUEUE_NAME_DEFAULT).strip() or QUEUE_NAME_DEFAULT


def _worker_heartbeat_age_seconds(worker: Any) -> float | None:
    hb = getattr(worker, "last_heartbeat", None)
    if hb is None:
        return None
    try:
        if isinstance(hb, str):
            hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
        elif isinstance(hb, datetime):
            hb_dt = hb
        else:
            return None
        if hb_dt.tzinfo is None:
            hb_dt = hb_dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - hb_dt).total_seconds())
    except (TypeError, ValueError):
        return None


def _scanx_workers_listening(conn: Any, queue_name: str) -> bool:
    """True when at least one live RQ worker is registered for this queue."""
    try:
        from rq import Worker

        for worker in Worker.all(connection=conn):
            names = list(worker.queue_names() or [])
            if queue_name not in names:
                continue
            age = _worker_heartbeat_age_seconds(worker)
            if age is not None and age > _WORKER_HEARTBEAT_MAX_AGE_SECONDS:
                logger.warning(
                    "Ignoring stale ScanX RQ worker=%s heartbeat_age=%.0fs queue=%s",
                    getattr(worker, "name", "?"),
                    age,
                    queue_name,
                )
                continue
            return True
    except Exception:
        logger.debug("ScanX worker discovery failed", exc_info=True)
    return False


def _seed_enqueue_progress(
    document_id: int,
    *,
    mode: str,
    job_id: str | None,
    waiting_for_worker: bool,
) -> None:
    """Persist initial progress so polling shows steps before the worker runs."""
    from app.db.database import SessionLocal, safe_close_session
    from app.models.scanx import ScanxDocument
    from app.services.scanx_progress import (
        apply_progress_to_metrics,
        initial_progress_steps,
    )

    db = SessionLocal()
    try:
        doc = db.query(ScanxDocument).filter(ScanxDocument.id == int(document_id)).first()
        if not doc:
            return
        metrics = dict(doc.metrics_json or {})
        # Upload already validated MIME/pages and stored bytes.
        validate_done = bool(doc.r2_key)
        steps = initial_progress_steps(
            waiting_for_worker=waiting_for_worker,
            validate_done=validate_done,
        )
        metrics = apply_progress_to_metrics(metrics, steps)
        metrics["enqueue_mode"] = mode
        if job_id:
            metrics["job_id"] = job_id
        # Fresh enqueue clears prior rescue flags so a new stall can be recovered.
        metrics.pop("rescue_thread_started", None)
        metrics.pop("rescue_reason", None)
        metrics.pop("stale_failed", None)
        doc.metrics_json = metrics
        db.commit()
    except Exception:
        logger.exception(
            "Failed to seed ScanX progress document_id=%s", document_id
        )
    finally:
        safe_close_session(db)


def _start_thread(document_id: int) -> str:
    def _run() -> None:
        from app.services.scanx_cancel import is_cancel_requested

        if is_cancel_requested(document_id):
            logger.info("ScanX thread skipped cancelled document_id=%s", document_id)
            return
        acquired = _THREAD_PARSE_SLOTS.acquire(blocking=False)
        if not acquired:
            _mark_thread_dispatch(
                document_id,
                mode="thread",
                job_id=f"thread-{document_id}",
                note="Waiting for parse slot…",
            )
            _THREAD_PARSE_SLOTS.acquire()
            if is_cancel_requested(document_id):
                logger.info(
                    "ScanX thread slot released for cancelled document_id=%s",
                    document_id,
                )
                _THREAD_PARSE_SLOTS.release()
                return
        try:
            from app.services.scanx_jobs import process_scanx_document

            logger.info("ScanX thread worker starting document_id=%s", document_id)
            result = process_scanx_document(int(document_id))
            logger.info(
                "ScanX thread worker finished document_id=%s result=%s",
                document_id,
                result,
            )
        except Exception:
            logger.exception("In-process ScanX job failed document_id=%s", document_id)
        finally:
            _THREAD_PARSE_SLOTS.release()

    thread = threading.Thread(
        target=_run,
        name=f"scanx-doc-{document_id}",
        daemon=True,
    )
    thread.start()
    return f"thread-{document_id}"


def _mark_thread_dispatch(
    document_id: int,
    *,
    mode: str,
    job_id: str,
    note: str = "Starting in-process worker…",
) -> None:
    """Update queued step for in-process dispatch without wiping prior progress."""
    from app.db.database import SessionLocal, safe_close_session
    from app.models.scanx import ScanxDocument
    from app.services.scanx_progress import (
        STEP_STATUS_IN_PROGRESS,
        apply_progress_to_metrics,
        initial_progress_steps,
        set_step,
    )

    db = SessionLocal()
    try:
        doc = db.query(ScanxDocument).filter(ScanxDocument.id == int(document_id)).first()
        if not doc:
            return
        metrics = dict(doc.metrics_json or {})
        steps = metrics.get("progress_steps")
        if not isinstance(steps, list) or not steps:
            steps = initial_progress_steps(
                waiting_for_worker=False,
                validate_done=bool(doc.r2_key),
            )
        else:
            steps = set_step(
                list(steps),
                "queued",
                STEP_STATUS_IN_PROGRESS,
                note=note,
                label="Queued / Started",
            )
        metrics = apply_progress_to_metrics(metrics, steps)
        metrics["enqueue_mode"] = mode
        metrics["job_id"] = job_id
        doc.metrics_json = metrics
        db.commit()
    except Exception:
        logger.exception(
            "Failed to mark ScanX thread dispatch document_id=%s", document_id
        )
    finally:
        safe_close_session(db)


def schedule_process_document(document_id: int, background_tasks: Any) -> dict[str, Any]:
    """Start parse *after* Starlette flushes the HTTP response (202 / reprocess).

    Calling ``enqueue_process_document`` inside the request starts Rapid/Paddle on
    a daemon thread that holds the GIL. The async upload handler then cannot
    serialize/send 202 until OCR finishes, so the SPA hits API_SCANX_TIMEOUT_MS
    (300s) even though the route is declared 202.
    """
    job_id = f"pending-{int(document_id)}"
    background_tasks.add_task(enqueue_process_document, int(document_id))
    logger.info(
        "Scheduled ScanX process after response document_id=%s job_id=%s",
        document_id,
        job_id,
    )
    return {"mode": "scheduled", "job_id": job_id}


def enqueue_process_document(
    document_id: int,
    *,
    force_thread: bool = False,
) -> dict[str, Any]:
    """Enqueue RQ job when Redis + a live worker are available; else daemon thread.

    If REDIS_URL is set but no ScanX worker is listening, fall back to a thread
    immediately so Parsing never stalls silently on an empty queue.

    Must not be awaited from an HTTP handler — use ``schedule_process_document``
    so the client receives 202 before OCR starts.
    """
    redis_url = (settings.REDIS_URL or "").strip()
    if redis_url and not force_thread:
        try:
            from rq import Queue

            conn = _redis_from_url(redis_url)
            queue_name = _queue_name()
            workers_ok = _scanx_workers_listening(conn, queue_name)
            if workers_ok:
                queue = Queue(queue_name, connection=conn)
                job = queue.enqueue(
                    "app.services.scanx_jobs.process_scanx_document",
                    int(document_id),
                    job_timeout="15m",
                    result_ttl=86400,
                    failure_ttl=86400,
                )
                logger.info(
                    "Enqueued ScanX RQ job=%s document_id=%s queue=%s",
                    job.id,
                    document_id,
                    queue_name,
                )
                _seed_enqueue_progress(
                    document_id,
                    mode="rq",
                    job_id=job.id,
                    waiting_for_worker=True,
                )
                return {"mode": "rq", "job_id": job.id}
            logger.warning(
                "No live ScanX RQ workers on queue=%s — falling back to thread "
                "immediately for document_id=%s",
                queue_name,
                document_id,
            )
        except Exception:
            logger.exception(
                "RQ enqueue failed for document_id=%s — falling back to thread",
                document_id,
            )

    mode = "thread_forced" if force_thread else "thread"
    # Seed metrics BEFORE starting the thread so polls never see empty steps,
    # and so the worker cannot race a later seed that rewinds progress.
    provisional_job_id = f"thread-{document_id}"
    if force_thread:
        _mark_thread_dispatch(document_id, mode=mode, job_id=provisional_job_id)
    else:
        _seed_enqueue_progress(
            document_id,
            mode=mode,
            job_id=provisional_job_id,
            waiting_for_worker=False,
        )
    job_id = _start_thread(document_id)
    logger.warning(
        "Processing ScanX document_id=%s in background thread (mode=%s job_id=%s)",
        document_id,
        mode,
        job_id,
    )
    return {"mode": mode, "job_id": job_id}


def rescue_stale_waiting_document(document_id: int) -> dict[str, Any] | None:
    """If still Waiting for worker past threshold, cancel RQ job and force thread."""
    from app.db.database import SessionLocal, safe_close_session
    from app.models.scanx import ScanxDocument
    from app.constants.scanx import STATUS_PARSING
    from app.services.scanx_progress import (
        STALE_WAITING_WORKER_SECONDS,
        is_waiting_for_worker,
        waiting_age_seconds,
    )

    job_id_to_cancel: str | None = None
    db = SessionLocal()
    try:
        doc = db.query(ScanxDocument).filter(ScanxDocument.id == int(document_id)).first()
        if not doc or doc.status != STATUS_PARSING:
            return None
        metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
        if metrics.get("cancel_requested"):
            return None
        if not is_waiting_for_worker(metrics):
            return None
        age = waiting_age_seconds(metrics)
        if age is None or age < STALE_WAITING_WORKER_SECONDS:
            return None
        if metrics.get("rescue_thread_started"):
            return None
        metrics = dict(metrics)
        metrics["rescue_thread_started"] = True
        metrics["rescue_reason"] = "stale_waiting_for_worker"
        raw_job = metrics.get("job_id")
        if raw_job and not str(raw_job).startswith("thread-"):
            job_id_to_cancel = str(raw_job)
        doc.metrics_json = metrics
        db.commit()
        logger.warning(
            "ScanX document_id=%s still waiting for worker after %.1fs — forcing thread",
            document_id,
            age,
        )
    except Exception:
        logger.exception("ScanX stale rescue check failed document_id=%s", document_id)
        return None
    finally:
        safe_close_session(db)

    if job_id_to_cancel:
        _cancel_rq_job(job_id_to_cancel)

    return enqueue_process_document(document_id, force_thread=True)


def rescue_stale_parsing_document(document_id: int) -> dict[str, Any] | None:
    """Recover Parsing docs with no progress bumps (hung thread / dead RQ).

    - First stall (>60s idle): force an in-process reprocess once.
    - Second stall after rescue: mark Red Flag so UI leaves “tracking parse steps”.
    """
    from app.db.database import SessionLocal, safe_close_session
    from app.models.scanx import ScanxDocument
    from app.constants.scanx import STATUS_PARSING, STATUS_RED_FLAG
    from app.services.scanx_progress import (
        STALE_NO_PROGRESS_SECONDS,
        STEP_STATUS_FAILED,
        apply_progress_to_metrics,
        is_waiting_for_worker,
        progress_idle_seconds,
        set_step,
    )

    action: str | None = None
    job_id_to_cancel: str | None = None
    db = SessionLocal()
    try:
        doc = db.query(ScanxDocument).filter(ScanxDocument.id == int(document_id)).first()
        if not doc or doc.status != STATUS_PARSING:
            return None
        metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
        if metrics.get("cancel_requested"):
            return None
        # Waiting-for-worker path has a faster dedicated rescue.
        if is_waiting_for_worker(metrics):
            return None
        idle = progress_idle_seconds(metrics)
        if idle is None or idle < STALE_NO_PROGRESS_SECONDS:
            return None

        metrics = dict(metrics)
        already_rescued = bool(metrics.get("rescue_thread_started"))
        current_label = metrics.get("current_step_label") or metrics.get("current_step_id")
        logger.warning(
            "ScanX document_id=%s parsing idle %.1fs step=%s rescued=%s enqueue=%s",
            document_id,
            idle,
            current_label,
            already_rescued,
            metrics.get("enqueue_mode"),
        )

        if already_rescued or metrics.get("stale_failed"):
            steps = metrics.get("progress_steps")
            if not isinstance(steps, list):
                steps = []
            else:
                steps = list(steps)
            active = str(metrics.get("current_step_id") or "queued")
            steps = set_step(
                steps,
                active,
                STEP_STATUS_FAILED,
                note=f"No progress for {int(idle)}s — marked failed",
            )
            metrics = apply_progress_to_metrics(metrics, steps)
            metrics["stale_failed"] = True
            metrics["rescue_reason"] = "stale_no_progress_failed"
            doc.status = STATUS_RED_FLAG
            doc.error_code = "M7"
            doc.metrics_json = metrics
            db.commit()
            action = "failed"
            logger.error(
                "ScanX document_id=%s marked red_flag after stalled parse (%.1fs idle)",
                document_id,
                idle,
            )
        else:
            metrics["rescue_thread_started"] = True
            metrics["rescue_reason"] = "stale_no_progress"
            # Bump progress_updated_at so we don't immediately fail again.
            metrics["progress_updated_at"] = datetime.now(timezone.utc).isoformat()
            raw_job = metrics.get("job_id")
            if raw_job and not str(raw_job).startswith("thread-"):
                job_id_to_cancel = str(raw_job)
            doc.metrics_json = metrics
            db.commit()
            action = "reprocess"
    except Exception:
        logger.exception(
            "ScanX no-progress rescue check failed document_id=%s", document_id
        )
        return None
    finally:
        safe_close_session(db)

    if action == "failed":
        return {"mode": "failed", "job_id": None}
    if action != "reprocess":
        return None

    if job_id_to_cancel:
        _cancel_rq_job(job_id_to_cancel)

    logger.warning(
        "ScanX document_id=%s no progress — forcing thread reprocess",
        document_id,
    )
    return enqueue_process_document(document_id, force_thread=True)


def _cancel_rq_job(job_id: str) -> None:
    redis_url = (settings.REDIS_URL or "").strip()
    if not redis_url or not job_id:
        return
    try:
        from rq.job import Job

        conn = _redis_from_url(redis_url)
        job = Job.fetch(job_id, connection=conn)
        job.cancel()
        logger.info("Cancelled stale ScanX RQ job=%s", job_id)
    except Exception:
        logger.debug("Could not cancel ScanX RQ job=%s", job_id, exc_info=True)


def cancel_scanx_rq_job(job_id: str) -> None:
    """Public alias used by counsellor Cancel (queued RQ jobs only)."""
    _cancel_rq_job(job_id)
