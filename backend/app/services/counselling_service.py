from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.counselling_booking import CounsellingBooking
from app.models.consultation_slot import ConsultationSlot
from app.models.lead import Lead
from app.models.message import Message
from app.models.message_history import MessageHistory
from app.models.user import User
from app.services.admin_roles import get_active_admin_role_ids
from app.services.public_holiday_service import is_bookable_day, is_public_holiday
from app.services.security_service import input_sanitizer
from app.services.settings_service import (
    get_bool_setting,
    get_int_setting,
    get_time_setting,
    is_working_day,
)
from app.utils.timezone import office_now, office_today

PENDING_STATUS = "PENDING"
SCHEDULED_STATUS = "SCHEDULED"
CANCELLED_STATUS = "CANCELLED"
COMPLETED_STATUS = "COMPLETED"
SCHEDULE_DAYS = 14
VISIBLE_PENDING_COLUMNS = 3

ADMIN_CELL_LABELS = {
    "available": "Available",
    "booked": "Booked",
    "past": "Past",
    "complete": "Complete",
}

CANDIDATE_STAGE_LABELS = {
    "AI_ACTIVE": "AI Active",
    "HANDOFF": "Handoff",
    "ARCHIVE": "Archive",
}


def _resolve_candidate_stage(lead: Lead | None) -> tuple[str | None, str | None]:
    if not lead or not lead.stage:
        return None, None
    stage_value = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage)
    label = CANDIDATE_STAGE_LABELS.get(stage_value, stage_value.replace("_", " ").title())
    return stage_value, label

HANDOFF_MARKER_PHRASES = (
    "connecting you with a human",
    "human advisor",
)


def _format_admin_name(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email


def _normalize_time(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _get_slot_minutes(db: Session) -> int:
    return get_int_setting(db, "COUNSELING_SLOT_DURATION", 30)


def _get_office_start(db: Session) -> time:
    return get_time_setting(db, "OFFICE_HOURS_START", time(9, 0))


def _get_office_end(db: Session) -> time:
    return get_time_setting(db, "OFFICE_HOURS_END", time(19, 0))


def get_max_bookings_per_slot(db: Session) -> int:
    return get_int_setting(db, "MAX_BOOKINGS_PER_SLOT", 5)


def list_whatsapp_bookable_dates(db: Session, *, limit: int = 8, days_ahead: int = 21) -> list[date]:
    """Dates that still have at least one open counselling slot in the schedule."""
    today = office_today(db)
    dates: list[date] = []
    for offset in range(1, days_ahead + 1):
        slot_day = today + timedelta(days=offset)
        if not is_bookable_day(db, slot_day):
            continue
        if get_bookable_slot_starts(db, slot_day):
            dates.append(slot_day)
        if len(dates) >= limit:
            break
    return dates


def get_bookable_slot_starts(db: Session, slot_day: date) -> list[datetime]:
    """Open counselling slot start times for WhatsApp appointment booking."""
    if not is_bookable_day(db, slot_day):
        return []

    now = office_now(db)
    max_per_slot = get_max_bookings_per_slot(db)
    range_start = datetime.combine(slot_day, _get_office_start(db))
    range_end = datetime.combine(slot_day, _get_office_end(db))

    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.scheduled_time >= range_start,
            CounsellingBooking.scheduled_time < range_end,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .all()
    )
    counts: dict[datetime, int] = {}
    for booking in bookings:
        key = _normalize_time(booking.scheduled_time)
        counts[key] = counts.get(key, 0) + 1

    available: list[datetime] = []
    for slot_start in _iter_day_slot_times(db, slot_day):
        if slot_start <= now:
            continue
        if counts.get(slot_start, 0) < max_per_slot:
            available.append(slot_start)
    return available


def _ensure_bookings_enabled(db: Session) -> None:
    if not get_bool_setting(db, "ALLOW_BOOKINGS", True):
        raise HTTPException(
            status_code=403,
            detail="New counselling bookings are currently disabled.",
        )


def _ensure_bookable_day(db: Session, scheduled: datetime) -> None:
    target = scheduled.date()
    if is_public_holiday(db, target):
        raise HTTPException(
            status_code=400,
            detail="Bookings are not available on holidays.",
        )
    if not is_working_day(db, target):
        raise HTTPException(
            status_code=400,
            detail="Bookings are not available on this day of the week.",
        )


def _iter_day_slot_times(db: Session, day: date) -> list[datetime]:
    if not is_bookable_day(db, day):
        return []
    slots: list[datetime] = []
    day_start = _get_office_start(db)
    day_end = _get_office_end(db)
    slot_minutes = _get_slot_minutes(db)
    cursor = datetime.combine(day, day_start)
    end = datetime.combine(day, day_end)
    while cursor < end:
        slots.append(cursor)
        cursor += timedelta(minutes=slot_minutes)
    return slots


def _format_day_label(day: date) -> str:
    return day.strftime("%a, %b %d")


def _format_slot_range(db: Session, start: datetime) -> str:
    end = start + timedelta(minutes=_get_slot_minutes(db))

    def _clock(value: datetime) -> str:
        hour = value.hour % 12 or 12
        return f"{hour}:{value.minute:02d}"

    return f"{_clock(start)} - {_clock(end)}"


def _appointments_count_at_time(
    db: Session,
    normalized_time: datetime,
    exclude_booking_id: int | None = None,
) -> int:
    query = db.query(CounsellingBooking).filter(
        CounsellingBooking.scheduled_time == normalized_time,
        CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
    )
    if exclude_booking_id:
        query = query.filter(CounsellingBooking.id != exclude_booking_id)
    return query.count()


def _ensure_slot_capacity(
    db: Session,
    normalized_time: datetime,
    exclude_booking_id: int | None = None,
) -> None:
    max_slots = get_max_bookings_per_slot(db)
    current = _appointments_count_at_time(db, normalized_time, exclude_booking_id)
    if current >= max_slots:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This time slot already has the maximum of {max_slots} "
                "counselling bookings."
            ),
        )


def _serialize_pending_booking(booking: CounsellingBooking) -> dict:
    return {
        "id": booking.id,
        "candidate_name": booking.candidate_name,
        "scheduled_time": booking.scheduled_time,
        "notes": booking.notes,
    }


def _build_pending_queue(pending: list[CounsellingBooking]) -> tuple[list[dict], int]:
    ordered = sorted(pending, key=lambda booking: (booking.created_at, booking.id))
    visible = ordered[:VISIBLE_PENDING_COLUMNS]
    hidden_count = max(0, len(ordered) - VISIBLE_PENDING_COLUMNS)

    queue: list[dict] = []
    for index in range(VISIBLE_PENDING_COLUMNS):
        if index < len(visible):
            queue.append(
                {
                    "queue_position": index + 1,
                    "booking": _serialize_pending_booking(visible[index]),
                }
            )
        else:
            queue.append({"queue_position": index + 1, "booking": None})

    return queue, hidden_count


def _admin_users_query(db: Session):
    role_ids = get_active_admin_role_ids(db)
    return db.query(User).filter(
        User.is_active.is_(True),
        or_(User.admin_role_id.in_(role_ids), User.is_superuser.is_(True)),
    )


def _get_admin_user(db: Session, admin_id: int) -> User:
    user = _admin_users_query(db).filter(User.id == admin_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Admin user not found.")
    return user


def _serialize_booking(booking: CounsellingBooking, admin: User | None = None) -> dict:
    return {
        "id": booking.id,
        "scheduled_time": booking.scheduled_time,
        "admin_id": booking.admin_id,
        "admin_name": _format_admin_name(admin) if admin else None,
        "candidate_name": booking.candidate_name,
        "candidate_email": booking.candidate_email,
        "candidate_phone": booking.candidate_phone,
        "status": booking.status,
        "notes": booking.notes,
    }


def _resolve_contact_fields(
    db: Session,
    candidate_email: str | None,
    candidate_phone: str | None,
    lead_id: int | None,
) -> tuple[str | None, str | None]:
    email = candidate_email
    phone = candidate_phone
    if lead_id and (not email or not phone):
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            email = email or lead.email
            phone = phone or lead.phone_number
    return email, phone


def create_pending_booking(
    db: Session,
    scheduled_time: datetime,
    candidate_name: str,
    candidate_email: str | None = None,
    candidate_phone: str | None = None,
    lead_id: int | None = None,
    notes: str | None = None,
    *,
    commit: bool = True,
) -> CounsellingBooking:
    _ensure_bookings_enabled(db)
    normalized = _normalize_time(scheduled_time)
    _ensure_bookable_day(db, normalized)
    _ensure_slot_capacity(db, normalized)
    email, phone = _resolve_contact_fields(db, candidate_email, candidate_phone, lead_id)
    sanitized_name = input_sanitizer(candidate_name) or "Candidate"
    sanitized_notes = input_sanitizer(notes) if notes else None

    booking = CounsellingBooking(
        scheduled_time=normalized,
        candidate_name=sanitized_name,
        candidate_email=email,
        candidate_phone=phone,
        lead_id=lead_id,
        admin_id=None,
        status=PENDING_STATUS,
        notes=sanitized_notes,
    )
    db.add(booking)
    if commit:
        db.commit()
        db.refresh(booking)
    return booking


def cancel_active_counselling_bookings_for_lead(db: Session, lead_id: int, *, commit: bool = True) -> None:
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead_id,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .all()
    )
    for booking in bookings:
        booking.status = CANCELLED_STATUS
        booking.updated_at = datetime.utcnow()
    if commit and bookings:
        db.commit()


def upsert_pending_booking_for_lead(
    db: Session,
    lead: Lead,
    scheduled_time: datetime,
    *,
    commit: bool = True,
) -> CounsellingBooking:
    normalized = _normalize_time(scheduled_time)
    email, phone = _resolve_contact_fields(db, lead.email, lead.phone_number, lead.id)
    candidate_name = (lead.full_name or "Candidate").strip()

    existing = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead.id,
            CounsellingBooking.admin_id.is_(None),
            CounsellingBooking.status == PENDING_STATUS,
        )
        .first()
    )
    if existing:
        if _normalize_time(existing.scheduled_time) != normalized:
            _ensure_bookable_day(db, normalized)
            _ensure_slot_capacity(db, normalized, exclude_booking_id=existing.id)
        existing.scheduled_time = normalized
        existing.candidate_name = candidate_name
        existing.candidate_email = email
        existing.candidate_phone = phone
        existing.updated_at = datetime.utcnow()
        if commit:
            db.commit()
            db.refresh(existing)
        return existing

    _ensure_bookable_day(db, normalized)
    _ensure_slot_capacity(db, normalized)
    return create_pending_booking(
        db,
        normalized,
        candidate_name,
        email,
        phone,
        lead.id,
        commit=commit,
    )


def sync_pending_bookings_from_leads(db: Session) -> int:
    """Backfill counselling_bookings from WhatsApp intake lead appointments."""
    today = office_today(db)
    leads = (
        db.query(Lead)
        .filter(
            Lead.consultation_scheduled_at.isnot(None),
            Lead.consultation_scheduled_at >= datetime.combine(today, datetime.min.time()),
        )
        .all()
    )
    created = 0
    updated = 0
    for lead in leads:
        if not lead.consultation_scheduled_at:
            continue
        active = (
            db.query(CounsellingBooking)
            .filter(
                CounsellingBooking.lead_id == lead.id,
                CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
            )
            .first()
        )
        if active:
            if (
                active.admin_id is None
                and active.status == PENDING_STATUS
                and active.scheduled_time != _normalize_time(lead.consultation_scheduled_at)
            ):
                active.scheduled_time = _normalize_time(lead.consultation_scheduled_at)
                active.updated_at = datetime.utcnow()
                updated += 1
            continue

        upsert_pending_booking_for_lead(db, lead, lead.consultation_scheduled_at, commit=False)
        created += 1

    if created or updated:
        db.commit()
    return created + updated


def get_pending_bookings(db: Session) -> dict:
    sync_pending_bookings_from_leads(db)

    today = office_today(db)
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.admin_id.is_(None),
            CounsellingBooking.status == PENDING_STATUS,
            CounsellingBooking.scheduled_time >= datetime.combine(today, datetime.min.time()),
        )
        .order_by(CounsellingBooking.scheduled_time.asc())
        .all()
    )

    today_items: list[dict] = []
    upcoming_map: dict[date, list[dict]] = {}

    for booking in bookings:
        payload = {
            "id": booking.id,
            "scheduled_time": booking.scheduled_time,
            "candidate_name": booking.candidate_name,
            "candidate_email": booking.candidate_email,
            "candidate_phone": booking.candidate_phone,
            "notes": booking.notes,
            "status": booking.status,
        }
        booking_date = booking.scheduled_time.date()
        if booking_date == today:
            today_items.append(payload)
        else:
            upcoming_map.setdefault(booking_date, []).append(payload)

    upcoming = [
        {
            "date": booking_date,
            "label": booking_date.strftime("%a, %b %d"),
            "bookings": items,
        }
        for booking_date, items in sorted(upcoming_map.items(), key=lambda item: item[0])
    ]

    return {"today": today_items, "upcoming": upcoming}


def _collect_schedule_dates(db: Session, today: date) -> list[date]:
    end_day = today + timedelta(days=SCHEDULE_DAYS - 1)
    range_start = datetime.combine(today, _get_office_start(db))
    range_end = datetime.combine(end_day, _get_office_end(db))

    booking_dates = {
        row[0]
        for row in db.query(CounsellingBooking.scheduled_time)
        .filter(
            CounsellingBooking.scheduled_time >= range_start,
            CounsellingBooking.scheduled_time < range_end,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .all()
        if row[0] is not None
    }

    dates = {_normalize_time(value).date() for value in booking_dates}
    if not dates:
        dates = {today}
    return sorted(dates)


def _resolve_day_section(target_date: date, focus_date: date) -> str:
    if target_date < focus_date:
        return "past"
    if target_date > focus_date:
        return "upcoming"
    return "selected"


def _build_day_grid(db: Session, target_date: date, focus_date: date) -> dict:
    admins = (
        _admin_users_query(db)
        .order_by(User.first_name.asc(), User.last_name.asc(), User.email.asc())
        .all()
    )
    range_start = datetime.combine(target_date, _get_office_start(db))
    range_end = datetime.combine(target_date, _get_office_end(db))

    day_bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.scheduled_time >= range_start,
            CounsellingBooking.scheduled_time < range_end,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS, COMPLETED_STATUS]),
        )
        .all()
    )

    bookings_by_time: dict[datetime, list[CounsellingBooking]] = {}
    for booking in day_bookings:
        key = _normalize_time(booking.scheduled_time)
        bookings_by_time.setdefault(key, []).append(booking)

    now = office_now(db)
    rows: list[dict] = []

    for slot_start in _iter_day_slot_times(db, target_date):
        slot_bookings = bookings_by_time.get(slot_start, [])
        pending = [
            booking
            for booking in slot_bookings
            if booking.admin_id is None and booking.status == PENDING_STATUS
        ]
        pending.sort(key=lambda booking: (booking.created_at, booking.id))
        pending_queue, hidden_pending_count = _build_pending_queue(pending)
        scheduled_by_admin = {
            booking.admin_id: booking
            for booking in slot_bookings
            if booking.admin_id is not None
            and booking.status in (SCHEDULED_STATUS, COMPLETED_STATUS)
        }

        admin_cells: list[dict] = []
        for admin in admins:
            scheduled = scheduled_by_admin.get(admin.id)
            if scheduled and scheduled.status == COMPLETED_STATUS:
                status = "complete"
                candidate_name = scheduled.candidate_name
                booking_id = scheduled.id
            elif slot_start < now:
                if scheduled:
                    status = "complete"
                    candidate_name = scheduled.candidate_name
                    booking_id = scheduled.id
                else:
                    status = "past"
                    candidate_name = None
                    booking_id = None
            elif scheduled:
                status = "booked"
                candidate_name = scheduled.candidate_name
                booking_id = scheduled.id
            else:
                status = "available"
                candidate_name = None
                booking_id = None

            admin_cells.append(
                {
                    "admin_id": admin.id,
                    "status": status,
                    "label": ADMIN_CELL_LABELS[status],
                    "candidate_name": candidate_name,
                    "booking_id": booking_id,
                }
            )

        rows.append(
            {
                "start_time": slot_start,
                "time_label": _format_slot_range(db, slot_start),
                "pending_queue": pending_queue,
                "hidden_pending_count": hidden_pending_count,
                "admin_cells": admin_cells,
            }
        )

    return {
        "date": target_date,
        "label": _format_day_label(target_date),
        "section": _resolve_day_section(target_date, focus_date),
        "admins": [{"id": admin.id, "name": _format_admin_name(admin)} for admin in admins],
        "rows": rows,
    }


def get_schedule_grid(db: Session, focus_date: date | None = None) -> dict:
    sync_pending_bookings_from_leads(db)
    selected = focus_date or office_today(db)
    past_date = selected - timedelta(days=1)
    upcoming_date = selected + timedelta(days=1)
    calendar_today = office_today(db)

    return {
        "days": [_build_day_grid(db, selected, selected)],
        "legend": ADMIN_CELL_LABELS,
        "max_bookings_per_slot": get_max_bookings_per_slot(db),
        "visible_pending_columns": VISIBLE_PENDING_COLUMNS,
        "focus_date": selected,
        "calendar_today": calendar_today,
        "navigation": {
            "past": {"date": past_date, "label": _format_day_label(past_date)},
            "selected": {"date": selected, "label": _format_day_label(selected)},
            "upcoming": {"date": upcoming_date, "label": _format_day_label(upcoming_date)},
        },
    }


def get_available_admins(
    db: Session,
    timestamp: datetime,
    exclude_booking_id: int | None = None,
    exclude_admin_id: int | None = None,
) -> dict:
    normalized = _normalize_time(timestamp)
    busy_query = db.query(CounsellingBooking.admin_id).filter(
        CounsellingBooking.admin_id.isnot(None),
        CounsellingBooking.status == SCHEDULED_STATUS,
        CounsellingBooking.scheduled_time == normalized,
    )
    if exclude_booking_id:
        busy_query = busy_query.filter(CounsellingBooking.id != exclude_booking_id)

    busy_admin_ids = {row[0] for row in busy_query.all() if row[0] is not None}
    if exclude_admin_id:
        busy_admin_ids.add(exclude_admin_id)

    admins = (
        _admin_users_query(db)
        .filter(User.id.notin_(busy_admin_ids) if busy_admin_ids else True)
        .order_by(User.first_name.asc(), User.last_name.asc(), User.email.asc())
        .all()
    )

    return {
        "time": normalized,
        "admins": [
            {"id": admin.id, "name": _format_admin_name(admin), "email": admin.email}
            for admin in admins
        ],
    }


def _serialize_my_booking(
    db: Session,
    booking: CounsellingBooking,
    admin: User | None,
    section: str,
) -> dict:
    payload = _serialize_booking(booking, admin)
    scheduled = booking.scheduled_time
    lead = None
    if booking.lead_id:
        lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
    candidate_stage, candidate_stage_label = _resolve_candidate_stage(lead)
    return {
        **payload,
        "lead_id": booking.lead_id,
        "candidate_stage": candidate_stage,
        "candidate_stage_label": candidate_stage_label,
        "time_label": _format_slot_range(db, scheduled),
        "date_label": _format_day_label(scheduled.date()),
        "section": section,
    }


def get_my_bookings(db: Session, user_id: int) -> dict:
    calendar_today = office_today(db)
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.admin_id == user_id,
            CounsellingBooking.status == SCHEDULED_STATUS,
        )
        .order_by(CounsellingBooking.scheduled_time.asc())
        .all()
    )

    admin_cache: dict[int, User | None] = {}
    past: list[dict] = []
    today: list[dict] = []
    upcoming: list[dict] = []

    for booking in bookings:
        if booking.admin_id not in admin_cache:
            admin_cache[booking.admin_id] = (
                db.query(User).filter(User.id == booking.admin_id).first()
                if booking.admin_id
                else None
            )
        admin = admin_cache.get(booking.admin_id)
        booking_date = booking.scheduled_time.date()
        if booking_date < calendar_today:
            section = "past"
        elif booking_date > calendar_today:
            section = "upcoming"
        else:
            section = "today"

        payload = _serialize_my_booking(db, booking, admin, section)
        if section == "past":
            past.append(payload)
        elif section == "today":
            today.append(payload)
        else:
            upcoming.append(payload)

    past.sort(key=lambda item: item["scheduled_time"], reverse=True)

    return {
        "past": past,
        "today": today,
        "upcoming": upcoming,
        "calendar_today": calendar_today,
        "total_count": len(bookings),
    }


def reassign_my_booking(
    db: Session,
    user_id: int,
    booking_id: int,
    target_admin_id: int,
) -> CounsellingBooking:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id, CounsellingBooking.status == SCHEDULED_STATUS)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found.")
    if booking.admin_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only reassign bookings assigned to you.",
        )

    available = get_available_admins(
        db,
        booking.scheduled_time,
        exclude_booking_id=booking.id,
        exclude_admin_id=user_id,
    )
    allowed_ids = {admin["id"] for admin in available["admins"]}
    if target_admin_id not in allowed_ids:
        raise HTTPException(
            status_code=409,
            detail="Selected admin is not available for this appointment slot.",
        )

    return switch_booking_admin(db, booking_id, target_admin_id)


def assign_booking(db: Session, booking_id: int, admin_id: int) -> CounsellingBooking:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id)
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.admin_id is not None and booking.status == SCHEDULED_STATUS:
        raise HTTPException(status_code=400, detail="Booking is already assigned.")
    if booking.status == CANCELLED_STATUS:
        raise HTTPException(status_code=400, detail="Cancelled bookings cannot be assigned.")

    admin = _get_admin_user(db, admin_id)
    normalized = _normalize_time(booking.scheduled_time)

    conflict = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.id != booking.id,
            CounsellingBooking.admin_id == admin.id,
            CounsellingBooking.status == SCHEDULED_STATUS,
            CounsellingBooking.scheduled_time == normalized,
        )
        .with_for_update()
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="Selected admin already has a booking at this time.",
        )

    try:
        booking.admin_id = admin.id
        booking.status = SCHEDULED_STATUS
        booking.updated_at = datetime.utcnow()
        if booking.lead_id:
            lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
            if lead and not lead.admission_stage:
                lead.admission_stage = "COUNSELLING"
                lead.admission_stage_entered_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    except Exception:
        db.rollback()
        raise


def cancel_booking(db: Session, booking_id: int) -> CounsellingBooking:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id)
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status == CANCELLED_STATUS:
        raise HTTPException(status_code=400, detail="Booking is already cancelled.")

    if booking.lead_id:
        lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
        if lead:
            slot = db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).first()
            if slot:
                slot.lead_id = None
            lead.consultation_scheduled_at = None
            lead.calendar_booking_id = None

    booking.status = CANCELLED_STATUS
    booking.admin_id = None
    booking.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return booking


def switch_booking_admin(
    db: Session,
    booking_id: int,
    target_admin_id: int,
) -> CounsellingBooking:
    if target_admin_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid target admin.")

    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id, CounsellingBooking.status == SCHEDULED_STATUS)
        .with_for_update()
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Active booking not found.")
    if not booking.admin_id:
        raise HTTPException(status_code=400, detail="Booking is not assigned to an admin.")

    target_admin = _get_admin_user(db, target_admin_id)
    if target_admin.id == booking.admin_id:
        raise HTTPException(status_code=400, detail="Booking is already assigned to this admin.")

    normalized = _normalize_time(booking.scheduled_time)
    conflict = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.id != booking.id,
            CounsellingBooking.admin_id == target_admin.id,
            CounsellingBooking.status == SCHEDULED_STATUS,
            CounsellingBooking.scheduled_time == normalized,
        )
        .with_for_update()
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="Target admin already has a booking at this time.",
        )

    try:
        booking.admin_id = target_admin.id
        booking.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(booking)
        return booking
    except Exception:
        db.rollback()
        raise


def get_booking_with_admin(db: Session, booking_id: int) -> tuple[CounsellingBooking, User | None]:
    booking = db.query(CounsellingBooking).filter(CounsellingBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    admin = None
    if booking.admin_id:
        admin = db.query(User).filter(User.id == booking.admin_id).first()
    return booking, admin


def _normalize_message_text(text: str | None) -> str:
    return " ".join((text or "").split()).strip().lower()


def _resolve_handoff_admin_name(
    db: Session,
    booking: CounsellingBooking,
    lead: Lead | None,
) -> str:
    if booking.admin_id:
        admin = db.query(User).filter(User.id == booking.admin_id).first()
        if admin:
            return _format_admin_name(admin)

    if lead and lead.assigned_advisor_id:
        assigned = db.query(User).filter(User.id == lead.assigned_advisor_id).first()
        if assigned:
            return _format_admin_name(assigned)

    return "Handoff Admin"


def _classify_advisor_message(
    *,
    text: str,
    handoff_started: bool,
    ai_texts: set[str],
) -> tuple[str, bool]:
    lower_text = text.lower()
    if any(marker in lower_text for marker in HANDOFF_MARKER_PHRASES):
        return "ai_agent", True

    if not handoff_started:
        return "ai_agent", handoff_started

    if _normalize_message_text(text) in ai_texts:
        return "ai_agent", handoff_started

    return "handoff_admin", handoff_started


def get_booking_communications(db: Session, booking_id: int) -> dict:
    booking, assigned_admin = get_booking_with_admin(db, booking_id)
    lead = None
    if booking.lead_id:
        lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()

    candidate_name = booking.candidate_name
    handoff_admin_name = _resolve_handoff_admin_name(db, booking, lead)
    admin_name = _format_admin_name(assigned_admin) if assigned_admin else handoff_admin_name

    if not lead:
        return {
            "booking_id": booking.id,
            "lead_id": None,
            "candidate_name": candidate_name,
            "candidate_email": booking.candidate_email,
            "candidate_phone": booking.candidate_phone,
            "candidate_stage": None,
            "candidate_stage_label": None,
            "admin_name": admin_name,
            "message_count": 0,
            "messages": [],
        }

    messages = (
        db.query(Message)
        .filter(Message.lead_id == lead.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    history_rows = (
        db.query(MessageHistory)
        .filter(MessageHistory.lead_id == lead.id)
        .order_by(MessageHistory.created_at.asc(), MessageHistory.id.asc())
        .all()
    )
    ai_texts = {
        _normalize_message_text(row.message_text)
        for row in history_rows
        if row.role == "ai" and row.message_text
    }

    serialized: list[dict] = []
    seen_message_keys: set[tuple[str, str]] = set()
    handoff_started = False

    def append_message(
        *,
        message_id: int | str,
        participant: str,
        participant_label: str,
        text: str,
        created_at: datetime | None,
        media_url: str | None = None,
        file_name: str | None = None,
    ) -> None:
        clean_text = text or ""
        timestamp = created_at or datetime.utcnow()
        dedupe_key = (_normalize_message_text(clean_text), timestamp.isoformat())
        if clean_text and dedupe_key in seen_message_keys:
            return
        if clean_text:
            seen_message_keys.add(dedupe_key)

        serialized.append(
            {
                "id": message_id,
                "participant": participant,
                "participant_label": participant_label,
                "text": clean_text,
                "created_at": timestamp,
                "media_url": media_url,
                "file_name": file_name,
            }
        )

    for message in messages:
        text = message.text or ""
        if message.sender in ("candidate", "student"):
            append_message(
                message_id=message.id,
                participant="candidate",
                participant_label=lead.full_name or candidate_name,
                text=text,
                created_at=message.created_at,
                media_url=message.media_url,
                file_name=message.file_name,
            )
            continue

        if message.sender == "system":
            append_message(
                message_id=message.id,
                participant="system",
                participant_label="System",
                text=text,
                created_at=message.created_at,
                media_url=message.media_url,
                file_name=message.file_name,
            )
            continue

        if message.sender == "advisor":
            participant, handoff_started = _classify_advisor_message(
                text=text,
                handoff_started=handoff_started,
                ai_texts=ai_texts,
            )
            participant_label = "AI Agent" if participant == "ai_agent" else handoff_admin_name
            append_message(
                message_id=message.id,
                participant=participant,
                participant_label=participant_label,
                text=text,
                created_at=message.created_at,
                media_url=message.media_url,
                file_name=message.file_name,
            )

    for row in history_rows:
        if row.role == "user":
            append_message(
                message_id=f"history-user-{row.id}",
                participant="candidate",
                participant_label=lead.full_name or candidate_name,
                text=row.message_text,
                created_at=row.created_at,
            )
        elif row.role == "ai":
            append_message(
                message_id=f"history-ai-{row.id}",
                participant="ai_agent",
                participant_label="AI Agent",
                text=row.message_text,
                created_at=row.created_at,
            )

    serialized.sort(key=lambda item: (item["created_at"], str(item["id"])))
    candidate_stage, candidate_stage_label = _resolve_candidate_stage(lead)

    return {
        "booking_id": booking.id,
        "lead_id": lead.id,
        "candidate_name": candidate_name,
        "candidate_email": booking.candidate_email or lead.email,
        "candidate_phone": booking.candidate_phone or lead.phone_number,
        "candidate_stage": candidate_stage,
        "candidate_stage_label": candidate_stage_label,
        "admin_name": admin_name,
        "message_count": len(serialized),
        "messages": serialized,
    }


def get_my_booking_communications(db: Session, user_id: int, booking_id: int) -> dict:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id, CounsellingBooking.admin_id == user_id)
        .first()
    )
    if not booking:
        raise HTTPException(
            status_code=404,
            detail="Booking not found or not assigned to you.",
        )
    return get_booking_communications(db, booking_id)
