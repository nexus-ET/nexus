from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.config import settings

logger = logging.getLogger(__name__)

# Transient transport failures worth one or two retries (provider resets, flaky TLS).
_TRANSIENT_SMTP_ERRORS = (
    ConnectionResetError,
    ConnectionAbortedError,
    ConnectionRefusedError,
    TimeoutError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    OSError,
)


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and (settings.SMTP_FROM_EMAIL or settings.SMTP_USER))


def _plain_to_simple_html(body: str) -> str:
    """Minimal HTML alternative — improves inbox placement vs plain-only bulk-looking mail."""
    escaped = (
        (body or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    paragraphs = []
    for block in escaped.split("\n\n"):
        lines = "<br>\n".join(line for line in block.split("\n"))
        paragraphs.append(f"<p style=\"margin:0 0 12px;line-height:1.5;\">{lines}</p>")
    inner = "".join(paragraphs) or "<p></p>"
    return (
        "<!DOCTYPE html><html><body style=\"font-family:Segoe UI,Arial,sans-serif;"
        "font-size:15px;color:#1a1a1a;background:#ffffff;padding:16px;\">"
        f"{inner}</body></html>"
    )


def _deliver(message: EmailMessage, *, recipients: list[str]) -> None:
    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    # Port 465 = implicit SSL (SMTP_SSL). Port 587 = plain SMTP + STARTTLS.
    use_implicit_ssl = port == 465
    # Envelope MAIL FROM must match the authenticated mailbox on many hosts
    # (GoDaddy / Hostinger); a mismatched From header alone often drops external mail.
    envelope_from = (settings.SMTP_USER or settings.SMTP_FROM_EMAIL or "").strip() or None

    if use_implicit_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message, from_addr=envelope_from, to_addrs=recipients)
        return

    with smtplib.SMTP(host, port, timeout=20) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message, from_addr=envelope_from, to_addrs=recipients)


def send_email(
    to_addresses: list[str],
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
) -> bool:
    recipients = [addr.strip() for addr in to_addresses if addr and str(addr).strip()]
    if not recipients:
        return False

    if not _smtp_configured():
        logger.warning(
            "SMTP is not configured (SMTP_HOST / SMTP_FROM_EMAIL). Skipping email: %s",
            subject,
        )
        return False

    message = EmailMessage()
    from_email = (settings.SMTP_FROM_EMAIL or settings.SMTP_USER or "").strip()
    smtp_user = (settings.SMTP_USER or "").strip()
    # Prefer authenticated mailbox as visible From when it is a real email — improves
    # SPF/alignment for external recipients (e.g. candidate @erxa.in vs counsellor @edutrust.in).
    visible_from = smtp_user if smtp_user and "@" in smtp_user else from_email
    display_name = (getattr(settings, "SMTP_FROM_NAME", None) or "Nexus Counselling").strip()
    message["From"] = formataddr((display_name, visible_from))
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    domain = visible_from.split("@", 1)[-1] if "@" in visible_from else "localhost"
    message["Message-ID"] = make_msgid(domain=domain)
    # Transactional marker — avoid Precedence:bulk which spam filters penalize.
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "OOF, AutoReply"
    if from_email and from_email.lower() != visible_from.lower():
        message["Reply-To"] = from_email
    elif visible_from:
        message["Reply-To"] = visible_from

    message.set_content(body)
    message.add_alternative(html_body or _plain_to_simple_html(body), subtype="html")

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            _deliver(message, recipients=recipients)
            logger.info("Email sent subject=%r to=%s from=%s", subject, recipients, visible_from)
            return True
        except smtplib.SMTPRecipientsRefused as exc:
            logger.error(
                "SMTP refused recipients for %r: %s",
                subject,
                exc.recipients,
            )
            return False
        except smtplib.SMTPSenderRefused as exc:
            logger.error(
                "SMTP refused sender for %r (from=%s): %s",
                subject,
                from_email,
                exc,
            )
            return False
        except smtplib.SMTPDataError as exc:
            # Permanent/data errors (often surfaced as "mail delivery failure" by providers).
            logger.error("SMTP data error sending %r: %s", subject, exc)
            return False
        except _TRANSIENT_SMTP_ERRORS as exc:
            if attempt >= attempts:
                logger.exception(
                    "Failed to send email after %s attempts: %s (%s)",
                    attempts,
                    subject,
                    exc,
                )
                return False
            delay = 0.6 * attempt
            logger.warning(
                "Transient SMTP error sending %r (attempt %s/%s): %s; retrying in %.1fs",
                subject,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)
        except Exception:
            logger.exception("Failed to send email: %s", subject)
            return False
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
