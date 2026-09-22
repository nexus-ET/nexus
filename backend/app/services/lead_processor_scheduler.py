from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.database import SessionLocal, safe_close_session
from app.services.lead_ingestion_pipeline import process_raw_leads

logger = logging.getLogger(__name__)

_processor_scheduler: BackgroundScheduler | None = None
_processor_lock = threading.Lock()
JOB_ID = "nexus_raw_lead_processor"
BATCH_SIZE = 50
INTERVAL_SECONDS = 30


def _run_processor_worker() -> None:
    if not _processor_lock.acquire(blocking=False):
        logger.debug("Raw lead processor skipped — previous batch still running.")
        return

    def _worker() -> None:
        from sqlalchemy.exc import DBAPIError, OperationalError

        from app.db.database import dispose_db_pool, is_ssh_tunnel_database_url
        from app.config import settings

        db = SessionLocal()
        try:
            stats = process_raw_leads(db, batch_size=BATCH_SIZE)
            if stats["examined"]:
                logger.info(
                    "Raw lead processor batch: examined=%s promoted=%s quarantined=%s failed=%s",
                    stats["examined"],
                    stats["promoted"],
                    stats["quarantined"],
                    stats["failed"],
                )
        except (OperationalError, DBAPIError) as exc:
            # SSH-tunnel flaps are expected noise — recycle pool and wait for next tick.
            try:
                db.rollback()
            except Exception:
                pass
            dispose_db_pool(reason=f"raw lead processor: {type(exc).__name__}")
            if is_ssh_tunnel_database_url(settings.DATABASE_URL):
                logger.warning(
                    "Raw lead processor skipped this tick — DB tunnel dropped (%s).",
                    type(exc).__name__,
                )
            else:
                logger.warning(
                    "Raw lead processor skipped this tick — DB connectivity error (%s).",
                    type(exc).__name__,
                )
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            logger.exception("Raw lead processor batch failed.")
        finally:
            safe_close_session(db)
            _processor_lock.release()

    threading.Thread(target=_worker, name="raw-lead-processor", daemon=True).start()


def start_raw_lead_processor_scheduler() -> BackgroundScheduler | None:
    global _processor_scheduler
    if _processor_scheduler is not None:
        return _processor_scheduler

    _processor_scheduler = BackgroundScheduler(timezone="UTC")
    _processor_scheduler.add_job(
        _run_processor_worker,
        trigger=IntervalTrigger(seconds=INTERVAL_SECONDS),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    _processor_scheduler.start()
    logger.info(
        "Raw lead processor scheduler started (every %ss, batch=%s).",
        INTERVAL_SECONDS,
        BATCH_SIZE,
    )
    return _processor_scheduler


def shutdown_raw_lead_processor_scheduler() -> None:
    global _processor_scheduler
    if _processor_scheduler is not None:
        _processor_scheduler.shutdown(wait=False)
        _processor_scheduler = None
        logger.info("Raw lead processor scheduler stopped.")
