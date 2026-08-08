from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.admin_role import AdminRole
from app.models.lead import Lead
from app.models.notification_log import NotificationLog
from app.models.user import User
from app.services.email_service import send_email
from app.utils.timezone import utc_now

logger = logging.getLogger(__name__)

HANDOFF_NOTIFY_ROLE_NAMES = (
    "Student Advisor",
    "Student Manager",
    "Web Admin",
    "Super Admin",
)

_HANDOFF_DEDUPE_WINDOW = timedelta(minutes=15)


def _lead_display_name(lead: Lead) -> str:
    name = (lead.full_name or "").strip()
    return name or f"Lead #{lead.id}"


def _handoff_marker(lead_id: int) -> str:
    return f"[handoff:lead:{lead_id}]"


def _recent_handoff_notification_exists(db: Session, user_id: int, lead_id: int) -> bool:
    marker = _handoff_marker(lead_id)
    cutoff = utc_now() - _HANDOFF_DEDUPE_WINDOW
    return (
        db.query(NotificationLog.id)
        .filter(
            NotificationLog.user_id == user_id,
            NotificationLog.channel == "in_app",
            NotificationLog.message.contains(marker),
            NotificationLog.sent_at >= cutoff,
        )
        .first()
        is not None
    )


def _active_handoff_recipients(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(AdminRole, User.admin_role_id == AdminRole.id)
        .filter(
            User.is_active.is_(True),
            AdminRole.is_active.is_(True),
            AdminRole.name.in_(HANDOFF_NOTIFY_ROLE_NAMES),
        )
        .all()
    )


def notify_advisors_of_handoff(
    db: Session,
    lead: Lead,
    *,
    reason: str,
    message_preview: str = "",
    ai_confidence: float | None = None,
) -> int:
    """
    Create in-app notifications for the advisor team and send a summary email when SMTP is configured.
    Returns the number of in-app notifications created.
    """
    marker = _handoff_marker(lead.id)
    student = _lead_display_name(lead)
    preview = (message_preview or "").strip()
    if len(preview) > 240:
        preview = f"{preview[:237]}..."

    body_lines = [
        marker,
        f"Lead {lead.id} ({student}) requires human handoff.",
        f"Reason: {reason}.",
    ]
    if ai_confidence is not None:
        body_lines.append(f"AI confidence: {round(float(ai_confidence) * 100, 1)}%")
    if preview:
        body_lines.append(f'Latest message: "{preview}"')
    body_lines.append("Open Handoffs in NEXUS to continue on WhatsApp.")
    message_body = "\n".join(body_lines)

    title = f"Handoff: {student}"
    created = 0

    recipients = _active_handoff_recipients(db)
    for user in recipients:
        if _recent_handoff_notification_exists(db, user.id, lead.id):
            continue
        db.add(
            NotificationLog(
                booking_id=None,
                user_id=user.id,
                channel="in_app",
                status="sent",
                title=title,
                message=message_body,
                priority="urgent",
                sent_at=utc_now(),
            )
        )
        created += 1

    if created:
        db.commit()

    emails = sorted({user.email.strip() for user in recipients if user.email and user.email.strip()})
    if emails:
        email_subject = f"NEXUS handoff — {student}"
        email_body = (
            f"A student conversation was escalated to human advisors.\n\n"
            f"Lead ID: {lead.id}\n"
            f"Student: {student}\n"
            f"Reason: {reason}\n"
        )
        if ai_confidence is not None:
            email_body += f"AI confidence: {round(float(ai_confidence) * 100, 1)}%\n"
        if preview:
            email_body += f'Latest message: "{preview}"\n'
        email_body += "\nReview the Handoffs queue in NEXUS."
        try:
            send_email(emails, email_subject, email_body)
        except Exception:
            logger.exception("Failed to send handoff alert email for lead_id=%s", lead.id)

    return created
