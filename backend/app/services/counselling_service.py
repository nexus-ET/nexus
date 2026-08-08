from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.counselling_booking import CounsellingBooking
from app.models.counselling_note import CounsellingNote
from app.models.consultation_slot import ConsultationSlot
from app.models.lead import Lead
from app.models.message import Message
from app.models.message_history import MessageHistory
from app.models.status_definition import StatusDefinition
from app.models.user import User
from app.services.candidate_profile_service import build_candidate_profile
from app.services.lead_study_interest import resolve_lead_study_interest
from app.services.pipeline_service import OUTCOME_CONFIG
from app.services.status_definition_service import (
    STATUS_COUNSELLING_FOLLOW_UP,
    STATUS_COUNSELLING_SCHEDULED,
    apply_lead_status,
    get_lead_status_history,
    get_status_definition,
    list_status_definitions,
    resolve_lead_status_meta,
)
from app.services.status_transition_service import get_valid_transitions, is_backward_transition
from app.services.admin_roles import get_active_admin_role_ids
from app.services.public_holiday_service import is_bookable_day, is_public_holiday
from app.services.security_service import input_sanitizer
from app.services.settings_service import (
    get_bool_setting,
    get_int_setting,
    get_setting,
    get_time_setting,
    is_working_day,
)
from app.utils.timezone import office_now, office_today, utc_now

PENDING_STATUS = "PENDING"
SCHEDULED_STATUS = "SCHEDULED"
CANCELLED_STATUS = "CANCELLED"
COMPLETED_STATUS = "COMPLETED"
SCHEDULE_DAYS = 14
VISIBLE_PENDING_COLUMNS = 3
MAX_SCHEDULE_GRID_RANGE_DAYS = 31
MY_BOOKINGS_ADMIN_ROLE_NAMES = {"Super Admin", "Web Admin"}

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


def _iter_office_slot_times(db: Session, day: date) -> list[datetime]:
    """Office-hour slot starts for a calendar day (ignores holidays / working-day rules)."""
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


def _iter_day_slot_times(db: Session, day: date) -> list[datetime]:
    if not is_bookable_day(db, day):
        return []
    return _iter_office_slot_times(db, day)


def _day_closure_reason(db: Session, day: date) -> str | None:
    if is_public_holiday(db, day):
        return "holiday"
    if not is_working_day(db, day):
        return "weekend"
    return None


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
        "lead_id": booking.lead_id,
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


def cancel_active_counselling_bookings_for_lead(
    db: Session,
    lead_id: int,
    *,
    commit: bool = True,
    alert_reason: str = "cancelled",
) -> list[dict]:
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead_id,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .all()
    )
    alert_snapshots: list[dict] = []
    for booking in bookings:
        if booking.admin_id and booking.status == SCHEDULED_STATUS:
            alert_snapshots.append(
                {
                    "admin_id": booking.admin_id,
                    "candidate_name": booking.candidate_name,
                    "scheduled_time": booking.scheduled_time,
                    "booking_id": booking.id,
                    "lead_id": booking.lead_id,
                    "alert_reason": alert_reason,
                }
            )
        booking.status = CANCELLED_STATUS
        booking.updated_at = utc_now()
    if commit and bookings:
        db.commit()
    return alert_snapshots


def dispatch_admin_booking_release_alerts(snapshots: list[dict]) -> None:
    """Fire cancel/reschedule WhatsApp alerts after bookings are released."""
    if not snapshots:
        return
    from app.services.admin_session_reminders import (
        run_admin_cancel_alert,
        run_admin_reschedule_alert,
    )

    for snapshot in snapshots:
        reason = snapshot.pop("alert_reason", "cancelled")
        if reason == "rescheduled":
            run_admin_reschedule_alert(
                admin_id=snapshot["admin_id"],
                candidate_name=snapshot["candidate_name"],
                previous_time=snapshot["scheduled_time"],
                booking_id=snapshot["booking_id"],
                lead_id=snapshot.get("lead_id"),
            )
        else:
            run_admin_cancel_alert(
                admin_id=snapshot["admin_id"],
                candidate_name=snapshot["candidate_name"],
                scheduled_time=snapshot["scheduled_time"],
                booking_id=snapshot["booking_id"],
                lead_id=snapshot.get("lead_id"),
            )


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
        existing.updated_at = utc_now()
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
                active.updated_at = utc_now()
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
            "lead_id": booking.lead_id,
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
                lead_id = scheduled.lead_id
            elif slot_start < now:
                if scheduled:
                    status = "complete"
                    candidate_name = scheduled.candidate_name
                    booking_id = scheduled.id
                    lead_id = scheduled.lead_id
                else:
                    status = "past"
                    candidate_name = None
                    booking_id = None
                    lead_id = None
            elif scheduled:
                status = "booked"
                candidate_name = scheduled.candidate_name
                booking_id = scheduled.id
                lead_id = scheduled.lead_id
            else:
                status = "available"
                candidate_name = None
                booking_id = None
                lead_id = None

            admin_cells.append(
                {
                    "admin_id": admin.id,
                    "admin_name": _format_admin_name(admin),
                    "status": status,
                    "label": ADMIN_CELL_LABELS[status],
                    "candidate_name": candidate_name,
                    "booking_id": booking_id,
                    "lead_id": lead_id,
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


def get_schedule_grid(
    db: Session,
    focus_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    sync_pending_bookings_from_leads(db)
    calendar_today = office_today(db)

    if start_date is not None or end_date is not None:
        range_start = start_date or end_date
        range_end = end_date or start_date
        assert range_start is not None and range_end is not None
        if range_start > range_end:
            range_start, range_end = range_end, range_start
        day_count = (range_end - range_start).days + 1
        if day_count > MAX_SCHEDULE_GRID_RANGE_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"Date period cannot exceed {MAX_SCHEDULE_GRID_RANGE_DAYS} days.",
            )
        days = []
        current = range_start
        while current <= range_end:
            days.append(_build_day_grid(db, current, range_start))
            current += timedelta(days=1)
        selected = range_start
        past_date = selected - timedelta(days=1)
        upcoming_date = selected + timedelta(days=1)
        return {
            "days": days,
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

    selected = focus_date or calendar_today
    past_date = selected - timedelta(days=1)
    upcoming_date = selected + timedelta(days=1)

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


DEFAULT_SESSION_PURPOSES: tuple[tuple[str, str], ...] = (
    ("General Counselling", "Initial study-abroad guidance, goals, and pathway overview"),
    ("Visa Application Help", "Visa forms, evidence checklist, and interview prep support"),
    ("Documentation", "Collecting, reviewing, and organizing application documents"),
    ("University Shortlisting", "Matching destinations, institutions, and programs"),
    ("Test Prep Guidance", "IELTS/TOEFL/GRE/GMAT planning and score targets"),
    ("Application Review", "Application drafts, essays, and submission readiness"),
)


def get_session_purposes(db: Session) -> list[dict[str, str]]:
    default_raw = "\n".join(
        f"{label} | {description}" for label, description in DEFAULT_SESSION_PURPOSES
    )
    raw = get_setting("COUNSELING_SESSION_PURPOSES", default_raw, db=db) or ""
    purposes: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in raw.replace(",", "\n").splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if "|" in cleaned:
            label_part, desc_part = cleaned.split("|", 1)
            label = label_part.strip()
            description = desc_part.strip()
        else:
            label = cleaned
            description = ""
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        if not description:
            description = next(
                (item[1] for item in DEFAULT_SESSION_PURPOSES if item[0].casefold() == key),
                "Counselling session category",
            )
        purposes.append({"label": label, "description": description})
    if purposes:
        return purposes
    return [{"label": label, "description": description} for label, description in DEFAULT_SESSION_PURPOSES]


def get_booking_session_config(db: Session) -> dict:
    start = _get_office_start(db)
    end = _get_office_end(db)
    return {
        "slot_duration_minutes": _get_slot_minutes(db),
        "purposes": get_session_purposes(db),
        "office_hours_start": start.strftime("%H:%M"),
        "office_hours_end": end.strftime("%H:%M"),
        "allow_bookings": get_bool_setting(db, "ALLOW_BOOKINGS", True),
    }


def list_counsellors(db: Session) -> list[dict]:
    admins = (
        _admin_users_query(db)
        .order_by(User.first_name.asc(), User.last_name.asc(), User.email.asc())
        .all()
    )
    return [
        {"id": admin.id, "name": _format_admin_name(admin), "email": admin.email}
        for admin in admins
    ]


def get_counsellor_availability(db: Session, admin_id: int, slot_day: date) -> dict:
    admin = _get_admin_user(db, admin_id)
    duration = _get_slot_minutes(db)
    closure_reason = _day_closure_reason(db, slot_day)
    day_status = closure_reason or "open"
    office_slots = _iter_office_slot_times(db, slot_day)

    if closure_reason:
        return {
            "date": slot_day,
            "admin_id": admin.id,
            "slot_duration_minutes": duration,
            "day_status": day_status,
            "bookable": False,
            "slots": [
                {
                    "start": slot_start,
                    "label": _format_slot_range(db, slot_start),
                    "available": False,
                    "reason": closure_reason,
                    "booking_id": None,
                    "candidate_name": None,
                    "lead_id": None,
                }
                for slot_start in office_slots
            ],
        }

    now = office_now(db)
    max_per_slot = get_max_bookings_per_slot(db)
    range_start = datetime.combine(slot_day, _get_office_start(db))
    range_end = datetime.combine(slot_day, _get_office_end(db))

    day_bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.scheduled_time >= range_start,
            CounsellingBooking.scheduled_time < range_end,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .all()
    )

    counts: dict[datetime, int] = {}
    counsellor_busy: dict[datetime, CounsellingBooking] = {}
    for booking in day_bookings:
        key = _normalize_time(booking.scheduled_time)
        counts[key] = counts.get(key, 0) + 1
        if booking.admin_id == admin.id and booking.status == SCHEDULED_STATUS:
            counsellor_busy[key] = booking

    slots: list[dict] = []
    for slot_start in office_slots:
        if slot_start <= now:
            slots.append(
                {
                    "start": slot_start,
                    "label": _format_slot_range(db, slot_start),
                    "available": False,
                    "reason": "past",
                    "booking_id": None,
                    "candidate_name": None,
                    "lead_id": None,
                }
            )
            continue
        busy_booking = counsellor_busy.get(slot_start)
        if busy_booking is not None:
            slots.append(
                {
                    "start": slot_start,
                    "label": _format_slot_range(db, slot_start),
                    "available": False,
                    "reason": "counsellor_busy",
                    "booking_id": busy_booking.id,
                    "candidate_name": busy_booking.candidate_name,
                    "lead_id": busy_booking.lead_id,
                }
            )
            continue
        if counts.get(slot_start, 0) >= max_per_slot:
            slots.append(
                {
                    "start": slot_start,
                    "label": _format_slot_range(db, slot_start),
                    "available": False,
                    "reason": "slot_full",
                    "booking_id": None,
                    "candidate_name": None,
                    "lead_id": None,
                }
            )
            continue
        slots.append(
            {
                "start": slot_start,
                "label": _format_slot_range(db, slot_start),
                "available": True,
                "reason": None,
                "booking_id": None,
                "candidate_name": None,
                "lead_id": None,
            }
        )

    return {
        "date": slot_day,
        "admin_id": admin.id,
        "slot_duration_minutes": duration,
        "day_status": day_status,
        "bookable": True,
        "slots": slots,
    }


def get_counsellor_availability_week(
    db: Session,
    admin_id: int,
    start_date: date,
    *,
    days: int = 7,
) -> dict:
    admin = _get_admin_user(db, admin_id)
    safe_days = max(1, min(int(days), 14))
    day_payloads = [
        get_counsellor_availability(db, admin.id, start_date + timedelta(days=offset))
        for offset in range(safe_days)
    ]
    return {
        "admin_id": admin.id,
        "start_date": start_date,
        "days": day_payloads,
        "slot_duration_minutes": _get_slot_minutes(db),
    }


def check_booking_contact_duplicates(
    db: Session,
    *,
    email: str | None,
    phone: str | None,
    exclude_lead_id: int | None = None,
) -> dict:
    email_taken = False
    phone_taken = False
    email_lead_id: int | None = None
    phone_lead_id: int | None = None

    normalized_email = (email or "").strip().lower()
    if normalized_email:
        email_query = db.query(Lead).filter(Lead.email == normalized_email)
        if exclude_lead_id:
            email_query = email_query.filter(Lead.id != exclude_lead_id)
        email_lead = email_query.first()
        if email_lead:
            email_taken = True
            email_lead_id = email_lead.id

    normalized_phone = (phone or "").strip()
    if normalized_phone:
        phone_query = db.query(Lead).filter(Lead.phone_number == normalized_phone)
        if exclude_lead_id:
            phone_query = phone_query.filter(Lead.id != exclude_lead_id)
        phone_lead = phone_query.first()
        if phone_lead:
            phone_taken = True
            phone_lead_id = phone_lead.id

    return {
        "email_taken": email_taken,
        "phone_taken": phone_taken,
        "email_lead_id": email_lead_id,
        "phone_lead_id": phone_lead_id,
    }


def create_booking_candidate_lead(
    db: Session,
    *,
    candidate_name: str,
    candidate_email: str | None,
    candidate_phone: str | None,
    commit: bool = False,
) -> Lead:
    """Create a minimal Offline lead for staff Book Appointment (new candidate)."""
    from app.models.lead import LeadChannel, LeadStage
    from app.services.student_status_service import on_lead_created

    sanitized_name = input_sanitizer(candidate_name) or "Candidate"
    email = (candidate_email or "").strip().lower() or None
    phone = (candidate_phone or "").strip() or None
    if not email and not phone:
        raise HTTPException(
            status_code=400,
            detail="Email or phone is required to create a new candidate lead.",
        )

    duplicates = check_booking_contact_duplicates(db, email=email, phone=phone)
    if duplicates["email_taken"]:
        raise HTTPException(
            status_code=409,
            detail="A registered user already exists with this email. Select the existing candidate instead.",
        )
    if duplicates["phone_taken"]:
        raise HTTPException(
            status_code=409,
            detail="A registered user already exists with this phone number. Select the existing candidate instead.",
        )

    lead = Lead(
        full_name=sanitized_name,
        email=email,
        phone_number=phone,
        channel=LeadChannel.OFFLINE,
        source="book_appointment",
        stage=LeadStage.HANDOFF,
        is_human_locked=True,
        admission_stage="COUNSELLING",
        admission_stage_entered_at=utc_now(),
    )
    db.add(lead)
    db.flush()
    on_lead_created(db, lead, source="Book Appointment")
    if commit:
        db.commit()
        db.refresh(lead)
    return lead


def _compose_booking_notes(session_purpose: str | None, notes: str | None) -> str | None:
    purpose = (session_purpose or "").strip()
    body = (notes or "").strip()
    if purpose and body:
        return f"Purpose: {purpose}\n{body}"
    if purpose:
        return f"Purpose: {purpose}"
    return body or None


def create_staff_booking(
    db: Session,
    scheduled_time: datetime,
    admin_id: int,
    candidate_name: str,
    candidate_email: str | None = None,
    candidate_phone: str | None = None,
    lead_id: int | None = None,
    session_purpose: str | None = None,
    notes: str | None = None,
    *,
    create_lead: bool = False,
) -> CounsellingBooking:
    """Create a SCHEDULED booking assigned to a counsellor (staff Book Appointment flow)."""
    _ensure_bookings_enabled(db)
    normalized = _normalize_time(scheduled_time)
    _ensure_bookable_day(db, normalized)

    allowed_starts = {_normalize_time(slot) for slot in _iter_day_slot_times(db, normalized.date())}
    if normalized not in allowed_starts:
        raise HTTPException(
            status_code=400,
            detail="Selected time is outside bookable office slots.",
        )
    if normalized <= office_now(db):
        raise HTTPException(status_code=400, detail="Cannot book a time in the past.")

    admin = _get_admin_user(db, admin_id)
    conflict = (
        db.query(CounsellingBooking)
        .filter(
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
            detail="Selected counsellor already has a booking at this time.",
        )

    _ensure_slot_capacity(db, normalized)

    if session_purpose:
        allowed_purposes = {p["label"].casefold() for p in get_session_purposes(db)}
        if session_purpose.strip().casefold() not in allowed_purposes:
            raise HTTPException(status_code=400, detail="Invalid session purpose.")

    resolved_lead_id = lead_id
    try:
        if create_lead and not resolved_lead_id:
            lead = create_booking_candidate_lead(
                db,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                candidate_phone=candidate_phone,
                commit=False,
            )
            resolved_lead_id = lead.id

        email, phone = _resolve_contact_fields(
            db, candidate_email, candidate_phone, resolved_lead_id
        )
        sanitized_name = input_sanitizer(candidate_name) or "Candidate"
        combined_notes = _compose_booking_notes(session_purpose, notes)
        sanitized_notes = input_sanitizer(combined_notes) if combined_notes else None

        booking = CounsellingBooking(
            scheduled_time=normalized,
            candidate_name=sanitized_name,
            candidate_email=email,
            candidate_phone=phone,
            lead_id=resolved_lead_id,
            admin_id=admin.id,
            status=SCHEDULED_STATUS,
            notes=sanitized_notes,
        )
        db.add(booking)
        db.flush()

        if booking.lead_id:
            # Supersede any older PENDING/SCHEDULED rows so WhatsApp reschedule
            # always surfaces this latest booking.
            prior = (
                db.query(CounsellingBooking)
                .filter(
                    CounsellingBooking.lead_id == booking.lead_id,
                    CounsellingBooking.id != booking.id,
                    CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
                )
                .all()
            )
            for old in prior:
                old.status = CANCELLED_STATUS
                old.updated_at = utc_now()

            lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
            if lead:
                now = utc_now()
                lead.consultation_scheduled_at = normalized
                if not lead.admission_stage:
                    lead.admission_stage = "COUNSELLING"
                    lead.admission_stage_entered_at = now
                from app.services.student_status_service import on_counselling_scheduled

                on_counselling_scheduled(
                    db,
                    lead,
                    booking_id=booking.id,
                    counsellor_id=admin.id,
                    changed_by_type="admin",
                )

        db.commit()
        db.refresh(booking)
        return booking
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


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


def _booking_session_status_label(status: str) -> str:
    normalized = (status or "").strip().upper()
    if normalized == COMPLETED_STATUS:
        return "Counselling: Finished"
    if normalized == CANCELLED_STATUS:
        return "Counselling: Cancelled"
    return "Counselling: Scheduled"


def _resolve_lead_jump_path(lead: Lead | None) -> str | None:
    if not lead:
        return None
    admission_stage = (getattr(lead, "admission_stage", None) or "").strip()
    if admission_stage:
        return f"/prospects/{lead.id}"
    stage_value = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    if stage_value == "AI_ACTIVE":
        return "/ai-active"
    if stage_value == "HANDOFF":
        return "/handoffs"
    if stage_value == "ARCHIVE":
        return "/archive"
    return f"/prospects/{lead.id}"


def _is_audio_media(media_url: str | None, file_name: str | None) -> bool:
    token = f"{media_url or ''} {file_name or ''}".lower()
    return any(ext in token for ext in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".webm", "audio"))


def _serialize_my_booking(
    db: Session,
    booking: CounsellingBooking,
    admin: User | None,
    section: str,
    lead: Lead | None = None,
) -> dict:
    payload = _serialize_booking(booking, admin)
    scheduled = booking.scheduled_time
    if lead is None and booking.lead_id:
        lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
    candidate_stage, candidate_stage_label = _resolve_candidate_stage(lead)
    study = resolve_lead_study_interest(lead) if lead else {}
    status_id, status_name, status_category = resolve_lead_status_meta(
        db,
        lead,
        booking_status=booking.status,
    )
    outcome_key = booking.outcome_key
    outcome_label = OUTCOME_CONFIG.get(outcome_key or "", {}).get("label") if outcome_key else None
    return {
        **payload,
        "lead_id": booking.lead_id,
        "candidate_stage": candidate_stage,
        "candidate_stage_label": candidate_stage_label,
        "current_location": getattr(lead, "current_location", None) if lead else None,
        "preferred_country": study.get("country") or getattr(lead, "preferred_country", None) if lead else None,
        "course_interest": study.get("course") or study.get("program") if lead else None,
        "status_definition_id": status_id,
        "status_stage_name": status_name,
        "status_category": status_category,
        "admission_stage": str(status_id) if status_id else None,
        "admission_stage_label": status_name,
        "admission_stage_category": status_category,
        "session_status_label": _booking_session_status_label(booking.status),
        "outcome_key": outcome_key,
        "outcome_label": outcome_label,
        "time_label": _format_slot_range(db, scheduled),
        "date_label": _format_day_label(scheduled.date()),
        "section": section,
    }


def _booking_section_for_date(booking_date: date, calendar_today: date) -> str:
    if booking_date < calendar_today:
        return "past"
    if booking_date > calendar_today:
        return "upcoming"
    return "today"


def _my_bookings_view_all(user: User) -> bool:
    if user.is_superuser:
        return True
    role_name = user.admin_role_ref.name if user.admin_role_ref and user.admin_role_ref.name else ""
    return role_name in MY_BOOKINGS_ADMIN_ROLE_NAMES


def _my_bookings_query(db: Session, user: User):
    user_id = user.id
    query = db.query(CounsellingBooking).filter(CounsellingBooking.admin_id.isnot(None))
    if not _my_bookings_view_all(user):
        query = query.filter(CounsellingBooking.admin_id == user_id)
    return query.order_by(CounsellingBooking.scheduled_time.asc())


def _group_serialized_my_bookings(
    db: Session,
    bookings: list[CounsellingBooking],
) -> tuple[list[dict], list[dict], list[dict]]:
    calendar_today = office_today(db)
    admin_cache: dict[int, User | None] = {}
    lead_cache: dict[int, Lead | None] = {}
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
        lead = None
        if booking.lead_id:
            if booking.lead_id not in lead_cache:
                lead_cache[booking.lead_id] = (
                    db.query(Lead).filter(Lead.id == booking.lead_id).first()
                )
            lead = lead_cache.get(booking.lead_id)
        booking_date = booking.scheduled_time.date()
        section = _booking_section_for_date(booking_date, calendar_today)
        payload = _serialize_my_booking(db, booking, admin, section, lead=lead)
        if section == "past":
            past.append(payload)
        elif section == "today":
            today.append(payload)
        else:
            upcoming.append(payload)

    past.sort(key=lambda item: item["scheduled_time"], reverse=True)
    return past, today, upcoming


def _get_viewable_booking(db: Session, user: User, booking_id: int) -> CounsellingBooking:
    booking = db.query(CounsellingBooking).filter(CounsellingBooking.id == booking_id).first()
    if not booking or booking.admin_id is None:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you.")
    if booking.admin_id != user.id and not _my_bookings_view_all(user):
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you.")
    return booking


def get_viewable_booking_for_lead(db: Session, user: User, lead_id: int) -> CounsellingBooking | None:
    bookings = (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead_id,
            CounsellingBooking.admin_id.isnot(None),
        )
        .order_by(CounsellingBooking.scheduled_time.desc(), CounsellingBooking.id.desc())
        .all()
    )
    for booking in bookings:
        if booking.admin_id == user.id or _my_bookings_view_all(user):
            return booking
    return None


def get_lead_profile_booking_context(db: Session, user: User, lead_id: int) -> dict:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")
    booking = get_viewable_booking_for_lead(db, user, lead_id)
    if not booking:
        raise HTTPException(
            status_code=404,
            detail="No counselling booking is available for this student on your account.",
        )
    admin = db.query(User).filter(User.id == booking.admin_id).first() if booking.admin_id else None
    section = "today"
    payload = _serialize_my_booking(db, booking, admin, section, lead=lead)
    return {
        "id": payload["id"],
        "lead_id": payload.get("lead_id"),
        "candidate_name": payload.get("candidate_name") or lead.full_name,
        "candidate_email": payload.get("candidate_email") or lead.email,
        "candidate_phone": payload.get("candidate_phone") or lead.phone_number,
        "current_location": payload.get("current_location"),
        "preferred_country": payload.get("preferred_country"),
        "course_interest": payload.get("course_interest"),
        "status_definition_id": payload.get("status_definition_id"),
        "status_stage_name": payload.get("status_stage_name"),
        "status_category": payload.get("status_category"),
        "date_label": payload.get("date_label"),
        "time_label": payload.get("time_label"),
        "status": payload.get("status"),
        "session_status_label": payload.get("session_status_label"),
        "admin_id": payload.get("admin_id"),
        "admin_name": payload.get("admin_name"),
        "scheduled_time": (
            booking.scheduled_time.isoformat() if booking.scheduled_time else None
        ),
    }


def _get_owned_booking(db: Session, user_id: int, booking_id: int) -> CounsellingBooking:
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
    return booking


def _build_counselling_note_timeline_items(note: CounsellingNote) -> list[dict]:
    items: list[dict] = []
    timestamp = note.updated_at or note.created_at or utc_now()

    if note.ai_transcription and note.ai_transcription.strip():
        items.append(
            {
                "id": f"note-audio-{note.id}",
                "kind": "audio",
                "participant": "admin",
                "participant_label": "Session Recording",
                "text": note.ai_transcription.strip(),
                "created_at": timestamp,
                "media_url": None,
                "file_name": "Session transcription",
            }
        )

    note_sections: list[tuple[str, str | None]] = [
        ("Session notes", note.officer_recommendations),
        ("Recommended Institutions", note.preferred_universities),
        ("Scholarship interests", note.scholarship_interests),
        ("Career goals", note.career_goals),
    ]
    for title, value in note_sections:
        clean = (value or "").strip()
        if not clean:
            continue
        items.append(
            {
                "id": f"note-{title.lower().replace(' ', '-')}-{note.id}",
                "kind": "session_note",
                "participant": "admin",
                "participant_label": title,
                "text": clean,
                "created_at": timestamp,
                "media_url": None,
                "file_name": None,
            }
        )
    return items


def _communications_to_timeline(messages: list[dict]) -> list[dict]:
    timeline: list[dict] = []
    for message in messages:
        participant = message.get("participant") or "system"
        media_url = message.get("media_url")
        file_name = message.get("file_name")
        kind = "whatsapp"
        if participant == "system":
            kind = "system"
        elif _is_audio_media(media_url, file_name):
            kind = "audio"
        timeline.append(
            {
                "id": f"msg-{message.get('id')}",
                "kind": kind,
                "participant": participant,
                "participant_label": message.get("participant_label") or participant.title(),
                "text": message.get("text") or "",
                "created_at": message.get("created_at"),
                "media_url": media_url,
                "file_name": file_name,
            }
        )
    return timeline


def _build_data_exchange(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    shared_by_student: list[dict] = []
    shared_by_admin: list[dict] = []

    for message in messages:
        media_url = (message.get("media_url") or "").strip()
        if not media_url:
            continue
        participant = message.get("participant") or "system"
        created_at = message.get("created_at") or utc_now()
        file_name = message.get("file_name")
        text = (message.get("text") or "").strip()
        title = file_name or (text[:80] + "…" if len(text) > 80 else text) or "Shared file"
        item = {
            "id": f"exchange-{message.get('id')}",
            "title": title,
            "url": media_url,
            "created_at": created_at,
            "file_name": file_name,
        }
        if participant == "candidate":
            shared_by_student.append({**item, "shared_by": "student"})
        else:
            shared_by_admin.append({**item, "shared_by": "admin"})
    return shared_by_student, shared_by_admin


def get_my_bookings(db: Session, user: User) -> dict:
    calendar_today = office_today(db)
    bookings = _my_bookings_query(db, user).all()
    past, today, upcoming = _group_serialized_my_bookings(db, bookings)

    return {
        "past": past,
        "today": today,
        "upcoming": upcoming,
        "calendar_today": calendar_today,
        "total_count": len(bookings),
        "view_all_bookings": _my_bookings_view_all(user),
    }


def get_my_bookings_overview(db: Session, user: User) -> dict:
    calendar_today = office_today(db)
    bookings = _my_bookings_query(db, user).all()
    past_count = 0
    today_count = 0
    upcoming_count = 0

    for booking in bookings:
        booking_date = booking.scheduled_time.date()
        if booking_date < calendar_today:
            past_count += 1
        elif booking_date > calendar_today:
            upcoming_count += 1
        else:
            today_count += 1

    return {
        "past_count": past_count,
        "today_count": today_count,
        "upcoming_count": upcoming_count,
        "calendar_today": calendar_today,
        "view_all_bookings": _my_bookings_view_all(user),
    }


def get_my_bookings_for_date(db: Session, user: User, selected_date: date) -> dict:
    calendar_today = office_today(db)
    bookings = _my_bookings_query(db, user).all()

    admin_cache: dict[int, User | None] = {}
    lead_cache: dict[int, Lead | None] = {}
    day_bookings: list[dict] = []

    for booking in bookings:
        if booking.scheduled_time.date() != selected_date:
            continue
        if booking.admin_id not in admin_cache:
            admin_cache[booking.admin_id] = (
                db.query(User).filter(User.id == booking.admin_id).first()
                if booking.admin_id
                else None
            )
        admin = admin_cache.get(booking.admin_id)
        section = _booking_section_for_date(booking.scheduled_time.date(), calendar_today)
        lead = None
        if booking.lead_id:
            if booking.lead_id not in lead_cache:
                lead_cache[booking.lead_id] = (
                    db.query(Lead).filter(Lead.id == booking.lead_id).first()
                )
            lead = lead_cache.get(booking.lead_id)
        day_bookings.append(_serialize_my_booking(db, booking, admin, section, lead=lead))

    return {
        "date": selected_date,
        "calendar_today": calendar_today,
        "bookings": day_bookings,
        "view_all_bookings": _my_bookings_view_all(user),
    }


def _build_booking_interaction_timeline(db: Session, booking_id: int) -> list[dict]:
    communications = get_booking_communications(db, booking_id)
    timeline = _communications_to_timeline(communications.get("messages", []))

    note = (
        db.query(CounsellingNote)
        .filter(CounsellingNote.booking_id == booking_id)
        .first()
    )
    if note:
        timeline.extend(_build_counselling_note_timeline_items(note))

    timeline.sort(key=lambda item: (item["created_at"], str(item["id"])))
    return timeline


def _booking_forward_status_change_blocked(booking: CounsellingBooking, calendar_today: date) -> bool:
    return booking.scheduled_time.date() > calendar_today


def _find_previous_stage_id(db: Session, current_status_id: int | None) -> int | None:
    if not current_status_id:
        return None
    predecessor = (
        db.query(StatusDefinition)
        .filter(StatusDefinition.next_stage_id == current_status_id)
        .order_by(StatusDefinition.id.asc())
        .first()
    )
    return predecessor.id if predecessor else None


def _is_forward_status_change(
    db: Session,
    current_status_id: int | None,
    next_status_id: int,
) -> bool:
    if current_status_id is None or current_status_id == next_status_id:
        return False
    if next_status_id < current_status_id:
        return False
    if is_backward_transition(db, current_status_id, next_status_id):
        return False
    return True


def _is_status_change_blocked_before_appointment(
    db: Session,
    current_status_id: int | None,
    status_definition_id: int,
) -> bool:
    if status_definition_id == STATUS_COUNSELLING_FOLLOW_UP:
        return True
    return _is_forward_status_change(db, current_status_id, status_definition_id)


def _assert_booking_status_change_allowed_before_appointment(
    db: Session,
    booking: CounsellingBooking,
    lead: Lead,
    status_definition_id: int,
) -> None:
    calendar_today = office_today(db)
    if not _booking_forward_status_change_blocked(booking, calendar_today):
        return
    if lead.status_definition_id == status_definition_id:
        return
    if not _is_status_change_blocked_before_appointment(
        db, lead.status_definition_id, status_definition_id
    ):
        return

    appointment_label = _format_day_label(booking.scheduled_time.date())
    raise HTTPException(
        status_code=400,
        detail=(
            f"This appointment is scheduled for {appointment_label}. "
            "Forward stage and follow-up changes are not allowed before the session date. "
            "You may move the candidate to an earlier stage."
        ),
    )


def _serialize_booking_activity_context(
    db: Session,
    booking: CounsellingBooking,
    admin: User | None,
    lead: Lead | None,
    *,
    acting_user: User | None = None,
) -> dict:
    calendar_today = office_today(db)
    section = _booking_section_for_date(booking.scheduled_time.date(), calendar_today)
    serialized_booking = _serialize_my_booking(db, booking, admin, section, lead=lead)

    communications = get_booking_communications(db, booking.id)
    shared_by_student, shared_by_admin = _build_data_exchange(communications.get("messages", []))

    status_history = get_lead_status_history(db, lead.id) if lead else []
    if lead and not status_history and lead.status_definition_id:
        definition = get_status_definition(db, lead.status_definition_id)
        status_history = [
            {
                "id": 0,
                "status_definition_id": definition.id,
                "status_id": definition.id,
                "stage_name": definition.stage_name,
                "category": definition.category,
                "entered_at": lead.status_entered_at or lead.created_at,
                "notes": None,
                "comments": None,
                "changed_by_type": "system",
                "changed_by_label": "System",
            }
        ]

    current_status_id = lead.status_definition_id if lead else None
    suggested_next = None
    previous_stage_id = None
    backward_status_ids: list[int] = []
    if current_status_id:
        current_definition = db.query(StatusDefinition).filter(StatusDefinition.id == current_status_id).first()
        if current_definition:
            suggested_next = current_definition.next_stage_id
        previous_stage_id = _find_previous_stage_id(db, current_status_id)
        transitions = get_valid_transitions(db, current_status_id, user=acting_user)
        backward_status_ids = [item["to_status_id"] for item in transitions["backward"]]

    forward_status_changes_blocked = _booking_forward_status_change_blocked(booking, calendar_today)

    if lead:
        from app.services.students_master_service import (
            get_students_master_by_lead,
            merge_profile_with_students_master,
        )

        master = get_students_master_by_lead(db, lead.id)
        candidate_profile = merge_profile_with_students_master(
            db,
            build_candidate_profile(db, lead, booking),
            master,
        )
    else:
        candidate_profile = build_candidate_profile(db, None, booking)

    return {
        "booking": serialized_booking,
        "status_history": status_history,
        "shared_by_student": shared_by_student,
        "shared_by_admin": shared_by_admin,
        "status_definitions": list_status_definitions(db),
        "current_status_definition_id": current_status_id,
        "suggested_next_status_definition_id": suggested_next,
        "previous_stage_id": previous_stage_id,
        "appointment_date": booking.scheduled_time.date(),
        "calendar_today": calendar_today,
        "forward_status_changes_blocked": forward_status_changes_blocked,
        "backward_status_ids": backward_status_ids,
        "lead_jump_path": _resolve_lead_jump_path(lead),
        "can_update_status": bool(lead),
        "candidate_profile": candidate_profile,
    }


def get_booking_activity_log(db: Session, user_id: int, booking_id: int) -> dict:
    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    admin = db.query(User).filter(User.id == booking.admin_id).first() if booking.admin_id else None
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return _serialize_booking_activity_context(db, booking, admin, lead, acting_user=user)


def get_booking_interaction_log(db: Session, user_id: int, booking_id: int) -> dict:
    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    return _build_booking_interaction_log_payload(db, booking)


def get_schedule_booking_interaction_log(db: Session, booking_id: int) -> dict:
    """Interaction log for Manage Appointments — works before counsellor assignment."""
    booking, _admin = get_booking_with_admin(db, booking_id)
    return _build_booking_interaction_log_payload(db, booking)


def _build_booking_interaction_log_payload(db: Session, booking: CounsellingBooking) -> dict:
    admin = db.query(User).filter(User.id == booking.admin_id).first() if booking.admin_id else None
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    calendar_today = office_today(db)
    section = _booking_section_for_date(booking.scheduled_time.date(), calendar_today)
    return {
        "booking": _serialize_my_booking(db, booking, admin, section, lead=lead),
        "timeline": _build_booking_interaction_timeline(db, booking.id),
    }


def get_booking_view_detail(db: Session, user_id: int, booking_id: int) -> dict:
    activity = get_booking_activity_log(db, user_id, booking_id)
    interaction = get_booking_interaction_log(db, user_id, booking_id)
    return {
        **activity,
        "timeline": interaction["timeline"],
        "can_complete_session": activity["can_update_status"],
        "session_outcomes": [],
        "pipeline_stages": [],
    }


def get_booking_candidate_profile(db: Session, user_id: int, booking_id: int) -> dict:
    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    profile = build_candidate_profile(db, lead, booking)
    if lead:
        from app.services.students_master_service import (
            get_students_master_by_lead,
            merge_profile_with_students_master,
        )

        master = get_students_master_by_lead(db, lead.id)
        profile = merge_profile_with_students_master(db, profile, master)
    return {
        "booking_id": booking.id,
        "candidate_name": booking.candidate_name,
        "profile": profile,
    }


def save_booking_students_master(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.students_master import StudentMasterSaveRequest
    from app.services.students_master_service import (
        students_master_to_profile_dict,
        upsert_students_master,
    )

    if not isinstance(payload, StudentMasterSaveRequest):
        payload = StudentMasterSaveRequest.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None

    record = upsert_students_master(
        db,
        lead=lead,
        booking_id=booking.id,
        user_id=user_id,
        payload=payload,
    )
    profile = students_master_to_profile_dict(db, record)
    return {
        "booking_id": booking.id,
        "lead_id": lead.id if lead else None,
        "students_master_id": record.id,
        "saved_at": record.updated_at,
        "profile": profile,
    }


def get_booking_candidate_aspirations(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.student_aspirations_service import get_booking_aspirations

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_booking_aspirations(db, booking, lead)


def save_booking_candidate_aspirations(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.student_aspirations import StudentAspirationsSaveRequest
    from app.services.student_aspirations_service import save_booking_aspirations

    if not isinstance(payload, StudentAspirationsSaveRequest):
        payload = StudentAspirationsSaveRequest.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return save_booking_aspirations(db, booking, lead, user_id, payload)


def get_booking_candidate_test_scores(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.candidate_test_scores_service import get_candidate_test_scores

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_candidate_test_scores(db, booking_id=booking_id, lead=lead).model_dump()


def save_booking_candidate_test_scores(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.candidate_test_scores import CandidateTestScoreSaveRequest
    from app.services.candidate_test_scores_service import save_candidate_test_scores

    if not isinstance(payload, CandidateTestScoreSaveRequest):
        payload = CandidateTestScoreSaveRequest.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    response = save_candidate_test_scores(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    )
    return response.model_dump()


def delete_booking_candidate_test_score_attempt(
    db: Session,
    user_id: int,
    booking_id: int,
    score_ids: list[int],
) -> dict:
    from app.services.candidate_test_scores_service import delete_candidate_test_score_attempt

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    response = delete_candidate_test_score_attempt(
        db,
        booking_id=booking_id,
        lead=lead,
        score_ids=score_ids,
    )
    return response.model_dump()


def replace_booking_candidate_test_score_attempt(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.candidate_test_scores import (
        CandidateTestScoreAttemptReplaceRequest,
        CandidateTestScoreSaveRequest,
    )
    from app.services.candidate_test_scores_service import replace_candidate_test_score_attempt

    if not isinstance(payload, CandidateTestScoreAttemptReplaceRequest):
        payload = CandidateTestScoreAttemptReplaceRequest.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    save_payload = CandidateTestScoreSaveRequest.model_validate(
        payload.model_dump(exclude={"score_ids"})
    )
    response = replace_candidate_test_score_attempt(
        db,
        booking_id=booking_id,
        lead=lead,
        score_ids=payload.score_ids,
        payload=save_payload,
    )
    return response.model_dump()


def get_booking_work_experiences(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.work_experience_service import get_work_experiences

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_work_experiences(db, booking_id=booking_id, lead=lead).model_dump()


def save_booking_work_experiences(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.work_experience import WorkExperienceSaveRequest
    from app.services.work_experience_service import save_work_experiences

    if not isinstance(payload, WorkExperienceSaveRequest):
        payload = WorkExperienceSaveRequest.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return save_work_experiences(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    ).model_dump()


def get_booking_research_projects(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.research_project_service import get_research_projects

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_research_projects(db, booking_id=booking_id, lead=lead).model_dump()


def create_booking_research_project(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.research_project import ResearchProjectInput
    from app.services.research_project_service import create_research_project

    if not isinstance(payload, ResearchProjectInput):
        payload = ResearchProjectInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return create_research_project(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    ).model_dump()


def update_booking_research_project(
    db: Session,
    user_id: int,
    booking_id: int,
    project_id: int,
    payload,
) -> dict:
    from app.schemas.research_project import ResearchProjectInput
    from app.services.research_project_service import update_research_project

    if not isinstance(payload, ResearchProjectInput):
        payload = ResearchProjectInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return update_research_project(
        db,
        booking_id=booking_id,
        lead=lead,
        project_id=project_id,
        payload=payload,
    ).model_dump()


def delete_booking_research_project(
    db: Session,
    user_id: int,
    booking_id: int,
    project_id: int,
) -> dict:
    from app.services.research_project_service import delete_research_project

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return delete_research_project(
        db,
        booking_id=booking_id,
        lead=lead,
        project_id=project_id,
    ).model_dump()


def get_booking_candidate_educations(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.candidate_education_service import get_candidate_educations

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_candidate_educations(db, booking_id=booking_id, lead=lead).model_dump()


def create_booking_candidate_education(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.candidate_education import CandidateEducationInput
    from app.services.candidate_education_service import create_candidate_education

    if not isinstance(payload, CandidateEducationInput):
        payload = CandidateEducationInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return create_candidate_education(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    ).model_dump()


def update_booking_candidate_education(
    db: Session,
    user_id: int,
    booking_id: int,
    education_id: int,
    payload,
) -> dict:
    from app.schemas.candidate_education import CandidateEducationInput
    from app.services.candidate_education_service import update_candidate_education

    if not isinstance(payload, CandidateEducationInput):
        payload = CandidateEducationInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return update_candidate_education(
        db,
        booking_id=booking_id,
        lead=lead,
        education_id=education_id,
        payload=payload,
    ).model_dump()


def delete_booking_candidate_education(
    db: Session,
    user_id: int,
    booking_id: int,
    education_id: int,
) -> dict:
    from app.services.candidate_education_service import delete_candidate_education

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return delete_candidate_education(
        db,
        booking_id=booking_id,
        lead=lead,
        education_id=education_id,
    ).model_dump()


def get_booking_non_academic_activities(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.non_academic_activity_service import get_non_academic_activities

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_non_academic_activities(db, booking_id=booking_id, lead=lead).model_dump()


def create_booking_non_academic_activity(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.non_academic_activity import NonAcademicActivityInput
    from app.services.non_academic_activity_service import create_non_academic_activity

    if not isinstance(payload, NonAcademicActivityInput):
        payload = NonAcademicActivityInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return create_non_academic_activity(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    ).model_dump()


def update_booking_non_academic_activity(
    db: Session,
    user_id: int,
    booking_id: int,
    activity_id: int,
    payload,
) -> dict:
    from app.schemas.non_academic_activity import NonAcademicActivityInput
    from app.services.non_academic_activity_service import update_non_academic_activity

    if not isinstance(payload, NonAcademicActivityInput):
        payload = NonAcademicActivityInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return update_non_academic_activity(
        db,
        booking_id=booking_id,
        lead=lead,
        activity_id=activity_id,
        payload=payload,
    ).model_dump()


def delete_booking_non_academic_activity(
    db: Session,
    user_id: int,
    booking_id: int,
    activity_id: int,
) -> dict:
    from app.services.non_academic_activity_service import delete_non_academic_activity

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return delete_non_academic_activity(
        db,
        booking_id=booking_id,
        lead=lead,
        activity_id=activity_id,
    ).model_dump()


def get_booking_digital_presence_links(db: Session, user_id: int, booking_id: int) -> dict:
    from app.services.digital_presence_link_service import get_digital_presence_links

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return get_digital_presence_links(db, booking_id=booking_id, lead=lead).model_dump()


def create_booking_digital_presence_link(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.digital_presence_link import DigitalPresenceLinkInput
    from app.services.digital_presence_link_service import create_digital_presence_link

    if not isinstance(payload, DigitalPresenceLinkInput):
        payload = DigitalPresenceLinkInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return create_digital_presence_link(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    ).model_dump()


def update_booking_digital_presence_link(
    db: Session,
    user_id: int,
    booking_id: int,
    link_id: int,
    payload,
) -> dict:
    from app.schemas.digital_presence_link import DigitalPresenceLinkInput
    from app.services.digital_presence_link_service import update_digital_presence_link

    if not isinstance(payload, DigitalPresenceLinkInput):
        payload = DigitalPresenceLinkInput.model_validate(payload)

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return update_digital_presence_link(
        db,
        booking_id=booking_id,
        lead=lead,
        link_id=link_id,
        payload=payload,
    ).model_dump()


def delete_booking_digital_presence_link(
    db: Session,
    user_id: int,
    booking_id: int,
    link_id: int,
) -> dict:
    from app.services.digital_presence_link_service import delete_digital_presence_link

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return delete_digital_presence_link(
        db,
        booking_id=booking_id,
        lead=lead,
        link_id=link_id,
    ).model_dump()


def update_my_booking_status(
    db: Session,
    user_id: int,
    booking_id: int,
    status_definition_id: int,
    notes: str | None = None,
) -> dict:
    booking = _get_owned_booking(db, user_id, booking_id)
    if booking.status not in (SCHEDULED_STATUS, COMPLETED_STATUS):
        raise HTTPException(
            status_code=400,
            detail="Only active or completed session bookings can be updated.",
        )
    if not booking.lead_id:
        raise HTTPException(status_code=400, detail="Booking is not linked to a lead.")

    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    _assert_booking_status_change_allowed_before_appointment(
        db,
        booking,
        lead,
        status_definition_id,
    )

    return apply_lead_status(
        db,
        lead=lead,
        status_definition_id=status_definition_id,
        counsellor_id=user_id,
        booking_id=booking.id,
        notes=notes,
        booking=booking,
    )


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
        booking.updated_at = utc_now()
        if booking.lead_id:
            lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
            if lead:
                now = utc_now()
                if not lead.admission_stage:
                    lead.admission_stage = "COUNSELLING"
                    lead.admission_stage_entered_at = now
                from app.services.student_status_service import on_counselling_scheduled

                on_counselling_scheduled(
                    db,
                    lead,
                    booking_id=booking.id,
                    counsellor_id=admin.id,
                    changed_by_type="admin",
                )
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

    alert_snapshot = None
    if booking.admin_id and booking.status == SCHEDULED_STATUS:
        alert_snapshot = {
            "admin_id": booking.admin_id,
            "candidate_name": booking.candidate_name,
            "scheduled_time": booking.scheduled_time,
            "booking_id": booking.id,
            "lead_id": booking.lead_id,
        }

    if booking.lead_id:
        lead = db.query(Lead).filter(Lead.id == booking.lead_id).first()
        if lead:
            slot = db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).first()
            if slot:
                slot.lead_id = None
            lead.consultation_scheduled_at = None
            lead.calendar_booking_id = None
            from app.services.student_status_service import on_session_cancelled

            on_session_cancelled(
                db,
                lead,
                source="admin_booking_cancel",
                had_active_booking=True,
            )

    booking.status = CANCELLED_STATUS
    booking.admin_id = None
    booking.updated_at = utc_now()
    db.commit()
    db.refresh(booking)

    if alert_snapshot:
        from app.services.admin_session_reminders import run_admin_cancel_alert

        run_admin_cancel_alert(**alert_snapshot)

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
        booking.updated_at = utc_now()
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


def _message_timestamps_near(
    left: datetime | None,
    right: datetime | None,
    *,
    window_seconds: float = 30.0,
) -> bool:
    """True when two message timestamps are close enough to be the same event."""
    if left is None or right is None:
        return False
    # Compare as naive UTC-ish values; DB timestamps are stored without tz.
    left_naive = left.replace(tzinfo=None) if getattr(left, "tzinfo", None) else left
    right_naive = right.replace(tzinfo=None) if getattr(right, "tzinfo", None) else right
    return abs((left_naive - right_naive).total_seconds()) <= window_seconds


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
    # Track (normalized_text, created_at) so Message + MessageHistory copies of the
    # same WhatsApp event (often a few ms apart) collapse to one timeline row.
    seen_message_events: list[tuple[str, datetime]] = []
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
        timestamp = created_at or utc_now()
        normalized = _normalize_message_text(clean_text)
        if normalized:
            for seen_text, seen_at in seen_message_events:
                if seen_text == normalized and _message_timestamps_near(seen_at, timestamp):
                    return
            seen_message_events.append((normalized, timestamp))

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

    # Inbound WhatsApp always writes both Message and MessageHistory. Prefer the
    # live messages table for the UI timeline so reset/retest cannot resurface
    # the same bubble twice. Fall back to history only for legacy leads with no
    # Message rows.
    if not messages:
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
    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    _get_viewable_booking(db, user, booking_id)
    return get_booking_communications(db, booking_id)


def _default_intake_assessment() -> dict:
    from app.schemas.intake_assessment import IntakeAssessmentPayload

    return IntakeAssessmentPayload().model_dump()


def _seed_intake_assessment_from_profile(
    assessment: dict,
    *,
    lead,
    aspirations: dict | None,
    study: dict,
    educations: list,
) -> dict:
    """Pre-fill empty counselor fields from pre-intake profile / aspirations."""
    asp = (aspirations or {}).get("aspirations") if isinstance(aspirations, dict) else None
    if not isinstance(asp, dict):
        asp = aspirations if isinstance(aspirations, dict) else {}

    goals = assessment.get("goals") or {}
    if not goals.get("countries"):
        countries = list(asp.get("study_countries_iso2") or [])
        preferred = study.get("country") or getattr(lead, "preferred_country", None)
        if preferred and preferred not in countries:
            countries = [preferred, *countries]
        goals["countries"] = [c for c in countries if c and str(c).upper() != "OTHER"]
    if not goals.get("colleges"):
        goals["colleges"] = list(asp.get("discipline_university_college") or [])[:12]
    if not goals.get("intake_year"):
        years = asp.get("intake_years") or []
        goals["intake_year"] = years[0] if years else (utc_now().year + 1)
    if not goals.get("intake_season"):
        seasons = asp.get("intake_seasons") or []
        season_map = {
            "JAN_FEB_SPRING": "Spring",
            "APR_MAY_SUMMER": "Summer",
            "JUL_AUG_SEP_OCT_AUTUMN": "Fall",
            "FEB_MAR_SEM1_AUS_NZ": "Spring",
            "JUL_AUG_SEM2_AUS_NZ": "Fall",
            "APRIL_JAPAN": "Spring",
        }
        goals["intake_season"] = season_map.get(seasons[0], "Fall") if seasons else "Fall"
    assessment["goals"] = goals

    academic = assessment.get("academic") or {}
    if not academic.get("grading_scale_code") and educations:
        first = educations[0] if isinstance(educations[0], dict) else {}
        academic["grading_scale_code"] = first.get("gpa_cgpa_code")
    assessment["academic"] = academic

    financial = assessment.get("financial") or {}
    if not financial.get("funding_source"):
        funding = asp.get("funding_sources") or []
        source_map = {
            "FAMILY_SPONSORED": "Family Sponsor",
            "EDUCATIONAL_LOAN": "Educational Loan",
            "GRANT_SCHOLARSHIP": "Scholarship",
        }
        if funding and isinstance(funding[0], dict):
            financial["funding_source"] = source_map.get(funding[0].get("source"))
        elif asp.get("funding_source"):
            financial["funding_source"] = source_map.get(asp.get("funding_source"))
    budget_map = {
        "BUDGET_FRIENDLY": (8000, 20000),
        "MID_RANGE": (20000, 40000),
        "PREMIUM": (40000, 65000),
        "HIGH_INVESTMENT": (65000, 100000),
        "NEEDS_FULL_FUNDING": (0, 15000),
    }
    budgets = asp.get("budget") or []
    if budgets and financial.get("budget_min", 0) == 0 and financial.get("budget_max", 40000) == 40000:
        lo, hi = budget_map.get(budgets[0], (10000, 45000))
        financial["budget_min"] = lo
        financial["budget_max"] = hi
    assessment["financial"] = financial

    english = assessment.get("english") or {}
    tests = asp.get("english_tests") or []
    if "WAIVER_NOT_REQUIRED" in tests:
        english["language_waiver_eligible"] = True
    assessment["english"] = english
    return assessment


def get_booking_intake_assessment(db: Session, user_id: int, booking_id: int) -> dict:
    """Load Sub-Process 1.1 counselor workspace + profile snapshot for the session."""
    from app.services.candidate_education_service import get_candidate_educations
    from app.services.candidate_test_scores_service import get_candidate_test_scores
    from app.services.work_experience_service import get_work_experiences
    from app.schemas.intake_assessment import IntakeAssessmentPayload

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None

    raw = getattr(booking, "intake_assessment", None) or {}
    has_saved = bool(raw)
    try:
        assessment = IntakeAssessmentPayload.model_validate(raw).model_dump()
    except Exception:
        assessment = _default_intake_assessment()
        has_saved = False

    educations = get_candidate_educations(db, booking_id=booking_id, lead=lead).model_dump()
    tests = get_candidate_test_scores(db, booking_id=booking_id, lead=lead).model_dump()
    work = get_work_experiences(db, booking_id=booking_id, lead=lead).model_dump()
    aspirations = None
    try:
        raw_asp = get_booking_candidate_aspirations(db, user_id, booking_id)
        aspirations = raw_asp.model_dump() if hasattr(raw_asp, "model_dump") else raw_asp
    except Exception:
        aspirations = None

    study = resolve_lead_study_interest(lead) if lead else {}
    if not has_saved:
        assessment = _seed_intake_assessment_from_profile(
            assessment,
            lead=lead,
            aspirations=aspirations,
            study=study,
            educations=educations.get("educations") or [],
        )

    return {
        "booking_id": booking.id,
        "lead_id": booking.lead_id,
        "assessment": assessment,
        "profile_snapshot": {
            "educations": educations.get("educations") or [],
            "test_scores": tests.get("scores") or tests.get("test_scores") or [],
            "work_experiences": work.get("experiences") or [],
            "aspirations": aspirations,
            "preferred_country": study.get("country") or getattr(lead, "preferred_country", None),
            "course_interest": study.get("course") or study.get("program"),
            "candidate_name": booking.candidate_name
            or (lead.full_name if lead else None)
            or "Candidate",
        },
    }


def save_booking_intake_assessment(
    db: Session,
    user_id: int,
    booking_id: int,
    payload,
) -> dict:
    from app.schemas.intake_assessment import IntakeAssessmentPayload
    from app.utils.timezone import utc_now

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    parsed = (
        payload
        if isinstance(payload, IntakeAssessmentPayload)
        else IntakeAssessmentPayload.model_validate(payload)
    )
    booking.intake_assessment = parsed.model_dump()
    booking.updated_at = utc_now()
    db.commit()
    db.refresh(booking)
    return get_booking_intake_assessment(db, user_id, booking_id)
