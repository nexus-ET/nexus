"""Lean WhatsApp cadence for admins/counsellors: digest, nudge, and instant alerts."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.models.counselling_booking import CounsellingBooking
from app.models.notification_log import NotificationLog
from app.models.user import User
from app.services.messaging import send_message
from app.services.settings_service import get_bool_setting, get_int_setting, get_time_setting
from app.utils.timezone import office_now, office_today, utc_now

logger = logging.getLogger(__name__)

SCHEDULED_STATUS = "SCHEDULED"

CHANNEL = "whatsapp_admin"
DIGEST_TITLE_PREFIX = "Counsellor morning digest"
NUDGE_TITLE = "Counsellor session nudge"
ASSIGN_TITLE = "Counsellor booking assigned"
CANCEL_TITLE = "Counsellor booking cancelled"
RESCHEDULE_TITLE = "Counsellor booking rescheduled"


def _display(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _format_admin_name(admin: User) -> str:
    first = (admin.first_name or "").strip()
    last = (admin.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or admin.email or "Counsellor"


def _format_when(value: datetime) -> str:
    return value.strftime("%a, %b %d at %I:%M %p").lstrip("0")


def _frontend_base() -> str:
    return (settings.FRONTEND_URL or "").rstrip("/")


def booking_nexus_link(*, lead_id: int | None = None) -> str | None:
    base = _frontend_base()
    if not base:
        return None
    if lead_id:
        return f"{base}/prospects/{lead_id}"
    return f"{base}/my-bookings"


def _append_action_links(lines: list[str], *, lead_id: int | None = None) -> None:
    profile = booking_nexus_link(lead_id=lead_id)
    bookings = booking_nexus_link()
    if profile or bookings:
        lines.append("")
        lines.append("*Quick links*")
        if profile:
            lines.append(f"• View student: {profile}")
        if bookings and bookings != profile:
            lines.append(f"• Open My Appointments: {bookings}")
        elif bookings and not profile:
            lines.append(f"• Open My Appointments: {bookings}")


def build_assignment_alert_message(
    *,
    admin_name: str,
    booking: CounsellingBooking,
) -> str:
    purpose = None
    for line in str(booking.notes or "").splitlines():
        cleaned = line.strip()
        if cleaned.lower().startswith("purpose:"):
            purpose = cleaned.split(":", 1)[1].strip() or None
            break
    lines = [
        f"Hi {admin_name},",
        "New booking assigned to you.",
        "",
        f"• Student: {booking.candidate_name}",
        f"• When: {_format_when(booking.scheduled_time)}",
        f"• Booking #{booking.id}",
    ]
    if purpose:
        lines.append(f"• Purpose: {purpose}")
    if booking.candidate_phone:
        lines.append(f"• Phone: {booking.candidate_phone}")
    base = _frontend_base()
    if base:
        lines.append(f"• Session: {base}/my-bookings/session/{booking.id}")
    _append_action_links(lines, lead_id=booking.lead_id)
    return "\n".join(lines)


def build_cancel_alert_message(
    *,
    admin_name: str,
    candidate_name: str,
    scheduled_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
) -> str:
    lines = [
        f"Hi {admin_name},",
        "A session on your calendar was cancelled.",
        "",
        f"• Student: {candidate_name}",
        f"• Was scheduled: {_format_when(scheduled_time)}",
        f"• Booking #{booking_id}",
    ]
    _append_action_links(lines, lead_id=lead_id)
    return "\n".join(lines)


def build_reschedule_alert_message(
    *,
    admin_name: str,
    candidate_name: str,
    previous_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
    new_time: datetime | None = None,
) -> str:
    lines = [
        f"Hi {admin_name},",
        "A student rescheduled a session assigned to you.",
        "",
        f"• Student: {candidate_name}",
        f"• Previous slot: {_format_when(previous_time)}",
    ]
    if new_time:
        lines.append(f"• New slot: {_format_when(new_time)}")
    else:
        lines.append("• New slot: pending (student is choosing a new time)")
    lines.append(f"• Booking #{booking_id}")
    _append_action_links(lines, lead_id=lead_id)
    return "\n".join(lines)


def build_session_nudge_message(
    *,
    admin_name: str,
    booking: CounsellingBooking,
    minutes: int,
) -> str:
    lines = [
        f"Hi {admin_name},",
        f"Upcoming session with *{booking.candidate_name}* in {minutes} mins.",
        "",
        f"• When: {_format_when(booking.scheduled_time)}",
        f"• Booking #{booking.id}",
    ]
    _append_action_links(lines, lead_id=booking.lead_id)
    lines.extend(
        [
            "",
            "Wrap up your current task, review the student profile, and join on time.",
        ]
    )
    return "\n".join(lines)


def build_morning_digest_message(
    *,
    admin_name: str,
    day_label: str,
    bookings: Iterable[CounsellingBooking],
) -> str:
    items = list(bookings)
    lines = [
        f"Hi {admin_name},",
        f"Your counselling schedule for *{day_label}* ({len(items)} session"
        f"{'' if len(items) == 1 else 's'}):",
        "",
    ]
    for index, booking in enumerate(items, start=1):
        when = booking.scheduled_time.strftime("%I:%M %p").lstrip("0")
        lines.append(f"{index}. {when} — {booking.candidate_name} (#{booking.id})")
        link = booking_nexus_link(lead_id=booking.lead_id)
        if link:
            lines.append(f"   {link}")
    bookings_home = booking_nexus_link()
    if bookings_home:
        lines.extend(["", f"Open My Appointments: {bookings_home}"])
    lines.extend(
        [
            "",
            "This is your daily heads-up — individual nudges arrive 15 minutes before each session.",
        ]
    )
    return "\n".join(lines)


def _already_logged(
    db: Session,
    *,
    user_id: int,
    title: str,
    booking_id: int | None = None,
) -> bool:
    query = db.query(NotificationLog.id).filter(
        NotificationLog.user_id == user_id,
        NotificationLog.channel == CHANNEL,
        NotificationLog.title == title,
        NotificationLog.status == "sent",
    )
    if booking_id is not None:
        query = query.filter(NotificationLog.booking_id == booking_id)
    return query.first() is not None


def _log_attempt(
    db: Session,
    *,
    booking_id: int | None,
    user_id: int | None,
    status: str,
    title: str,
    message: str,
    priority: str = "important",
) -> None:
    db.add(
        NotificationLog(
            booking_id=booking_id,
            user_id=user_id,
            channel=CHANNEL,
            status=status,
            title=title,
            message=message,
            priority="urgent" if status == "failed" else priority,
            sent_at=utc_now(),
        )
    )
    db.commit()


async def _send_to_admin(
    db: Session,
    *,
    admin: User,
    message: str,
    title: str,
    booking_id: int | None = None,
    priority: str = "important",
) -> str:
    phone = _display(getattr(admin, "phone_number", None))
    if not phone:
        _log_attempt(
            db,
            booking_id=booking_id,
            user_id=admin.id,
            status="skipped",
            title=title,
            message=message,
            priority=priority,
        )
        return "skipped"

    sent = await send_message(phone, message)
    status = "sent" if sent else "failed"
    _log_attempt(
        db,
        booking_id=booking_id,
        user_id=admin.id,
        status=status,
        title=title,
        message=message,
        priority=priority,
    )
    if not sent:
        logger.warning("Failed counsellor WhatsApp (%s) to admin %s", title, admin.id)
    return status


def process_admin_morning_digests(db: Session) -> int:
    """Send one consolidated WhatsApp per counsellor for today's scheduled sessions."""
    if not get_bool_setting(db, "ADMIN_SESSION_DIGEST_ENABLED", True):
        return 0

    digest_time = get_time_setting(db, "ADMIN_SESSION_DIGEST_TIME", time(8, 0))
    now = office_now(db)
    window_start = datetime.combine(now.date(), digest_time)
    # Interval job may wake a few minutes late — allow a 5-minute send window.
    if now < window_start or now >= window_start + timedelta(minutes=5):
        return 0

    today = office_today(db)
    day_start = datetime.combine(today, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    digest_title = f"{DIGEST_TITLE_PREFIX} {today.isoformat()}"

    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.status == SCHEDULED_STATUS,
            CounsellingBooking.admin_id.isnot(None),
            CounsellingBooking.scheduled_time >= day_start,
            CounsellingBooking.scheduled_time < day_end,
        )
        .order_by(CounsellingBooking.scheduled_time.asc())
        .all()
    )
    if not bookings:
        return 0

    by_admin: dict[int, list[CounsellingBooking]] = defaultdict(list)
    for booking in bookings:
        if booking.admin_id:
            by_admin[booking.admin_id].append(booking)

    sent_count = 0
    day_label = today.strftime("%a, %b %d %Y")
    for admin_id, admin_bookings in by_admin.items():
        if _already_logged(db, user_id=admin_id, title=digest_title):
            continue
        admin = db.query(User).filter(User.id == admin_id).first()
        if not admin:
            continue
        message = build_morning_digest_message(
            admin_name=_format_admin_name(admin),
            day_label=day_label,
            bookings=admin_bookings,
        )
        status = asyncio.run(
            _send_to_admin(
                db,
                admin=admin,
                message=message,
                title=digest_title,
                booking_id=None,
                priority="normal",
            )
        )
        if status == "sent":
            sent_count += 1
    return sent_count


def process_admin_session_nudges(db: Session) -> int:
    """WhatsApp each counsellor 15 minutes (configurable) before a session."""
    if not get_bool_setting(db, "ADMIN_SESSION_NUDGE_ENABLED", True):
        return 0

    minutes = max(1, get_int_setting(db, "ADMIN_SESSION_NUDGE_MINUTES", 15))
    now = office_now(db).replace(second=0, microsecond=0)
    # Match bookings whose start falls in the next [minutes-1, minutes] window.
    window_end = now + timedelta(minutes=minutes)
    window_start = window_end - timedelta(minutes=1)

    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.status == SCHEDULED_STATUS,
            CounsellingBooking.admin_id.isnot(None),
            CounsellingBooking.scheduled_time >= window_start,
            CounsellingBooking.scheduled_time < window_end + timedelta(seconds=1),
        )
        .all()
    )

    sent_count = 0
    for booking in bookings:
        if not booking.admin_id:
            continue
        if _already_logged(db, user_id=booking.admin_id, title=NUDGE_TITLE, booking_id=booking.id):
            continue
        admin = db.query(User).filter(User.id == booking.admin_id).first()
        if not admin:
            continue
        message = build_session_nudge_message(
            admin_name=_format_admin_name(admin),
            booking=booking,
            minutes=minutes,
        )
        status = asyncio.run(
            _send_to_admin(
                db,
                admin=admin,
                message=message,
                title=NUDGE_TITLE,
                booking_id=booking.id,
                priority="important",
            )
        )
        if status == "sent":
            sent_count += 1
    return sent_count


def process_admin_session_reminder_tick() -> dict[str, int]:
    """Interval tick: morning digest window + pre-session nudges."""
    db = SessionLocal()
    try:
        digests = process_admin_morning_digests(db)
        nudges = process_admin_session_nudges(db)
        return {"digests": digests, "nudges": nudges}
    except Exception:
        logger.exception("Admin session reminder tick failed.")
        db.rollback()
        return {"digests": 0, "nudges": 0}
    finally:
        db.close()


async def send_admin_cancel_alert(
    db: Session,
    *,
    admin_id: int,
    candidate_name: str,
    scheduled_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
) -> str:
    if not get_bool_setting(db, "ADMIN_BOOKING_ALERTS_ENABLED", True):
        return "disabled"
    admin = db.query(User).filter(User.id == admin_id).first()
    if not admin:
        return "skipped"
    message = build_cancel_alert_message(
        admin_name=_format_admin_name(admin),
        candidate_name=candidate_name,
        scheduled_time=scheduled_time,
        booking_id=booking_id,
        lead_id=lead_id,
    )
    return await _send_to_admin(
        db,
        admin=admin,
        message=message,
        title=CANCEL_TITLE,
        booking_id=booking_id,
    )


async def send_admin_reschedule_alert(
    db: Session,
    *,
    admin_id: int,
    candidate_name: str,
    previous_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
    new_time: datetime | None = None,
) -> str:
    if not get_bool_setting(db, "ADMIN_BOOKING_ALERTS_ENABLED", True):
        return "disabled"
    admin = db.query(User).filter(User.id == admin_id).first()
    if not admin:
        return "skipped"
    message = build_reschedule_alert_message(
        admin_name=_format_admin_name(admin),
        candidate_name=candidate_name,
        previous_time=previous_time,
        booking_id=booking_id,
        lead_id=lead_id,
        new_time=new_time,
    )
    return await _send_to_admin(
        db,
        admin=admin,
        message=message,
        title=RESCHEDULE_TITLE,
        booking_id=booking_id,
    )


def run_admin_cancel_alert(
    *,
    admin_id: int,
    candidate_name: str,
    scheduled_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
) -> None:
    db = SessionLocal()
    try:
        asyncio.run(
            send_admin_cancel_alert(
                db,
                admin_id=admin_id,
                candidate_name=candidate_name,
                scheduled_time=scheduled_time,
                booking_id=booking_id,
                lead_id=lead_id,
            )
        )
    except Exception:
        logger.exception("Failed counsellor cancel alert for booking %s", booking_id)
    finally:
        db.close()


def run_admin_reschedule_alert(
    *,
    admin_id: int,
    candidate_name: str,
    previous_time: datetime,
    booking_id: int,
    lead_id: int | None = None,
    new_time: datetime | None = None,
) -> None:
    db = SessionLocal()
    try:
        asyncio.run(
            send_admin_reschedule_alert(
                db,
                admin_id=admin_id,
                candidate_name=candidate_name,
                previous_time=previous_time,
                booking_id=booking_id,
                lead_id=lead_id,
                new_time=new_time,
            )
        )
    except Exception:
        logger.exception("Failed counsellor reschedule alert for booking %s", booking_id)
    finally:
        db.close()


def collect_assigned_booking_snapshots_for_lead(
    db: Session,
    lead_id: int,
) -> list[dict]:
    """Capture assigned scheduled bookings before cancel/reschedule clears them."""
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead_id,
            CounsellingBooking.status == SCHEDULED_STATUS,
            CounsellingBooking.admin_id.isnot(None),
        )
        .all()
    )
    return [
        {
            "admin_id": booking.admin_id,
            "candidate_name": booking.candidate_name,
            "scheduled_time": booking.scheduled_time,
            "booking_id": booking.id,
            "lead_id": booking.lead_id,
        }
        for booking in bookings
        if booking.admin_id
    ]
