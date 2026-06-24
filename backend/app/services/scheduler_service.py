from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.services.audit_runner import run_scheduled_security_audit
from app.services.pipeline_service import process_stalled_document_reminders

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_security_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.SECURITY_AUDIT_ENABLED:
        logger.info("Security audit scheduler disabled via SECURITY_AUDIT_ENABLED.")
        return None
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_scheduled_security_audit,
        trigger="cron",
        hour=settings.SECURITY_AUDIT_CRON_HOUR,
        minute=0,
        id="nexus_daily_security_audit",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        run_scheduled_document_reminders,
        trigger="cron",
        hour=9,
        minute=0,
        id="nexus_daily_document_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Security audit scheduler started (daily at %02d:00 UTC).",
        settings.SECURITY_AUDIT_CRON_HOUR,
    )
    return _scheduler


def shutdown_security_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Security audit scheduler stopped.")


def run_scheduled_document_reminders() -> None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        sent = process_stalled_document_reminders(db)
        logger.info("Document reminder job finished. reminders_sent=%s", sent)
    except Exception:
        logger.exception("Scheduled document reminder job failed.")
        db.rollback()
    finally:
        db.close()
