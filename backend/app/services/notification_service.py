from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.config import settings
from app.models.counselling_booking import CounsellingBooking
from app.models.lead import Lead
from app.models.message import Message
from app.models.notification_log import NotificationLog
from app.models.user import User
from app.services.email_service import send_email
from app.services.lead_conversation import touch_lead_activity
from app.services.messaging import _recent_identical_outbound
from app.services.phone_utils import find_lead_by_phone
from app.services.push_service import push_notification_service
from app.services.messaging import send_message

logger = logging.getLogger(__name__)


def _resolve_lead_for_booking_notification(
    db: Session,
    *,
    lead_id: int | None,
    candidate_phone: str | None,
) -> Lead | None:
    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            return lead
    return find_lead_by_phone(db, candidate_phone)


def persist_booking_confirmation_in_chat(
    db: Session,
    *,
    lead_id: int | None,
    candidate_phone: str | None,
    message: str,
) -> bool:
    """Mirror consultant assignment WhatsApp confirmations in AI-Active chat history."""
    lead = _resolve_lead_for_booking_notification(
        db,
        lead_id=lead_id,
        candidate_phone=candidate_phone,
    )
    if not lead:
        logger.info(
            "Booking confirmation not saved to chat history — no lead matched (lead_id=%s phone=%s)",
            lead_id,
            candidate_phone,
        )
        return False

    cleaned = (message or "").strip()
    if not cleaned:
        return False
    if _recent_identical_outbound(db, lead.id, cleaned, within_minutes=60):
        return False

    db.add(
        Message(
            lead_id=lead.id,
            sender="advisor",
            text=cleaned,
            ai_confidence=1.0,
            is_read=True,
        )
    )
    touch_lead_activity(db, lead)
    db.commit()
    return True


def _format_admin_name(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email


def _format_time(value: datetime) -> str:
    return value.strftime("%a, %b %d at %I:%M %p").lstrip("0")


def _whatsapp_message(candidate_name: str, admin_name: str, scheduled_time: datetime) -> str:
    return (
        f"Hi {candidate_name}, session with {admin_name} is confirmed for "
        f"{_format_time(scheduled_time)}."
    )


def _email_content(candidate_name: str, admin_name: str, scheduled_time: datetime) -> tuple[str, str]:
    subject = f"Confirmation: Session with {admin_name}."
    body = f"Dear {candidate_name}, your session is {_format_time(scheduled_time)}."
    return subject, body


def _push_assignment_content(candidate_name: str, scheduled_time: datetime) -> tuple[str, str]:
    title = "New Assignment"
    body = f"Session with {candidate_name} at {_format_time(scheduled_time)}."
    return title, body


def _upcoming_appointment_content(candidate_name: str, scheduled_time: datetime) -> tuple[str, str]:
    title = "Upcoming Appointment"
    body = f"Session with {candidate_name} on {_format_time(scheduled_time)}."
    return title, body


def _booking_notification_priority(scheduled_time: datetime) -> str:
    now = datetime.utcnow()
    if scheduled_time.date() == now.date():
        return "urgent"
    days_until = (scheduled_time.date() - now.date()).days
    if days_until <= 7:
        return "important"
    return "normal"


def _booking_has_active_notification(db: Session, user_id: int, booking_id: int) -> bool:
    return (
        db.query(NotificationLog.id)
        .filter(
            NotificationLog.user_id == user_id,
            NotificationLog.booking_id == booking_id,
            NotificationLog.status != "resolved",
        )
        .first()
        is not None
    )


def ensure_in_app_booking_notifications(db: Session, user_id: int) -> int:
    """Backfill in-app inbox rows for upcoming assigned bookings."""
    now = datetime.utcnow()
    upcoming_bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.admin_id == user_id,
            CounsellingBooking.status == "SCHEDULED",
            CounsellingBooking.scheduled_time >= now - timedelta(hours=1),
        )
        .order_by(CounsellingBooking.scheduled_time.asc())
        .all()
    )

    created = 0
    for booking in upcoming_bookings:
        if _booking_has_active_notification(db, user_id, booking.id):
            continue
        title, body = _upcoming_appointment_content(booking.candidate_name, booking.scheduled_time)
        db.add(
            NotificationLog(
                booking_id=booking.id,
                user_id=user_id,
                channel="in_app",
                status="sent",
                title=title,
                message=body,
                priority=_booking_notification_priority(booking.scheduled_time),
                sent_at=datetime.utcnow(),
            )
        )
        created += 1

    if created:
        db.commit()
    return created


def _create_in_app_assignment_notification(
    db: Session,
    *,
    booking: CounsellingBooking,
    admin: User,
) -> None:
    if _booking_has_active_notification(db, admin.id, booking.id):
        return
    title, body = _push_assignment_content(booking.candidate_name, booking.scheduled_time)
    db.add(
        NotificationLog(
            booking_id=booking.id,
            user_id=admin.id,
            channel="in_app",
            status="sent",
            title=title,
            message=body,
            priority="important",
            sent_at=datetime.utcnow(),
        )
    )
    db.commit()


def _load_user_tokens(user: User | None) -> list[str]:
    if not user or not user.fcm_tokens:
        return []
    try:
        payload = json.loads(user.fcm_tokens)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(token).strip() for token in payload if str(token).strip()]


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def _log_attempt(
        self,
        *,
        booking_id: int | None,
        user_id: int | None,
        channel: str,
        status: str,
        title: str,
        message: str,
        priority: str = "normal",
    ) -> None:
        self.db.add(
            NotificationLog(
                booking_id=booking_id,
                user_id=user_id,
                channel=channel,
                status=status,
                title=title,
                message=message,
                priority="urgent" if status == "failed" else priority,
                sent_at=datetime.utcnow(),
            )
        )
        self.db.commit()

    async def send_whatsapp_confirmation(
        self,
        booking_id: int,
        candidate_name: str,
        admin_name: str,
        scheduled_time: datetime,
        candidate_phone: str | None,
        *,
        lead_id: int | None = None,
    ) -> str:
        message = _whatsapp_message(candidate_name, admin_name, scheduled_time)
        if not candidate_phone:
            self._log_attempt(
                booking_id=booking_id,
                user_id=None,
                channel="whatsapp",
                status="skipped",
                title="WhatsApp confirmation",
                message=message,
                priority="normal",
            )
            return "skipped"

        sent = await send_message(candidate_phone, message)
        status = "sent" if sent else "failed"
        if sent:
            persist_booking_confirmation_in_chat(
                self.db,
                lead_id=lead_id,
                candidate_phone=candidate_phone,
                message=message,
            )
        self._log_attempt(
            booking_id=booking_id,
            user_id=None,
            channel="whatsapp",
            status=status,
            title="WhatsApp confirmation",
            message=message,
            priority="normal",
        )
        return status

    async def send_email_confirmation(
        self,
        booking_id: int,
        candidate_name: str,
        admin_name: str,
        scheduled_time: datetime,
        candidate_email: str | None,
    ) -> str:
        subject, body = _email_content(candidate_name, admin_name, scheduled_time)
        if not candidate_email:
            self._log_attempt(
                booking_id=booking_id,
                user_id=None,
                channel="email",
                status="skipped",
                title=subject,
                message=body,
                priority="normal",
            )
            return "skipped"

        sent = await asyncio.to_thread(send_email, [candidate_email], subject, body)
        status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=booking_id,
            user_id=None,
            channel="email",
            status=status,
            title=subject,
            message=body,
            priority="normal",
        )
        return status

    async def send_push_assignment(
        self,
        booking_id: int,
        admin: User,
        candidate_name: str,
        scheduled_time: datetime,
    ) -> str:
        title, body = _push_assignment_content(candidate_name, scheduled_time)
        tokens = _load_user_tokens(admin)
        if not tokens:
            self._log_attempt(
                booking_id=booking_id,
                user_id=admin.id,
                channel="push",
                status="skipped",
                title=title,
                message=body,
                priority="important",
            )
            return "skipped"

        sent, status = await asyncio.to_thread(
            push_notification_service.send_to_tokens,
            tokens,
            title=title,
            body=body,
            data={
                "booking_id": str(booking_id),
                "type": "assignment",
            },
        )
        if status == "unavailable":
            self._log_attempt(
                booking_id=booking_id,
                user_id=admin.id,
                channel="push",
                status="skipped",
                title=title,
                message=body,
                priority="important",
            )
            return "skipped"

        final_status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=booking_id,
            user_id=admin.id,
            channel="push",
            status=final_status,
            title=title,
            message=body,
            priority="important",
        )
        return final_status

    async def send_booking_assignment_notifications(self, booking_id: int) -> dict[str, str]:
        booking = self.db.query(CounsellingBooking).filter(CounsellingBooking.id == booking_id).first()
        if not booking or not booking.admin_id:
            raise ValueError("Assigned booking is missing an admin.")

        admin = self.db.query(User).filter(User.id == booking.admin_id).first()
        if not admin:
            raise ValueError("Assigned admin record was not found.")

        admin_name = _format_admin_name(admin)
        whatsapp_status = await self.send_whatsapp_confirmation(
            booking_id=booking.id,
            candidate_name=booking.candidate_name,
            admin_name=admin_name,
            scheduled_time=booking.scheduled_time,
            candidate_phone=booking.candidate_phone,
            lead_id=booking.lead_id,
        )
        email_status = await self.send_email_confirmation(
            booking_id=booking.id,
            candidate_name=booking.candidate_name,
            admin_name=admin_name,
            scheduled_time=booking.scheduled_time,
            candidate_email=booking.candidate_email,
        )
        push_status = await self.send_push_assignment(
            booking_id=booking.id,
            admin=admin,
            candidate_name=booking.candidate_name,
            scheduled_time=booking.scheduled_time,
        )
        _create_in_app_assignment_notification(self.db, booking=booking, admin=admin)
        return {"whatsapp": whatsapp_status, "email": email_status, "push": push_status}

    async def send_urgent_alert(self, title: str, message: str) -> dict[str, int]:
        super_admins = (
            self.db.query(User)
            .filter(User.is_superuser.is_(True), User.is_active.is_(True))
            .all()
        )
        if not super_admins:
            logger.warning("No active super admins found for urgent security alert.")
            return {"email": 0, "push": 0, "whatsapp": 0}

        email_sent = 0
        push_sent = 0
        whatsapp_sent = 0
        whatsapp_enabled = settings.SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED

        for admin in super_admins:
            if admin.email:
                sent = await asyncio.to_thread(
                    send_email,
                    [admin.email],
                    title,
                    message,
                )
                status = "sent" if sent else "failed"
                if sent:
                    email_sent += 1
                self._log_attempt(
                    booking_id=None,
                    user_id=admin.id,
                    channel="email",
                    status=status,
                    title=title,
                    message=message,
                    priority="urgent",
                )

            tokens = _load_user_tokens(admin)
            if tokens:
                sent, delivery_status = await asyncio.to_thread(
                    push_notification_service.send_to_tokens,
                    tokens,
                    title=title,
                    body=message,
                    data={"type": "security_critical", "severity": "urgent"},
                )
                if delivery_status != "unavailable":
                    final_status = "sent" if sent else "failed"
                    if sent:
                        push_sent += 1
                    self._log_attempt(
                        booking_id=None,
                        user_id=admin.id,
                        channel="push",
                        status=final_status,
                        title=title,
                        message=message,
                        priority="urgent",
                    )

            if whatsapp_enabled and admin.phone_number:
                sent = await send_message(admin.phone_number, f"{title}\n\n{message}")
                status = "sent" if sent else "failed"
                if sent:
                    whatsapp_sent += 1
                self._log_attempt(
                    booking_id=None,
                    user_id=admin.id,
                    channel="whatsapp",
                    status=status,
                    title=title,
                    message=message,
                    priority="urgent",
                )

        return {"email": email_sent, "push": push_sent, "whatsapp": whatsapp_sent}

    async def send_friendly_document_reminder(
        self,
        *,
        lead_id: int,
        phone_number: str,
        candidate_name: str,
        message: str,
    ) -> bool:
        title = "Document Reminder"
        sent = await send_message(phone_number, message)
        status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=None,
            user_id=None,
            channel="whatsapp",
            status=status,
            title=title,
            message=message,
            priority="important",
        )
        return sent


def run_assignment_notifications(booking_id: int) -> None:
    db = SessionLocal()
    try:
        service = NotificationService(db)
        asyncio.run(service.send_booking_assignment_notifications(booking_id))
    except Exception:
        logger.exception("Failed to send assignment notifications for booking %s", booking_id)
    finally:
        db.close()


def register_push_token(db: Session, user: User, token: str) -> None:
    cleaned = token.strip()
    if not cleaned:
        return
    tokens = _load_user_tokens(user)
    if cleaned not in tokens:
        tokens.append(cleaned)
    user.fcm_tokens = json.dumps(tokens)
    db.commit()


def list_user_notification_inbox(db: Session, user_id: int, limit: int = 50) -> list[dict]:
    ensure_in_app_booking_notifications(db, user_id)
    rows = (
        db.query(NotificationLog)
        .filter(NotificationLog.user_id == user_id)
        .order_by(NotificationLog.sent_at.desc(), NotificationLog.id.desc())
        .limit(limit)
        .all()
    )
    priority_rank = {"urgent": 0, "important": 1, "normal": 2}
    sorted_rows = sorted(
        rows,
        key=lambda row: (priority_rank.get(row.priority or "normal", 3), -row.sent_at.timestamp()),
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "message": row.message,
            "channel": row.channel,
            "status": row.status,
            "priority": row.priority or "normal",
            "sent_at": row.sent_at,
            "booking_id": row.booking_id,
        }
        for row in sorted_rows
    ]


def get_active_user_notifications(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    ensure_in_app_booking_notifications(db, user_id)
    rows = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user_id,
            NotificationLog.status.in_(["sent", "failed"]),
        )
        .order_by(NotificationLog.sent_at.desc(), NotificationLog.id.desc())
        .limit(limit)
        .all()
    )
    severity_map = {"urgent": "HIGH", "important": "MEDIUM", "normal": "LOW"}
    return [
        {
            "id": row.id,
            "severity": severity_map.get(row.priority or "normal", "LOW"),
            "title": row.title,
            "message": row.message,
            "link_path": "/counselling" if row.booking_id else "/",
        }
        for row in rows
    ]


def resolve_user_notification(db: Session, user_id: int, notification_id: int) -> bool:
    row = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.id == notification_id,
            NotificationLog.user_id == user_id,
        )
        .first()
    )
    if not row:
        return False
    row.status = "resolved"
    db.commit()
    return True
