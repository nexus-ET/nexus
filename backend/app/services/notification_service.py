from __future__ import annotations

import asyncio
from app.utils.timezone import utc_now
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
from app.services.messaging import (
    OutreachTemplateParameter,
    WhatsAppDeliveryError,
    _recent_identical_outbound,
    lead_has_open_whatsapp_messaging_window,
    send_message,
    send_whatsapp_template,
)
from app.services.phone_utils import clean_phone_number, find_lead_by_phone
from app.services.push_service import push_notification_service

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


def _extract_session_purpose(notes: str | None) -> str | None:
    if not notes:
        return None
    for line in str(notes).splitlines():
        cleaned = line.strip()
        if cleaned.lower().startswith("purpose:"):
            purpose = cleaned.split(":", 1)[1].strip()
            return purpose or None
    return None


def _whatsapp_message(
    candidate_name: str,
    admin_name: str,
    scheduled_time: datetime,
    *,
    session_purpose: str | None = None,
) -> str:
    purpose_line = f" Purpose: {session_purpose}." if session_purpose else ""
    return (
        f"Hi {candidate_name}, your counselling session with {admin_name} is confirmed for "
        f"{_format_time(scheduled_time)}.{purpose_line} Your counsellor will contact you at the "
        f"scheduled time (phone/WhatsApp). Reply with the buttons below to reschedule or cancel "
        f"if needed."
    )


def _template_param(value: object | None, *, fallback: str = "-") -> str:
    """Meta template variables cannot be empty and should stay single-line."""
    cleaned = " ".join(str(value or "").split()).strip()
    return (cleaned or fallback)[:1024]


def _phone_has_open_whatsapp_window(db: Session, phone: str | None, *, lead_id: int | None = None) -> bool:
    """True when Meta allows free-form session messages to this recipient."""
    if lead_id and lead_has_open_whatsapp_messaging_window(db, lead_id):
        return True
    lead = find_lead_by_phone(db, phone) if phone else None
    if lead and lead.id != lead_id and lead_has_open_whatsapp_messaging_window(db, lead.id):
        return True
    return False


def _display_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    cleaned = str(value).strip()
    return cleaned or None


def _join_list(values: list | None, *, limit: int = 6) -> str | None:
    items = [str(item).strip() for item in (values or []) if str(item).strip()]
    if not items:
        return None
    if len(items) > limit:
        remaining = len(items) - limit
        return f"{', '.join(items[:limit])} (+{remaining} more)"
    return ", ".join(items)


def _build_admin_assignment_whatsapp_message(
    db: Session,
    *,
    admin_name: str,
    booking: CounsellingBooking,
    lead: Lead | None,
) -> str:
    """Lean instant assign alert — profile depth lives in Nexus, not WhatsApp."""
    from app.services.admin_session_reminders import build_assignment_alert_message

    _ = db, lead  # reserved for future enrichment without changing call sites
    return build_assignment_alert_message(admin_name=admin_name, booking=booking)


async def _send_whatsapp_appointment_management_followup(
    db: Session,
    *,
    booking_id: int,
    lead_id: int | None,
    candidate_phone: str,
) -> str:
    """Send reschedule/cancel buttons after counsellor assignment confirmation."""
    from app.services.admissions_intake_flow import build_appointment_management_reply

    reply = build_appointment_management_reply()
    lead = _resolve_lead_for_booking_notification(
        db,
        lead_id=lead_id,
        candidate_phone=candidate_phone,
    )

    try:
        if lead:
            from app.services.twilio_ai_conversation import persist_and_send_intake_reply

            await persist_and_send_intake_reply(db, lead, candidate_phone, reply)
        else:
            from app.services.messaging import PROVIDER_WHATSAPP, get_active_provider

            if get_active_provider() == PROVIDER_WHATSAPP:
                from app.services.meta_whatsapp_interactive import deliver_meta_intake_reply

                await deliver_meta_intake_reply(candidate_phone, reply)
            else:
                from app.services.twilio_whatsapp_interactive import dispatch_whatsapp_interactive

                interactive = reply.quick_reply or reply.list_picker
                if interactive:
                    sent, fallback = dispatch_whatsapp_interactive(candidate_phone, interactive)
                    if not sent:
                        await send_message(candidate_phone, fallback)
                else:
                    await send_message(candidate_phone, reply.text)
        status = "sent"
    except Exception:
        logger.exception(
            "Failed to send appointment management buttons (booking_id=%s phone=%s)",
            booking_id,
            candidate_phone,
        )
        status = "failed"

    db.add(
        NotificationLog(
            booking_id=booking_id,
            user_id=None,
            channel="whatsapp",
            status=status,
            title="WhatsApp appointment management",
            message=reply.text,
            priority="normal",
            sent_at=utc_now(),
        )
    )
    db.commit()
    return status


def _email_content(
    candidate_name: str,
    admin_name: str,
    scheduled_time: datetime,
    *,
    session_purpose: str | None = None,
) -> tuple[str, str]:
    # Avoid spammy subject patterns ("Confirmation:", ALL CAPS, heavy punctuation).
    subject = f"Your counselling session with {admin_name}"
    purpose_line = f"\nSession purpose: {session_purpose}" if session_purpose else ""
    company = (settings.WHATSAPP_OUTREACH_COMPANY_NAME or "Edutrust").strip() or "Edutrust"
    body = (
        f"Hi {candidate_name},\n\n"
        f"Your counselling session with {admin_name} is confirmed for "
        f"{_format_time(scheduled_time)}.{purpose_line}\n\n"
        "Your counsellor will contact you at the scheduled time.\n\n"
        f"Best regards,\n{company} / Nexus Counselling"
    )
    return subject, body


def _admin_email_content(
    admin_name: str,
    booking: CounsellingBooking,
    *,
    session_purpose: str | None = None,
) -> tuple[str, str]:
    subject = f"New booking assigned: {booking.candidate_name}"
    purpose_line = f"\nPurpose: {session_purpose}" if session_purpose else ""
    body = (
        f"Hi {admin_name},\n\n"
        f"A counselling session has been assigned to you.\n\n"
        f"Candidate: {booking.candidate_name}\n"
        f"When: {_format_time(booking.scheduled_time)}\n"
        f"Booking #: {booking.id}"
        f"{purpose_line}\n"
    )
    if booking.candidate_email:
        body += f"Email: {booking.candidate_email}\n"
    if booking.candidate_phone:
        body += f"Phone: {booking.candidate_phone}\n"
    base = (settings.FRONTEND_URL or "").rstrip("/")
    if base:
        body += f"\nOpen session: {base}/my-bookings/session/{booking.id}\n"
    body += "\n— Nexus Counselling"
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
    now = utc_now()
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
    now = utc_now()
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
                sent_at=utc_now(),
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
            sent_at=utc_now(),
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
                sent_at=utc_now(),
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
        session_purpose: str | None = None,
    ) -> str:
        message = _whatsapp_message(
            candidate_name,
            admin_name,
            scheduled_time,
            session_purpose=session_purpose,
        )
        lead = _resolve_lead_for_booking_notification(
            self.db,
            lead_id=lead_id,
            candidate_phone=candidate_phone,
        )
        if lead:
            from app.services.student_status_service import is_lead_communication_opted_out

            if is_lead_communication_opted_out(self.db, lead):
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

        phone = clean_phone_number(candidate_phone or "") or (candidate_phone or "").strip()
        if not phone:
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

        window_open = _phone_has_open_whatsapp_window(
            self.db, phone, lead_id=lead.id if lead else lead_id
        )
        sent = False
        log_message = message
        if window_open:
            sent = await send_message(phone, message)
            if sent:
                persist_booking_confirmation_in_chat(
                    self.db,
                    lead_id=lead_id,
                    candidate_phone=phone,
                    message=message,
                )
                try:
                    await _send_whatsapp_appointment_management_followup(
                        self.db,
                        booking_id=booking_id,
                        lead_id=lead_id,
                        candidate_phone=phone,
                    )
                except Exception:
                    logger.exception(
                        "Appointment management WhatsApp follow-up failed for booking %s",
                        booking_id,
                    )
        else:
            template = (settings.WHATSAPP_BOOKING_TEMPLATE or "").strip()
            if not template:
                log_message = (
                    f"{message}\n\n[blocked: outside 24h WhatsApp window; "
                    "set WHATSAPP_BOOKING_TEMPLATE to an approved Meta UTILITY template]"
                )
                logger.warning(
                    "Candidate WhatsApp blocked for booking %s — outside 24h window and "
                    "WHATSAPP_BOOKING_TEMPLATE is not configured.",
                    booking_id,
                )
            else:
                language = (settings.WHATSAPP_BOOKING_TEMPLATE_LANGUAGE or "en").strip() or "en"
                params = [
                    OutreachTemplateParameter(_template_param(candidate_name, fallback="there")),
                    OutreachTemplateParameter(_template_param(admin_name, fallback="your counsellor")),
                    OutreachTemplateParameter(_template_param(_format_time(scheduled_time))),
                    OutreachTemplateParameter(
                        _template_param(session_purpose, fallback="Counselling session")
                    ),
                ]
                try:
                    wamid = await send_whatsapp_template(
                        phone,
                        template,
                        language_code=language,
                        body_parameters=params,
                    )
                    sent = True
                    log_message = (
                        f"[template:{template}] Hi {candidate_name}, session with {admin_name} "
                        f"confirmed for {_format_time(scheduled_time)}. wamid={wamid}"
                    )
                    persist_booking_confirmation_in_chat(
                        self.db,
                        lead_id=lead_id,
                        candidate_phone=phone,
                        message=message,
                    )
                except WhatsAppDeliveryError as exc:
                    logger.error(
                        "Candidate booking WhatsApp template failed for booking %s: %s",
                        booking_id,
                        exc,
                    )
                    log_message = f"{message}\n\n[template failed: {exc}]"

        status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=booking_id,
            user_id=None,
            channel="whatsapp",
            status=status,
            title="WhatsApp confirmation",
            message=log_message,
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
        *,
        session_purpose: str | None = None,
    ) -> str:
        subject, body = _email_content(
            candidate_name,
            admin_name,
            scheduled_time,
            session_purpose=session_purpose,
        )
        email = (candidate_email or "").strip()
        if not email:
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

        sent = await asyncio.to_thread(send_email, [email], subject, body)
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

    async def send_email_admin_assignment(
        self,
        *,
        booking: CounsellingBooking,
        admin: User,
        admin_name: str,
        session_purpose: str | None = None,
    ) -> str:
        subject, body = _admin_email_content(
            admin_name,
            booking,
            session_purpose=session_purpose,
        )
        admin_email = (admin.email or "").strip()
        if not admin_email:
            self._log_attempt(
                booking_id=booking.id,
                user_id=admin.id,
                channel="email_admin",
                status="skipped",
                title=subject,
                message=body,
                priority="important",
            )
            return "skipped"

        sent = await asyncio.to_thread(send_email, [admin_email], subject, body)
        status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=booking.id,
            user_id=admin.id,
            channel="email_admin",
            status=status,
            title=subject,
            message=body,
            priority="important",
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

    async def send_whatsapp_admin_assignment(
        self,
        *,
        booking: CounsellingBooking,
        admin: User,
        admin_name: str,
        lead: Lead | None,
    ) -> str:
        """WhatsApp the assigned counsellor with a lean booking alert."""
        from app.services.admin_session_reminders import ASSIGN_TITLE
        from app.services.settings_service import get_bool_setting

        if not get_bool_setting(self.db, "ADMIN_BOOKING_ALERTS_ENABLED", True):
            return "disabled"

        message = _build_admin_assignment_whatsapp_message(
            self.db,
            admin_name=admin_name,
            booking=booking,
            lead=lead,
        )
        raw_phone = _display_value(getattr(admin, "phone_number", None))
        admin_phone = clean_phone_number(raw_phone or "") or raw_phone
        if not admin_phone:
            logger.info(
                "Skipping counsellor WhatsApp for booking %s — admin %s has no phone_number.",
                booking.id,
                admin.id,
            )
            self._log_attempt(
                booking_id=booking.id,
                user_id=admin.id,
                channel="whatsapp_admin",
                status="skipped",
                title=ASSIGN_TITLE,
                message=message,
                priority="important",
            )
            return "skipped"

        window_open = _phone_has_open_whatsapp_window(
            self.db, admin_phone, lead_id=lead.id if lead else None
        )
        sent = False
        log_message = message
        if window_open:
            sent = await send_message(admin_phone, message)
        else:
            template = (settings.WHATSAPP_ADMIN_BOOKING_TEMPLATE or "").strip()
            if not template:
                log_message = (
                    f"{message}\n\n[blocked: outside 24h WhatsApp window; "
                    "set WHATSAPP_ADMIN_BOOKING_TEMPLATE to an approved Meta UTILITY template]"
                )
                logger.warning(
                    "Counsellor WhatsApp blocked for booking %s — outside 24h window and "
                    "WHATSAPP_ADMIN_BOOKING_TEMPLATE is not configured.",
                    booking.id,
                )
            else:
                language = (
                    settings.WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE or "en"
                ).strip() or "en"
                params = [
                    OutreachTemplateParameter(_template_param(admin_name, fallback="Counsellor")),
                    OutreachTemplateParameter(
                        _template_param(booking.candidate_name, fallback="Student")
                    ),
                    OutreachTemplateParameter(
                        _template_param(_format_time(booking.scheduled_time))
                    ),
                    OutreachTemplateParameter(_template_param(booking.id)),
                ]
                try:
                    wamid = await send_whatsapp_template(
                        admin_phone,
                        template,
                        language_code=language,
                        body_parameters=params,
                    )
                    sent = True
                    log_message = f"[template:{template}] {message}\nwamid={wamid}"
                except WhatsAppDeliveryError as exc:
                    logger.error(
                        "Counsellor booking WhatsApp template failed for booking %s: %s",
                        booking.id,
                        exc,
                    )
                    log_message = f"{message}\n\n[template failed: {exc}]"

        status = "sent" if sent else "failed"
        self._log_attempt(
            booking_id=booking.id,
            user_id=admin.id,
            channel="whatsapp_admin",
            status=status,
            title=ASSIGN_TITLE,
            message=log_message,
            priority="important",
        )
        if not sent:
            logger.warning(
                "Failed to WhatsApp counsellor %s for booking %s.",
                admin.id,
                booking.id,
            )
        return status

    async def send_booking_assignment_notifications(self, booking_id: int) -> dict[str, str]:
        booking = self.db.query(CounsellingBooking).filter(CounsellingBooking.id == booking_id).first()
        if not booking or not booking.admin_id:
            raise ValueError("Assigned booking is missing an admin.")

        admin = self.db.query(User).filter(User.id == booking.admin_id).first()
        if not admin:
            raise ValueError("Assigned admin record was not found.")

        admin_name = _format_admin_name(admin)
        session_purpose = _extract_session_purpose(booking.notes)
        lead = _resolve_lead_for_booking_notification(
            self.db,
            lead_id=booking.lead_id,
            candidate_phone=booking.candidate_phone,
        )

        async def _safe(channel: str, coro) -> str:
            try:
                return await coro
            except Exception:
                logger.exception(
                    "Assignment notification channel %s failed for booking %s",
                    channel,
                    booking_id,
                )
                return "failed"

        # Candidate + counsellor each get email and WhatsApp independently.
        # Keep sequential: NotificationService shares one Session and channel
        # helpers commit notification_logs. SMTP fail-fast keeps this under
        # the Book Appointment client budget.
        whatsapp_status = await _safe(
            "whatsapp",
            self.send_whatsapp_confirmation(
                booking_id=booking.id,
                candidate_name=booking.candidate_name,
                admin_name=admin_name,
                scheduled_time=booking.scheduled_time,
                candidate_phone=booking.candidate_phone,
                lead_id=booking.lead_id,
                session_purpose=session_purpose,
            ),
        )
        email_status = await _safe(
            "email",
            self.send_email_confirmation(
                booking_id=booking.id,
                candidate_name=booking.candidate_name,
                admin_name=admin_name,
                scheduled_time=booking.scheduled_time,
                candidate_email=booking.candidate_email,
                session_purpose=session_purpose,
            ),
        )
        admin_whatsapp_status = await _safe(
            "whatsapp_admin",
            self.send_whatsapp_admin_assignment(
                booking=booking,
                admin=admin,
                admin_name=admin_name,
                lead=lead,
            ),
        )
        admin_email_status = await _safe(
            "email_admin",
            self.send_email_admin_assignment(
                booking=booking,
                admin=admin,
                admin_name=admin_name,
                session_purpose=session_purpose,
            ),
        )
        push_status = await _safe(
            "push",
            self.send_push_assignment(
                booking_id=booking.id,
                admin=admin,
                candidate_name=booking.candidate_name,
                scheduled_time=booking.scheduled_time,
            ),
        )
        try:
            _create_in_app_assignment_notification(self.db, booking=booking, admin=admin)
        except Exception:
            logger.exception("In-app assignment notification failed for booking %s", booking_id)
        return {
            "whatsapp": whatsapp_status,
            "email": email_status,
            "whatsapp_admin": admin_whatsapp_status,
            "email_admin": admin_email_status,
            "push": push_status,
        }

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
        from app.services.student_status_service import is_lead_communication_opted_out

        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if lead and is_lead_communication_opted_out(self.db, lead):
            self._log_attempt(
                booking_id=None,
                user_id=None,
                channel="whatsapp",
                status="skipped",
                title="Document Reminder",
                message=message,
                priority="important",
            )
            return False

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


# Hard ceiling for sync notification fan-out (Book Appointment waits on this).
# Must stay well under the frontend API_FETCH_TIMEOUT_MS (60s).
_ASSIGNMENT_NOTIFICATION_BUDGET_SECONDS = 35.0


def run_assignment_notifications(booking_id: int) -> dict[str, str]:
    """Send candidate/counsellor email + WhatsApp. Safe to call from BackgroundTasks."""
    failed = {
        "whatsapp": "failed",
        "email": "failed",
        "whatsapp_admin": "failed",
        "email_admin": "failed",
        "push": "failed",
    }
    db = SessionLocal()
    try:
        service = NotificationService(db)

        async def _run() -> dict[str, str]:
            return await asyncio.wait_for(
                service.send_booking_assignment_notifications(booking_id),
                timeout=_ASSIGNMENT_NOTIFICATION_BUDGET_SECONDS,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(_run())
            except TimeoutError:
                logger.error(
                    "Assignment notifications timed out after %.0fs for booking %s",
                    _ASSIGNMENT_NOTIFICATION_BUDGET_SECONDS,
                    booking_id,
                )
                return failed

        # Already inside an event loop (e.g. some ASGI contexts): run in a worker thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            try:
                return executor.submit(asyncio.run, _run()).result(
                    timeout=_ASSIGNMENT_NOTIFICATION_BUDGET_SECONDS + 5
                )
            except TimeoutError:
                logger.error(
                    "Assignment notifications timed out after %.0fs for booking %s",
                    _ASSIGNMENT_NOTIFICATION_BUDGET_SECONDS,
                    booking_id,
                )
                return failed
    except Exception:
        logger.exception("Failed to send assignment notifications for booking %s", booking_id)
        return failed
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
