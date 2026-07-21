from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


def send_email(to_addresses: list[str], subject: str, body: str) -> bool:
    if not to_addresses:
        return False

    if not _smtp_configured():
        logger.warning(
            "SMTP is not configured (SMTP_HOST / SMTP_FROM_EMAIL). Skipping email: %s",
            subject,
        )
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = ", ".join(to_addresses)
    message["Subject"] = subject
    message.set_content(body)

    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    # Port 465 = implicit SSL (SMTP_SSL). Port 587 = plain SMTP + STARTTLS.
    use_implicit_ssl = port == 465

    try:
        if use_implicit_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send email: %s", subject)
        return False


def notify_super_admins_of_deactivation(
    *,
    deactivated_user_name: str,
    deactivated_user_email: str,
    deactivated_user_role: str,
    reason: str,
    reason_description: str,
    super_admin_emails: list[str],
) -> bool:
    subject = f"[Nexus] User deactivated: {deactivated_user_name}"
    body = (
        "A Nexus admin account was deactivated.\n\n"
        f"User: {deactivated_user_name}\n"
        f"Email: {deactivated_user_email}\n"
        f"Role: {deactivated_user_role}\n"
        f"Reason: {reason}\n"
        f"Details: {reason_description}\n\n"
        "This notification was sent to all Super Admin accounts."
    )
    return send_email(super_admin_emails, subject, body)
