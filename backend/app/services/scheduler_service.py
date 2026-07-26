from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.services.audit_logger import cleanup_old_audit_logs
from app.services.audit_runner import run_scheduled_security_audit
from app.services.exception_log_service import cleanup_old_exception_logs
from app.services.pipeline_service import process_stalled_document_reminders

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_security_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    if settings.SECURITY_AUDIT_ENABLED:
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
        logger.info(
            "Security audit job registered (daily at %02d:00 UTC).",
            settings.SECURITY_AUDIT_CRON_HOUR,
        )
    else:
        logger.info("Security audit job disabled via SECURITY_AUDIT_ENABLED.")

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
    _scheduler.add_job(
        cleanup_old_audit_logs,
        trigger="cron",
        hour=3,
        minute=15,
        id="nexus_daily_audit_log_cleanup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        cleanup_old_exception_logs,
        trigger="cron",
        hour=3,
        minute=20,
        id="nexus_daily_exception_log_cleanup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        run_scheduled_calendar_intake_reminders,
        trigger="cron",
        hour=8,
        minute=30,
        id="nexus_daily_calendar_intake_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if settings.MONITORING_CHECK_ENABLED:
        interval_minutes = max(1, int(settings.MONITORING_CHECK_INTERVAL_MINUTES or 5))
        _scheduler.add_job(
            run_scheduled_uptime_monitoring_check,
            trigger="interval",
            minutes=interval_minutes,
            id="nexus_uptime_monitoring_check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "Uptime monitoring job registered (every %s minute(s); gated by MONITORING_STATUS).",
            interval_minutes,
        )
    else:
        logger.info("Uptime monitoring scheduler disabled via MONITORING_CHECK_ENABLED.")

    # Counsellor digest (morning window) + 15-min pre-session nudges.
    _scheduler.add_job(
        run_scheduled_admin_session_reminders,
        trigger="interval",
        minutes=1,
        id="nexus_admin_session_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("Counsellor session reminder job registered (every 1 minute).")

    _scheduler.start()
    logger.info("Operational scheduler started.")
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


def run_scheduled_calendar_intake_reminders() -> None:
    from app.db.database import SessionLocal
    from app.services.hierarchical_intake_service import process_calendar_intake_reminders

    db = SessionLocal()
    try:
        created = process_calendar_intake_reminders(db)
        logger.info("Calendar intake reminder job finished. alerts_created=%s", created)
    except Exception:
        logger.exception("Scheduled calendar intake reminder job failed.")
        db.rollback()
    finally:
        db.close()


def run_scheduled_uptime_monitoring_check() -> None:
    from app.services.monitoring_uptime_service import run_uptime_monitoring_check

    try:
        run_uptime_monitoring_check()
    except Exception:
        logger.exception("Scheduled uptime monitoring check failed.")


def run_scheduled_admin_session_reminders() -> None:
    from app.services.admin_session_reminders import process_admin_session_reminder_tick

    try:
        result = process_admin_session_reminder_tick()
        if result.get("digests") or result.get("nudges"):
            logger.info(
                "Counsellor session reminders finished. digests=%s nudges=%s",
                result.get("digests"),
                result.get("nudges"),
            )
    except Exception:
        logger.exception("Scheduled counsellor session reminder job failed.")
