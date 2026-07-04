from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.models.security_audit_run import SecurityAuditRun
from app.schemas.security_audit import SecurityAuditRunOut, SecurityCheckResult as SecurityCheckResultSchema
from app.services.audit_logger import write_audit_log
from app.services.notification_service import NotificationService
from app.services.security_audit import SecurityCheckResult, run_all_security_checks

logger = logging.getLogger(__name__)


def _serialize_run(run: SecurityAuditRun) -> SecurityAuditRunOut:
    try:
        raw_checks = json.loads(run.results_json or "[]")
    except json.JSONDecodeError:
        raw_checks = []
    checks = [SecurityCheckResultSchema(**item) for item in raw_checks if isinstance(item, dict)]
    return SecurityAuditRunOut(
        id=run.id,
        status=run.status,
        total_checks=run.total_checks,
        passed_checks=run.passed_checks,
        failed_checks=run.failed_checks,
        red_flags=run.red_flags,
        triggered_by=run.triggered_by,
        triggered_by_user_id=run.triggered_by_user_id,
        checks=checks,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _persist_run(
    db: Session,
    *,
    checks: list[SecurityCheckResult],
    triggered_by: str,
    triggered_by_user_id: int | None,
    started_at: datetime,
) -> SecurityAuditRun:
    failed = [check for check in checks if not check.passed]
    passed_count = len(checks) - len(failed)
    status = "pass" if not failed else "fail"
    red_flags = bool(failed)

    run = SecurityAuditRun(
        status=status,
        total_checks=len(checks),
        passed_checks=passed_count,
        failed_checks=len(failed),
        red_flags=red_flags,
        triggered_by=triggered_by,
        triggered_by_user_id=triggered_by_user_id,
        results_json=json.dumps([check.to_dict() for check in checks], default=str),
        started_at=started_at,
        completed_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _should_send_red_flag_alert(*, triggered_by: str) -> bool:
    if not settings.SECURITY_AUDIT_RED_ALERTS_ENABLED:
        return False
    if settings.SECURITY_AUDIT_ALERT_MANUAL_ONLY and triggered_by != "manual":
        return False
    return True


def _handle_red_flags(
    db: Session,
    *,
    run: SecurityAuditRun,
    failed_checks: list[SecurityCheckResult],
    triggered_by_user_id: int | None,
    triggered_by: str,
) -> bool:
    failure_summary = "; ".join(f"{check.name}: {check.message}" for check in failed_checks[:5])
    write_audit_log(
        db,
        user_id=triggered_by_user_id,
        action_type="SECURITY_CRITICAL",
        target_resource="security_audit",
        resource_id=str(run.id),
        status="failed",
        details={
            "failed_checks": [check.to_dict() for check in failed_checks],
            "summary": failure_summary,
        },
        sync_mode="AUTOMATED",
    )

    if not _should_send_red_flag_alert(triggered_by=triggered_by):
        logger.info(
            "Security audit run %s red flags logged; outbound alerts suppressed "
            "(RED_ALERTS=%s MANUAL_ONLY=%s triggered_by=%s).",
            run.id,
            settings.SECURITY_AUDIT_RED_ALERTS_ENABLED,
            settings.SECURITY_AUDIT_ALERT_MANUAL_ONLY,
            triggered_by,
        )
        return False

    title = "NEXUS Security Fortress Alert"
    message = (
        f"Security audit run #{run.id} detected {len(failed_checks)} red flag(s). "
        f"{failure_summary}"
    )
    try:
        service = NotificationService(db)
        asyncio.run(service.send_urgent_alert(title=title, message=message))
        return True
    except Exception:
        logger.exception("Failed to dispatch urgent security alert for run %s", run.id)
        return False


def run_security_audit_suite(
    db: Session,
    *,
    triggered_by: str = "scheduled",
    triggered_by_user_id: int | None = None,
) -> tuple[SecurityAuditRun, bool]:
    started_at = datetime.utcnow()
    checks = run_all_security_checks()
    failed = [check for check in checks if not check.passed]

    try:
        run = _persist_run(
            db,
            checks=checks,
            triggered_by=triggered_by,
            triggered_by_user_id=triggered_by_user_id,
            started_at=started_at,
        )
    except Exception:
        db.rollback()
        raise

    alert_sent = False
    if failed:
        alert_sent = _handle_red_flags(
            db,
            run=run,
            failed_checks=failed,
            triggered_by_user_id=triggered_by_user_id,
            triggered_by=triggered_by,
        )

    return run, alert_sent


def run_scheduled_security_audit() -> None:
    db = SessionLocal()
    try:
        run, alert_sent = run_security_audit_suite(db, triggered_by="scheduled")
        logger.info(
            "Scheduled security audit run %s finished with status=%s alert_sent=%s",
            run.id,
            run.status,
            alert_sent,
        )
    except Exception:
        logger.exception("Scheduled security audit failed.")
        db.rollback()
    finally:
        db.close()


def list_security_audit_runs(db: Session, limit: int = 20) -> list[SecurityAuditRunOut]:
    rows = (
        db.query(SecurityAuditRun)
        .order_by(SecurityAuditRun.started_at.desc(), SecurityAuditRun.id.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_run(row) for row in rows]


def get_security_audit_run(db: Session, run_id: int) -> SecurityAuditRunOut | None:
    row = db.query(SecurityAuditRun).filter(SecurityAuditRun.id == run_id).first()
    if not row:
        return None
    return _serialize_run(row)


def get_latest_security_audit_status(db: Session) -> SecurityAuditRunOut | None:
    row = (
        db.query(SecurityAuditRun)
        .order_by(SecurityAuditRun.started_at.desc(), SecurityAuditRun.id.desc())
        .first()
    )
    if not row:
        return None
    return _serialize_run(row)
