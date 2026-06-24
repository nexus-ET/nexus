from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.db.database import SessionLocal, safe_close_session
from app.services.lead_sync_scheduler_leader import (
    claim_scheduler_leadership,
    ensure_scheduler_leadership,
    get_scheduler_leader_label,
    is_scheduler_leader,
    release_scheduler_leadership,
)
from app.services.lead_sync_settings import get_lead_sync_config, run_lead_sync_isolated
from app.services.sync_log_service import SOURCE_SCHEDULED, SYNC_MODE_AUTOMATED, TRIGGERED_BY_SYSTEM

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_scheduled_worker_lock = threading.Lock()
_active_schedule_signature: str | None = None
JOB_ID = "nexus_meta_lead_safety_net"
LEADER_HEARTBEAT_JOB_ID = "nexus_meta_lead_scheduler_heartbeat"

# Daily automated sync time (UTC). 00:00 UTC = 05:30 IST (India has no DST).
_DAILY_SYNC_HOUR_UTC = 0
_DAILY_SYNC_MINUTE_UTC = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _interval_timedelta(interval_value: int, interval_unit: str) -> timedelta:
    unit = interval_unit.strip().lower()
    value = max(1, int(interval_value))
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    if unit == "days":
        return timedelta(days=value)
    if unit == "weeks":
        return timedelta(weeks=value)
    return timedelta(hours=value)


def _schedule_signature(interval_value: int, interval_unit: str) -> str:
    """Stable key so we can detect stale APScheduler jobs that ignore Settings."""
    unit = interval_unit.strip().lower()
    value = max(1, int(interval_value))
    if unit == "days" and value == 1:
        return f"cron:daily:{_DAILY_SYNC_HOUR_UTC:02d}:{_DAILY_SYNC_MINUTE_UTC:02d}UTC"
    if unit == "weeks" and value == 1:
        return f"cron:weekly:mon:{_DAILY_SYNC_HOUR_UTC:02d}:{_DAILY_SYNC_MINUTE_UTC:02d}UTC"
    return f"interval:{unit}:{value}"


def _build_trigger(interval_value: int, interval_unit: str):
    """Build APScheduler trigger strictly from Settings values."""
    unit = interval_unit.strip().lower()
    value = max(1, int(interval_value))
    if unit == "days" and value == 1:
        return CronTrigger(
            hour=_DAILY_SYNC_HOUR_UTC,
            minute=_DAILY_SYNC_MINUTE_UTC,
            timezone="UTC",
        )
    if unit == "weeks" and value == 1:
        return CronTrigger(
            day_of_week="mon",
            hour=_DAILY_SYNC_HOUR_UTC,
            minute=_DAILY_SYNC_MINUTE_UTC,
            timezone="UTC",
        )
    kwargs = {unit: value} if unit in {"minutes", "hours", "days", "weeks"} else {"hours": value}
    return IntervalTrigger(**kwargs)


def _describe_trigger(trigger) -> str:
    if isinstance(trigger, CronTrigger):
        fields = {field.name: str(field) for field in trigger.fields}
        if fields.get("day_of_week") not in (None, "*"):
            return f"weekly (Mon {_DAILY_SYNC_HOUR_UTC:02d}:{_DAILY_SYNC_MINUTE_UTC:02d} UTC)"
        return f"daily ({_DAILY_SYNC_HOUR_UTC:02d}:{_DAILY_SYNC_MINUTE_UTC:02d} UTC)"
    interval = getattr(trigger, "interval", None)
    if interval is None:
        return str(trigger)
    total_seconds = int(interval.total_seconds())
    if total_seconds % 604_800 == 0:
        return f"every {total_seconds // 604_800} week(s)"
    if total_seconds % 86_400 == 0:
        return f"every {total_seconds // 86_400} day(s)"
    if total_seconds % 3600 == 0:
        return f"every {total_seconds // 3600} hour(s)"
    if total_seconds % 60 == 0:
        return f"every {total_seconds // 60} minute(s)"
    return f"every {total_seconds} second(s)"


def _describe_job_interval(job) -> str | None:
    if job is None or job.trigger is None:
        return None
    return _describe_trigger(job.trigger)


def _job_matches_settings(job, config: dict[str, Any]) -> bool:
    global _active_schedule_signature
    expected = _schedule_signature(config["interval_value"], config["interval_unit"])
    if _active_schedule_signature != expected:
        return False
    if job is None:
        return False
    expected_trigger = _build_trigger(config["interval_value"], config["interval_unit"])
    return _describe_trigger(job.trigger) == _describe_trigger(expected_trigger)


def _is_automated_mode() -> bool:
    db = SessionLocal()
    try:
        return get_lead_sync_config(db)["mode"] == "automated"
    finally:
        safe_close_session(db)


def _scheduler_leader_heartbeat() -> None:
    """Keep the Postgres advisory-lock connection alive and reclaim leadership if needed."""
    global _scheduler

    if not ensure_scheduler_leadership():
        if _scheduler is not None:
            logger.warning(
                "Meta lead sync scheduler heartbeat lost leadership in pid=%s.",
                os.getpid(),
            )
        return

    if _scheduler is None and settings.META_LEAD_SYNC_ENABLED:
        logger.info("Meta lead sync scheduler reclaiming leadership — re-arming job.")
        start_lead_sync_scheduler()


def reconcile_lead_sync_scheduler_from_settings() -> bool:
    """
    Re-arm the scheduler from Settings (DB).

    Returns True when automated mode is active and the job signature matches Settings.
    """
    global _scheduler

    if not ensure_scheduler_leadership():
        return False

    if _scheduler is None:
        start_lead_sync_scheduler()
        if _scheduler is None:
            return False

    db = SessionLocal()
    try:
        config = get_lead_sync_config(db)
        if config["mode"] != "automated":
            if _scheduler.get_job(JOB_ID):
                _scheduler.remove_job(JOB_ID)
                logger.info("Meta lead sync scheduler job removed (manual mode in Settings).")
            return False

        job = _scheduler.get_job(JOB_ID)
        if job is None or not _job_matches_settings(job, config):
            logger.warning(
                "Meta lead sync scheduler out of sync with Settings (%s %s); rescheduling.",
                config["interval_value"],
                config["interval_unit"],
            )
            reschedule_lead_sync_job(run_immediately=False)
        return True
    finally:
        safe_close_session(db)


def _run_scheduled_sync_worker() -> None:
    """Run one automated sync if settings allow and no other sync holds the mutex."""
    if not _is_automated_mode():
        logger.info("Scheduled Meta lead sync skipped (manual mode).")
        return

    result = run_lead_sync_isolated(
        sync_mode=SYNC_MODE_AUTOMATED,
        triggered_by_user=TRIGGERED_BY_SYSTEM,
        source=SOURCE_SCHEDULED,
        raise_http_errors=False,
    )
    if result.get("skipped"):
        logger.info("Scheduled Meta lead sync skipped — another sync is already running.")
        return
    if result.get("error"):
        logger.warning("Scheduled Meta lead sync finished with error: %s", result["error"])


def sync_historical_leads() -> None:
    """
    APScheduler entry point for automated Meta lead delta sync.

    Always reconciles with Settings first. Never creates overlapping runs.
    """
    if not reconcile_lead_sync_scheduler_from_settings():
        return

    if not _scheduled_worker_lock.acquire(blocking=False):
        logger.info("Scheduled Meta lead sync skipped — previous scheduled worker still starting.")
        return

    def _worker() -> None:
        try:
            if not _is_automated_mode():
                return
            _run_scheduled_sync_worker()
        finally:
            _scheduled_worker_lock.release()

    threading.Thread(
        target=_worker,
        name="meta-lead-scheduled-sync",
        daemon=True,
    ).start()


def get_lead_sync_scheduler_status() -> dict[str, Any]:
    """Expose scheduler health for Settings / Reports."""
    db = SessionLocal()
    try:
        config = get_lead_sync_config(db)
        configured_interval = f"{config['interval_value']} {config['interval_unit']}"
        schedule_signature = _schedule_signature(config["interval_value"], config["interval_unit"])
        configured_schedule = _describe_trigger(
            _build_trigger(config["interval_value"], config["interval_unit"])
        )
    finally:
        safe_close_session(db)

    is_leader = is_scheduler_leader()
    leader_label = get_scheduler_leader_label()

    if not settings.META_LEAD_SYNC_ENABLED:
        return {
            "scheduler_enabled": False,
            "scheduler_active": False,
            "scheduler_is_leader": is_scheduler_leader(),
            "scheduler_leader_label": leader_label,
            "configured_interval": configured_interval,
            "configured_schedule": configured_schedule,
            "schedule_signature": schedule_signature,
            "active_job_interval": None,
            "next_scheduled_run_at": None,
        }

    if _scheduler is None and ensure_scheduler_leadership():
        start_lead_sync_scheduler()

    if _scheduler is None:
        return {
            "scheduler_enabled": True,
            "scheduler_active": False,
            "scheduler_is_leader": is_leader,
            "scheduler_leader_label": leader_label,
            "configured_interval": configured_interval,
            "configured_schedule": configured_schedule,
            "schedule_signature": schedule_signature,
            "active_job_interval": None,
            "next_scheduled_run_at": None,
        }

    job = _scheduler.get_job(JOB_ID)
    if job is None or job.next_run_time is None:
        return {
            "scheduler_enabled": True,
            "scheduler_active": job is not None,
            "scheduler_is_leader": is_leader,
            "scheduler_leader_label": leader_label,
            "configured_interval": configured_interval,
            "configured_schedule": configured_schedule,
            "schedule_signature": schedule_signature,
            "active_job_interval": _describe_job_interval(job),
            "next_scheduled_run_at": None,
        }

    next_run = job.next_run_time
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    else:
        next_run = next_run.astimezone(timezone.utc)

    return {
        "scheduler_enabled": True,
        "scheduler_active": True,
        "scheduler_is_leader": is_leader,
        "scheduler_leader_label": leader_label,
        "configured_interval": configured_interval,
        "configured_schedule": configured_schedule,
        "schedule_signature": schedule_signature,
        "active_job_interval": _describe_job_interval(job),
        "next_scheduled_run_at": next_run.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def reschedule_lead_sync_job(*, run_immediately: bool = False) -> None:
    """Apply current lead sync settings to the APScheduler job."""
    global _scheduler, _active_schedule_signature

    if _scheduler is None:
        if not settings.META_LEAD_SYNC_ENABLED:
            return
        start_lead_sync_scheduler()
        if _scheduler is None:
            return

    db = SessionLocal()
    try:
        config = get_lead_sync_config(db)
        if config["mode"] != "automated":
            if _scheduler.get_job(JOB_ID):
                _scheduler.remove_job(JOB_ID)
            logger.info("Meta lead safety-net job removed (manual mode).")
            return

        interval_value = config["interval_value"]
        interval_unit = config["interval_unit"]
        trigger = _build_trigger(interval_value, interval_unit)
        _active_schedule_signature = _schedule_signature(interval_value, interval_unit)

        if isinstance(trigger, CronTrigger):
            next_run_time = None
        elif run_immediately:
            next_run_time = _utcnow()
        else:
            next_run_time = _utcnow() + _interval_timedelta(interval_value, interval_unit)

        _scheduler.add_job(
            sync_historical_leads,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
            next_run_time=next_run_time,
        )
        job = _scheduler.get_job(JOB_ID)
        next_label = job.next_run_time.isoformat() if job and job.next_run_time else "unknown"
        logger.info(
            "Meta lead sync scheduled from Settings: %s %s (%s). Next run %s.",
            interval_value,
            interval_unit,
            _describe_trigger(trigger),
            next_label,
        )
    finally:
        safe_close_session(db)


def start_lead_sync_scheduler() -> BackgroundScheduler | None:
    """Register Meta lead safety-net job from saved settings. Called on FastAPI startup."""
    global _scheduler

    if not settings.META_LEAD_SYNC_ENABLED:
        logger.info("Meta lead safety-net scheduler disabled via META_LEAD_SYNC_ENABLED.")
        return None

    if not claim_scheduler_leadership():
        logger.warning(
            "Meta lead sync scheduler skipped in pid=%s — another backend holds the lock. "
            "Stop duplicate NEXUS backends (only one process on port %s).",
            os.getpid(),
            os.getenv("NEXUS_PORT", "8002"),
        )
        return None

    db = SessionLocal()
    try:
        from app.services.sync_log_service import recover_stale_sync_logs

        recovered = recover_stale_sync_logs(db, older_than_minutes=10)
        if recovered:
            logger.warning(
                "Recovered %s stale in-progress Meta lead sync log(s) on scheduler startup.",
                recovered,
            )
    finally:
        safe_close_session(db)

    if _scheduler is not None:
        reschedule_lead_sync_job(run_immediately=False)
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _scheduler_leader_heartbeat,
        trigger=IntervalTrigger(minutes=4),
        id=LEADER_HEARTBEAT_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    reschedule_lead_sync_job(run_immediately=False)
    logger.info(
        "Meta lead safety-net scheduler started from Settings (runner=%s).",
        get_scheduler_leader_label(),
    )
    return _scheduler


def shutdown_lead_sync_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Meta lead safety-net scheduler stopped.")
    release_scheduler_leadership()
