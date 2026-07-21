"""Conditional uptime monitoring — only runs when MONITORING_STATUS is exactly Active."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.services.email_service import send_email
from app.services.settings_service import get_setting, parse_alert_emails

logger = logging.getLogger(__name__)

MONITORING_STATUS_ACTIVE = "Active"
DEFAULT_PING_TIMEOUT_SECONDS = 15


def run_uptime_monitoring_check() -> None:
    """Scheduled worker: abort unless monitoring is Active, then ping and alert on failure."""
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        # CRITICAL: read config first; skip all network I/O unless status is exactly Active.
        monitoring_status = (
            get_setting("MONITORING_STATUS", default="Inactive", db=db) or "Inactive"
        ).strip()
        if monitoring_status != MONITORING_STATUS_ACTIVE:
            logger.info(
                "Uptime monitoring check aborted (MONITORING_STATUS=%r; required %r).",
                monitoring_status,
                MONITORING_STATUS_ACTIVE,
            )
            return

        target_url = (get_setting("UPTIME_TARGET_URL", default="", db=db) or "").strip()
        alert_recipients = parse_alert_emails(
            get_setting("ALERT_EMAIL", default="", db=db) or ""
        )

        if not target_url:
            logger.warning(
                "Monitoring is Active but UPTIME_TARGET_URL is empty; skipping ping."
            )
            return

        ok, detail = _ping_uptime_target(target_url)
        if ok:
            logger.info("Uptime check succeeded for %s (%s).", target_url, detail)
            return

        logger.error("Uptime check failed for %s: %s", target_url, detail)
        if not alert_recipients:
            logger.warning(
                "Uptime check failed but ALERT_EMAIL is empty; no notification sent."
            )
            return

        sent = send_email(
            alert_recipients,
            subject=f"[Nexus] Uptime alert: {target_url}",
            body=(
                "Nexus uptime monitoring detected a failure.\n\n"
                f"Target URL: {target_url}\n"
                f"Checked at (UTC): {datetime.now(timezone.utc).isoformat()}\n"
                f"Result: {detail}\n\n"
                "Monitoring Status is Active. Set MONITORING_STATUS to Inactive in "
                "Application Settings to pause checks."
            ),
        )
        if sent:
            logger.info("Uptime failure alert emailed to %s.", ", ".join(alert_recipients))
        else:
            logger.warning(
                "Uptime failure alert could not be sent to %s.",
                ", ".join(alert_recipients),
            )
    except Exception:
        logger.exception("Uptime monitoring check crashed.")
    finally:
        db.close()


def _ping_uptime_target(url: str) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=DEFAULT_PING_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code == 200:
            return True, f"HTTP {response.status_code}"
        return False, f"HTTP {response.status_code} (expected 200)"
    except httpx.TimeoutException:
        return False, f"Connection timed out after {DEFAULT_PING_TIMEOUT_SECONDS}s"
    except httpx.HTTPError as exc:
        return False, f"Connection error: {exc}"
