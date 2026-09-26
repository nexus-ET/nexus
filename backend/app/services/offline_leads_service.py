from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, asc, case, cast, desc, or_, text
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadSource, LeadStage
from app.schemas.offline_lead import OfflineLeadCreate, SortDirection, SortField
from app.services.countries import get_country_by_iso2
from app.services.education_degrees import resolve_education_payload
from app.services.target_programs import resolve_study_interest_fields

OFFLINE_SOURCE = "OFFLINE"
EXPRESS_SOURCE = "EXPRESS"
META_SOURCES = (LeadSource.FACEBOOK_LEAD.value, LeadSource.INSTAGRAM_LEAD.value)

SORT_COLUMNS: dict[SortField, Any] = {
    "full_name": Lead.full_name,
    "created_at": Lead.created_at,
    "email": Lead.email,
    "phone_number": Lead.phone_number,
}


def _compose_full_name(first: str, middle: str | None, last: str | None) -> str:
    parts = [
        first.strip().title(),
        (middle or "").strip().title(),
        (last or "").strip().title(),
    ]
    return " ".join(part for part in parts if part)


def _compute_age(dob_str: str | None) -> int | None:
    if not dob_str:
        return None
    try:
        dob = date.fromisoformat(dob_str)
    except ValueError:
        return None
    today = date.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


def _format_phone(db: Session, iso2: str, local: str) -> str:
    country = get_country_by_iso2(db, iso2)
    if not country:
        raise HTTPException(status_code=400, detail="Select a valid phone country code.")
    return f"+{country.dial_code}{local}"


def _offline_email(payload: OfflineLeadCreate, phone: str) -> str:
    if payload.email:
        return str(payload.email).strip().lower()
    phone_slug = re.sub(r"\D", "", phone) or "unknown"
    return f"offline_{phone_slug}@edutrust.nexus"


def _resolve_country_name(db: Session, iso2: str | None) -> str | None:
    if not iso2:
        return None
    country = get_country_by_iso2(db, iso2)
    return country.name if country else iso2


def _build_location_string(db: Session, payload: OfflineLeadCreate) -> str | None:
    if not payload.location or not payload.location.has_content():
        return None
    loc = payload.location
    country_name = _resolve_country_name(db, loc.country_iso2) if loc.country_iso2 else None
    street = ", ".join(
        p.strip() for p in (loc.address_line_1, loc.address_line_2) if p and p.strip()
    )
    city_state = ", ".join(
        p.strip() for p in (loc.city, loc.state) if p and p.strip()
    )
    if loc.zip_code and loc.zip_code.strip():
        city_state = f"{city_state} {loc.zip_code.strip()}" if city_state else loc.zip_code.strip()
    parts = [p for p in (street, city_state, country_name) if p]
    return ", ".join(parts) if parts else None


def _build_academic_summary(db: Session, payload: OfflineLeadCreate) -> str | None:
    bits: list[str] = []
    study_interest = resolve_study_interest_fields(db, payload)
    programs = study_interest.get("target_programs") or []
    if isinstance(programs, list) and programs:
        bits.append(", ".join(str(item) for item in programs))
    elif study_interest.get("target_program"):
        bits.append(str(study_interest["target_program"]))
    if payload.education:
        edu = resolve_education_payload(db, payload.education)
        if edu and (edu.get("program") or edu.get("degree")):
            program = str(edu.get("program") or edu.get("degree"))
            if program not in bits:
                bits.append(program)
    return " — ".join(bits) if bits else None


def _empty_study_interest() -> dict[str, Any]:
    return {
        "target_destination_iso2s": [],
        "target_destinations": [],
        "target_destination_iso2": None,
        "target_destination": None,
        "target_level_id": None,
        "target_level_name": None,
        "target_major_ids": [],
        "target_majors": [],
        "target_program_codes": [],
        "target_programs": [],
        "target_program_code": None,
        "target_program": None,
        "target_course_code": None,
        "target_course": None,
    }


def _build_additional_data(db: Session, payload: OfflineLeadCreate) -> dict[str, Any]:
    data: dict[str, Any] = {
        "entry_type": "offline",
        "first_name": payload.first_name.strip(),
        "last_name": (payload.last_name or "").strip(),
    }
    if payload.middle_name and payload.middle_name.strip():
        data["middle_name"] = payload.middle_name.strip()
    data["phone_country_iso2"] = payload.phone_country_iso2
    if payload.date_of_birth:
        data["date_of_birth"] = payload.date_of_birth.isoformat()
    if payload.education:
        edu = resolve_education_payload(db, payload.education)
        if edu:
            data["education"] = edu
    loc = payload.location
    if loc and loc.has_content():
        if loc.country_iso2 and not get_country_by_iso2(db, loc.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")
        loc_dump = loc.model_dump()
        loc_dump["country"] = _resolve_country_name(db, loc.country_iso2) if loc.country_iso2 else None
        data["location"] = loc_dump
    data.update(resolve_study_interest_fields(db, payload))
    return data


def _status_label(lead: Lead) -> str:
    """AI/chat lifecycle label (AI Active / Handoff / Archive / Inactive), not pipeline Lead Status."""
    if lead.archived_at is not None:
        return "Inactive"
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    if lead.is_human_locked or "HANDOFF" in stage.upper():
        return "Handoff"
    if "ARCHIVE" in stage.upper():
        return "Archive"
    return "AI Active"


def _pipeline_status_names_for_leads(db: Session, lead_ids: list[int]) -> dict[int, str]:
    """Map lead id → status_definitions.stage_name via leads.status_definition_id."""
    if not lead_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT l.id AS lead_id, sd.stage_name AS stage_name
            FROM leads l
            JOIN status_definitions sd ON sd.id = l.status_definition_id
            WHERE l.id = ANY(:lead_ids)
              AND l.status_definition_id IS NOT NULL
            """
        ),
        {"lead_ids": lead_ids},
    ).all()
    return {
        int(lead_id): str(stage_name)
        for lead_id, stage_name in rows
        if lead_id is not None and stage_name
    }


def _status_stage_name(
    lead: Lead,
    db: Session | None = None,
    *,
    status_by_id: dict[int, Any] | None = None,
    pipeline_names: dict[int, str] | None = None,
) -> str | None:
    """
    Pipeline Lead Status: status_definitions.stage_name for leads.status_definition_id.

    Set on create via on_lead_created → Lead: New; updated on stage transitions.
    Not the AI/chat lifecycle (AI Active / Handoff / Archive).
    """
    if pipeline_names is not None:
        named = pipeline_names.get(int(lead.id))
        if named:
            return named

    status_id = getattr(lead, "status_definition_id", None)
    if status_id is not None and status_by_id is not None:
        cached = status_by_id.get(int(status_id))
        if cached is not None:
            name = getattr(cached, "stage_name", None)
            if name:
                return str(name)

    if db is None:
        return None
    from app.services.status_definition_service import resolve_lead_status_meta

    _status_id, stage_name, _category = resolve_lead_status_meta(db, lead)
    return stage_name


def _extract_additional(lead: Lead) -> dict[str, Any]:
    raw = getattr(lead, "additional_data", None)
    return raw if isinstance(raw, dict) else {}


def build_offline_lead_list_item(
    lead: Lead,
    db: Session | None = None,
    *,
    status_by_id: dict[int, Any] | None = None,
    pipeline_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    extra = _extract_additional(lead)
    education = extra.get("education") if isinstance(extra.get("education"), dict) else {}
    location = extra.get("location") if isinstance(extra.get("location"), dict) else {}
    dob = extra.get("date_of_birth")
    country_iso2 = location.get("country_iso2")
    country_name = location.get("country")
    if db and country_iso2 and not country_name:
        country_name = _resolve_country_name(db, country_iso2)

    first_name = extra.get("first_name")
    middle_name = extra.get("middle_name")
    last_name = extra.get("last_name")
    if not first_name and not last_name and lead.full_name:
        parts = lead.full_name.split()
        if parts:
            first_name = parts[0]
            if len(parts) > 2:
                middle_name = " ".join(parts[1:-1])
                last_name = parts[-1]
            elif len(parts) == 2:
                last_name = parts[1]

    list_source = lead.source or OFFLINE_SOURCE
    if lead.meta_leadgen_id and list_source not in {
        OFFLINE_SOURCE,
        EXPRESS_SOURCE,
        *META_SOURCES,
    }:
        if getattr(lead.channel, "value", lead.channel) == LeadChannel.INSTAGRAM.value:
            list_source = LeadSource.INSTAGRAM_LEAD.value
        else:
            list_source = LeadSource.FACEBOOK_LEAD.value

    pipeline_status = _status_stage_name(
        lead,
        db,
        status_by_id=status_by_id,
        pipeline_names=pipeline_names,
    )

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone_country_iso2": extra.get("phone_country_iso2"),
        "stage": lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage),
        "status_label": _status_label(lead),
        "status_stage_name": pipeline_status,
        "lead_status": pipeline_status,
        "source": list_source,
        "is_active": lead.archived_at is None,
        "target_destination": extra.get("target_destination") or lead.preferred_country,
        "target_destination_iso2": extra.get("target_destination_iso2"),
        "target_destination_iso2s": list(extra.get("target_destination_iso2s") or (
            [extra["target_destination_iso2"]] if extra.get("target_destination_iso2") else []
        )),
        "target_destinations": list(extra.get("target_destinations") or (
            [extra["target_destination"]] if extra.get("target_destination") else []
        )),
        "target_level_id": extra.get("target_level_id"),
        "target_level_name": extra.get("target_level_name"),
        "target_major_ids": list(extra.get("target_major_ids") or []),
        "target_majors": list(extra.get("target_majors") or []),
        "target_program_codes": list(extra.get("target_program_codes") or (
            [extra["target_program_code"]] if extra.get("target_program_code") else []
        )),
        "target_programs": list(extra.get("target_programs") or (
            [extra["target_program"]] if extra.get("target_program") else []
        )),
        "target_program": extra.get("target_program"),
        "target_program_code": extra.get("target_program_code"),
        "target_course": extra.get("target_course") or lead.academic_summary,
        "target_course_code": extra.get("target_course_code"),
        "city": location.get("city"),
        "state": location.get("state"),
        "zip_code": location.get("zip_code"),
        "address_line_1": location.get("address_line_1"),
        "address_line_2": location.get("address_line_2"),
        "country": country_name,
        "country_iso2": country_iso2,
        "degree": education.get("degree"),
        "degree_code": education.get("degree_code"),
        "program": education.get("program") or education.get("degree"),
        "program_code": education.get("program_code") or education.get("degree_code"),
        "level_id": education.get("level_id"),
        "full_time_study_years": education.get("full_time_study_years"),
        "major": education.get("major"),
        "university": education.get("university"),
        "graduation_year": education.get("graduation_year"),
        "gpa_cgpa": education.get("gpa_cgpa"),
        "gpa_cgpa_code": education.get("gpa_cgpa_code"),
        "date_of_birth": dob,
        "age": _compute_age(dob if isinstance(dob, str) else None),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "booking_count": 0,
        "scheduled_time": None,
        "scheduled_end_at": None,
        "followup_count": 0,
        "followup_status_label": None,
        "followup_date": None,
    }


def _base_manual_offline_query(db: Session):
    """Offline / Express rows only (create/edit via All Leads form)."""
    return db.query(Lead).filter(
        or_(
            Lead.source == OFFLINE_SOURCE,
            Lead.source == EXPRESS_SOURCE,
            Lead.channel == LeadChannel.OFFLINE,
        )
    )


def _base_all_leads_query(db: Session):
    """All Leads list: Offline, Express, and Meta (Facebook/Instagram)."""
    return db.query(Lead).filter(
        or_(
            Lead.source == OFFLINE_SOURCE,
            Lead.source == EXPRESS_SOURCE,
            Lead.channel == LeadChannel.OFFLINE,
            Lead.source.in_(META_SOURCES),
            Lead.meta_leadgen_id.isnot(None),
        )
    )


def _base_offline_query(db: Session):
    """Backward-compatible alias for manual offline/express rows."""
    return _base_manual_offline_query(db)


def _apply_status_filter(query, status: str | None):
    normalized = (status or "ALL").strip().upper().replace("-", "_").replace(" ", "_")
    if normalized in {"", "ALL", "ALL_PROSPECTS"}:
        return query
    if normalized in {"ACTIVE_LEAD", "ACTIVE_LEADS", "ACTIVE"}:
        return query.filter(Lead.archived_at.is_(None))
    if normalized in {"OFFLINE", "OFFLINE_LEADS", "OFFLINE_LEAD"}:
        return query.filter(Lead.source == OFFLINE_SOURCE)
    if normalized in {"AI_ACTIVE", "AIACTIVE"}:
        return query.filter(
            cast(Lead.stage, String).ilike("%AI_ACTIVE%"),
            Lead.is_human_locked.is_(False),
        )
    if normalized == "HANDOFF":
        return query.filter(
            or_(
                cast(Lead.stage, String).ilike("%HANDOFF%"),
                Lead.is_human_locked.is_(True),
            )
        )
    if normalized == "ARCHIVE":
        return query.filter(cast(Lead.stage, String).ilike("%ARCHIVE%"))
    return query


def _count_bookings_for_lead_ids(db: Session, lead_ids: list[int]) -> dict[int, int]:
    """Count counselling bookings per lead without loading ORM relationship graphs."""
    if not lead_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT lead_id, COUNT(*)::int AS booking_count
            FROM counselling_bookings
            WHERE lead_id = ANY(:lead_ids)
              AND admin_id IS NOT NULL
            GROUP BY lead_id
            """
        ),
        {"lead_ids": lead_ids},
    ).all()
    return {int(lead_id): int(count) for lead_id, count in rows if lead_id is not None}


def _pick_display_scheduled_start(
    times: list[datetime],
    now: datetime,
    slot_minutes: int,
) -> datetime | None:
    """Soonest slot that has not ended; otherwise the most recent past start."""
    if not times:
        return None
    duration = timedelta(minutes=slot_minutes)
    open_slots = sorted(start for start in times if start + duration > now)
    if open_slots:
        return open_slots[0]
    return max(times)


def _scheduled_slots_for_lead_ids(
    db: Session,
    lead_ids: list[int],
) -> dict[int, tuple[datetime, datetime]]:
    """Assigned counselling slot (start, end) to show on All Leads. End uses slot duration."""
    if not lead_ids:
        return {}
    from app.services.settings_service import get_int_setting
    from app.utils.timezone import office_now

    slot_minutes = get_int_setting(db, "COUNSELING_SLOT_DURATION", 30)
    now = office_now(db)
    rows = db.execute(
        text(
            """
            SELECT lead_id, scheduled_time
            FROM counselling_bookings
            WHERE lead_id = ANY(:lead_ids)
              AND admin_id IS NOT NULL
              AND UPPER(COALESCE(status, '')) <> 'CANCELLED'
              AND scheduled_time IS NOT NULL
            """
        ),
        {"lead_ids": lead_ids},
    ).all()
    by_lead: dict[int, list[datetime]] = {}
    for lead_id, scheduled in rows:
        if lead_id is None or scheduled is None:
            continue
        stamp = scheduled.replace(tzinfo=None) if getattr(scheduled, "tzinfo", None) else scheduled
        by_lead.setdefault(int(lead_id), []).append(stamp)

    result: dict[int, tuple[datetime, datetime]] = {}
    duration = timedelta(minutes=slot_minutes)
    for lead_id, times in by_lead.items():
        chosen = _pick_display_scheduled_start(times, now, slot_minutes)
        if chosen is None:
            continue
        result[lead_id] = (chosen, chosen + duration)
    return result


def _name_ilike_clauses(term: str):
    """Match full_name and optional name parts stored on additional_data (case-insensitive contains)."""
    pattern = f"%{term}%"
    return or_(
        Lead.full_name.ilike(pattern),
        text("COALESCE(leads.additional_data->>'first_name', '') ILIKE :name_term").bindparams(
            name_term=pattern
        ),
        text("COALESCE(leads.additional_data->>'middle_name', '') ILIKE :name_term").bindparams(
            name_term=pattern
        ),
        text("COALESCE(leads.additional_data->>'last_name', '') ILIKE :name_term").bindparams(
            name_term=pattern
        ),
    )


def _student_id_clauses(raw: str):
    """Match the on-screen Student ID column (leads.id) — exact when numeric, else id text contains."""
    value = raw.strip()
    if not value:
        return None
    clauses = [cast(Lead.id, String).ilike(f"%{value}%")]
    if value.isdigit():
        try:
            clauses.append(Lead.id == int(value))
        except ValueError:
            pass
    return or_(*clauses)


_DATE_KEYWORDS = (
    "today",
    "tomorrow",
    "day after tomorrow",
    "upcoming",
    "overdue",
    "completed",
)
_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _date_filter_keywords(raw: str | None) -> list[str]:
    """Prefixes of a keyword or of a word inside it. Same rule as the date inputs."""
    query = " ".join((raw or "").strip().lower().split())
    if not query:
        return []
    hits: list[str] = []
    for keyword in _DATE_KEYWORDS:
        words = keyword.split(" ")
        if keyword.startswith(query) or any(word.startswith(query) for word in words):
            hits.append(keyword)
    return hits


def _parse_client_clock(client_time: str | None) -> datetime:
    text_value = (client_time or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text_value, fmt)
            return parsed.replace(year=2000, month=1, day=1)
        except ValueError:
            continue
    now = datetime.now()
    return now.replace(year=2000, month=1, day=1, microsecond=0)


def _booking_status_label(diff_days: int, start_has_passed: bool) -> str:
    if diff_days == 0 and start_has_passed:
        return "Overdue"
    if diff_days == 0:
        return "Today"
    if diff_days == 1:
        return "Tomorrow"
    if diff_days == 2:
        return "Day After Tomorrow"
    if diff_days >= 3:
        return "Upcoming"
    return "Date Passed"


def _keyword_matches_day(
    keyword: str,
    diff_days: int,
    *,
    column: str,
    start_has_passed: bool,
) -> bool:
    if keyword == "overdue":
        if column == "followup":
            return False
        return diff_days == 0 and start_has_passed
    if keyword == "today":
        return diff_days == 0
    if keyword == "tomorrow":
        return diff_days == 1
    if keyword == "day after tomorrow":
        return diff_days == 2
    if keyword == "upcoming":
        return diff_days >= 1
    return diff_days < 0


def _date_text_matches(
    raw: str | None,
    diff_days: int | None,
    *,
    column: str,
    start_has_passed: bool,
    visible_text: str,
) -> bool:
    trimmed = (raw or "").strip()
    if not trimmed:
        return True
    keywords = _date_filter_keywords(trimmed)
    if keywords:
        if diff_days is None:
            return False
        return any(
            _keyword_matches_day(
                keyword,
                diff_days,
                column=column,
                start_has_passed=start_has_passed,
            )
            for keyword in keywords
        )
    needle = " ".join(trimmed.lower().split())
    return needle in visible_text.lower()


def _booking_visible_text(start: datetime, end: datetime, diff_days: int, start_has_passed: bool) -> str:
    weekday = _WEEKDAY_SHORT[start.weekday()]
    month = _MONTH_SHORT[start.month - 1]
    label = _booking_status_label(diff_days, start_has_passed)
    return (
        f"{weekday}, {start.day:02d}-{month}-{start.year % 100:02d} "
        f"({start:%H:%M} - {end:%H:%M}) {label}"
    )


def _followup_visible_text(followup_day: date, diff_days: int) -> str:
    weekday = _WEEKDAY_SHORT[followup_day.weekday()]
    month = _MONTH_SHORT[followup_day.month - 1]
    label = _booking_status_label(diff_days, False)
    iso = followup_day.isoformat()
    day_first = f"{weekday}, {followup_day.day} {month} {followup_day.year}"
    month_first = f"{weekday}, {month} {followup_day.day}, {followup_day.year}"
    return f"{day_first} {month_first} {iso} {label}"


def _materialize_offline_lead_items(db: Session, rows: list[Any]) -> list[dict[str, Any]]:
    lead_ids = [row.id for row in rows]
    booking_counts = _count_bookings_for_lead_ids(db, lead_ids)
    scheduled_slots = _scheduled_slots_for_lead_ids(db, lead_ids)
    from app.models.status_definition import StatusDefinition
    from app.services.counselor_followup_service import (
        count_followups_for_lead_ids,
        latest_followup_date_for_lead_ids,
        latest_followup_status_for_lead_ids,
    )

    pipeline_names = _pipeline_status_names_for_leads(db, lead_ids)
    status_ids = {
        int(row.status_definition_id)
        for row in rows
        if getattr(row, "status_definition_id", None)
    }
    status_by_id: dict[int, Any] = {}
    if status_ids:
        status_by_id = {
            int(defn.id): defn
            for defn in db.query(StatusDefinition)
            .filter(StatusDefinition.id.in_(status_ids))
            .all()
        }

    followup_counts = count_followups_for_lead_ids(db, lead_ids)
    followup_statuses = latest_followup_status_for_lead_ids(db, lead_ids)
    followup_dates = latest_followup_date_for_lead_ids(db, lead_ids)
    items = []
    for row in rows:
        item = build_offline_lead_list_item(
            row,
            db,
            status_by_id=status_by_id,
            pipeline_names=pipeline_names,
        )
        item["booking_count"] = booking_counts.get(row.id, 0)
        slot = scheduled_slots.get(row.id)
        if slot is not None:
            item["scheduled_time"], item["scheduled_end_at"] = slot
        item["followup_count"] = followup_counts.get(row.id, 0)
        item["followup_status_label"] = followup_statuses.get(row.id)
        item["followup_date"] = followup_dates.get(row.id)
        if not item.get("status_stage_name"):
            item["status_stage_name"] = pipeline_names.get(row.id)
        if not item.get("lead_status"):
            item["lead_status"] = item.get("status_stage_name")
        items.append(item)
    return items


def _all_display_scheduled_slots(db: Session) -> dict[int, tuple[datetime, datetime]]:
    """Display booking for every lead that has one. The bookings table is small."""
    from app.services.settings_service import get_int_setting
    from app.utils.timezone import office_now

    slot_minutes = get_int_setting(db, "COUNSELING_SLOT_DURATION", 30)
    now = office_now(db)
    rows = db.execute(
        text(
            """
            SELECT lead_id, scheduled_time
            FROM counselling_bookings
            WHERE admin_id IS NOT NULL
              AND UPPER(COALESCE(status, '')) <> 'CANCELLED'
              AND scheduled_time IS NOT NULL
            """
        )
    ).all()
    by_lead: dict[int, list[datetime]] = {}
    for lead_id, scheduled in rows:
        if lead_id is None or scheduled is None:
            continue
        stamp = scheduled.replace(tzinfo=None) if getattr(scheduled, "tzinfo", None) else scheduled
        by_lead.setdefault(int(lead_id), []).append(stamp)
    duration = timedelta(minutes=slot_minutes)
    result: dict[int, tuple[datetime, datetime]] = {}
    for lead_id, times in by_lead.items():
        chosen = _pick_display_scheduled_start(times, now, slot_minutes)
        if chosen is not None:
            result[lead_id] = (chosen, chosen + duration)
    return result


def _all_latest_followup_dates(db: Session) -> dict[int, str]:
    """Latest note's next-follow-up date, matching the Notes page newest-first rule."""
    rows = db.execute(
        text(
            """
            SELECT lead_id, target_completion_date
            FROM (
                SELECT lead_id,
                       target_completion_date,
                       row_number() OVER (
                           PARTITION BY lead_id
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM counselor_followup_logs
            ) ranked
            WHERE rn = 1
              AND target_completion_date IS NOT NULL
            """
        )
    ).all()
    result: dict[int, str] = {}
    for lead_id, followup_day in rows:
        if lead_id is None or followup_day is None:
            continue
        result[int(lead_id)] = followup_day.isoformat()[:10]
    return result


def _list_offline_leads_for_date_filter(
    db: Session,
    query,
    *,
    page: int,
    page_size: int,
    booking_date_q: str | None,
    followup_date_q: str | None,
    client_date: date | None,
    client_time: str | None,
    sort_by: SortField,
    sort_dir: SortDirection,
) -> dict[str, Any]:
    """One response of leads whose booking or follow-up date matches the text.

    Day math uses the browser's civil date. Appointment timestamps stay naive
    wall-clock values, so a UTC midnight conversion cannot move the day.
    """
    civil = client_date or datetime.now().date()
    clock = _parse_client_clock(client_time)
    booking_q = (booking_date_q or "").strip()
    followup_q = (followup_date_q or "").strip()
    slots = _all_display_scheduled_slots(db)
    followup_dates = _all_latest_followup_dates(db) if followup_q else {}
    pool = set(slots)
    if followup_q:
        pool.update(followup_dates)
    matched: list[int] = []
    for lead_id in pool:
        slot = slots.get(lead_id)
        booking_ok = True
        if booking_q:
            if slot is None:
                booking_ok = _date_text_matches(
                    booking_q, None, column="booking", start_has_passed=False, visible_text=""
                )
            else:
                start, end = slot
                diff_days = (start.date() - civil).days
                start_passed = start.date() == civil and start.time().replace(microsecond=0) < clock.time()
                booking_ok = _date_text_matches(
                    booking_q,
                    diff_days,
                    column="booking",
                    start_has_passed=start_passed,
                    visible_text=_booking_visible_text(start, end, diff_days, start_passed),
                )
        followup_ok = True
        if followup_q:
            raw_day = followup_dates.get(lead_id)
            if not raw_day:
                followup_ok = _date_text_matches(
                    followup_q, None, column="followup", start_has_passed=False, visible_text=""
                )
            else:
                followup_day = date.fromisoformat(raw_day[:10])
                diff_days = (followup_day - civil).days
                followup_ok = _date_text_matches(
                    followup_q,
                    diff_days,
                    column="followup",
                    start_has_passed=False,
                    visible_text=_followup_visible_text(followup_day, diff_days),
                )
        if booking_ok and followup_ok:
            matched.append(lead_id)

    if matched:
        allowed = {
            int(row[0])
            for row in query.filter(Lead.id.in_(matched)).with_entities(Lead.id).all()
        }
        matched = [lead_id for lead_id in matched if lead_id in allowed]
    else:
        matched = []

    if sort_by == "scheduled_time":
        dated = [lead_id for lead_id in matched if lead_id in slots]
        undated = [lead_id for lead_id in matched if lead_id not in slots]
        dated.sort(key=lambda lead_id: slots[lead_id][0], reverse=sort_dir == "desc")
        ordered = dated + undated
    else:
        sort_col = SORT_COLUMNS.get(sort_by, Lead.created_at)
        ordering = asc(sort_col) if sort_dir == "asc" else desc(sort_col)
        ordered = [
            int(row[0])
            for row in db.query(Lead.id)
            .filter(Lead.id.in_(matched or [-1]))
            .order_by(ordering, Lead.id.desc())
            .all()
        ]

    total = len(ordered)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    safe_page = min(max(1, page), total_pages)
    offset = (safe_page - 1) * page_size
    page_ids = ordered[offset : offset + page_size]
    if not page_ids:
        return {
            "items": [],
            "page": safe_page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }
    found = {
        int(row.id): row
        for row in query.filter(Lead.id.in_(page_ids)).all()
    }
    rows = [found[lead_id] for lead_id in page_ids if lead_id in found]
    return {
        "items": _materialize_offline_lead_items(db, rows),
        "page": safe_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _rows_today_bookings_first(
    db: Session,
    query,
    *,
    page: int,
    page_size: int,
    client_date: date | None,
    sort_dir: SortDirection,
) -> list[Any]:
    """Full lead list: today's bookings, then other bookings, then rows with none.

    The booking filter box is empty on this path. Today's civil date comes from
    the browser so a UTC clock cannot move the day.
    """
    civil = client_date or datetime.now().date()
    slots = _all_display_scheduled_slots(db)
    today_ids: list[int] = []
    other_ids: list[int] = []
    for lead_id, (start, _end) in slots.items():
        if start.date() == civil:
            today_ids.append(lead_id)
        else:
            other_ids.append(lead_id)
    reverse = sort_dir == "desc"
    today_ids.sort(key=lambda lead_id: slots[lead_id][0], reverse=reverse)
    other_ids.sort(key=lambda lead_id: slots[lead_id][0], reverse=reverse)
    dated = today_ids + other_ids
    if dated:
        allowed = {
            int(row[0])
            for row in query.filter(Lead.id.in_(dated)).with_entities(Lead.id).all()
        }
        dated = [lead_id for lead_id in dated if lead_id in allowed]

    offset = (page - 1) * page_size
    page_ids = dated[offset : offset + page_size]
    need = page_size - len(page_ids)
    rows: list[Any] = []
    if page_ids:
        found = {
            int(row.id): row
            for row in query.filter(Lead.id.in_(page_ids)).all()
        }
        rows = [found[lead_id] for lead_id in page_ids if lead_id in found]
    if need <= 0:
        return rows

    undated_offset = max(0, offset - len(dated))
    undated_query = query
    if dated:
        undated_query = undated_query.filter(~Lead.id.in_(dated))
    undated_rows = (
        undated_query.order_by(Lead.created_at.desc(), Lead.id.desc())
        .offset(undated_offset)
        .limit(need)
        .all()
    )
    rows.extend(undated_rows)
    return rows


def list_offline_leads(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    name: str | None = None,
    student_id: str | None = None,
    status: str | None = None,
    sort_by: SortField = "created_at",
    sort_dir: SortDirection = "desc",
    booking_date_q: str | None = None,
    followup_date_q: str | None = None,
    client_date: date | None = None,
    client_time: str | None = None,
) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    query = _base_all_leads_query(db)

    if q and q.strip():
        raw_q = q.strip()
        term = f"%{raw_q}%"
        q_clauses = [
            Lead.full_name.ilike(term),
            Lead.email.ilike(term),
            Lead.phone_number.ilike(term),
            text("COALESCE(leads.additional_data->>'first_name', '') ILIKE :q_term").bindparams(
                q_term=term
            ),
            text("COALESCE(leads.additional_data->>'middle_name', '') ILIKE :q_term").bindparams(
                q_term=term
            ),
            text("COALESCE(leads.additional_data->>'last_name', '') ILIKE :q_term").bindparams(
                q_term=term
            ),
        ]
        id_clause = _student_id_clauses(raw_q)
        if id_clause is not None and raw_q.isdigit():
            q_clauses.append(id_clause)
        query = query.filter(or_(*q_clauses))

    if name and name.strip():
        query = query.filter(_name_ilike_clauses(name.strip()))

    if student_id and student_id.strip():
        id_clause = _student_id_clauses(student_id)
        if id_clause is not None:
            query = query.filter(id_clause)

    query = _apply_status_filter(query, status)

    if (booking_date_q or "").strip() or (followup_date_q or "").strip():
        return _list_offline_leads_for_date_filter(
            db,
            query,
            page=safe_page,
            page_size=safe_page_size,
            booking_date_q=booking_date_q,
            followup_date_q=followup_date_q,
            client_date=client_date,
            client_time=client_time,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / safe_page_size)) if total else 1
    if safe_page > total_pages and total > 0:
        safe_page = total_pages

    if sort_by == "scheduled_time":
        rows = _rows_today_bookings_first(
            db,
            query,
            page=safe_page,
            page_size=safe_page_size,
            client_date=client_date,
            sort_dir=sort_dir,
        )
        return {
            "items": _materialize_offline_lead_items(db, rows),
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": total_pages,
        }

    sort_col = SORT_COLUMNS.get(sort_by, Lead.created_at)
    ordering = asc(sort_col) if sort_dir == "asc" else desc(sort_col)
    order_clauses: list[Any] = []
    exact_id: int | None = None
    digit_q = (q or "").strip()
    digit_student = (student_id or "").strip()
    if digit_student.isdigit():
        exact_id = int(digit_student)
    elif digit_q.isdigit():
        exact_id = int(digit_q)
    if exact_id is not None:
        order_clauses.append(case((Lead.id == exact_id, 0), else_=1))
    if sort_by != "created_at":
        order_clauses.extend([ordering, Lead.id.desc()])
    else:
        order_clauses.extend([ordering, Lead.id.desc()])
    query = query.order_by(*order_clauses)

    offset = (safe_page - 1) * safe_page_size
    rows = query.offset(offset).limit(safe_page_size).all()
    items = _materialize_offline_lead_items(db, rows)

    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": total_pages,
    }


def create_offline_lead(db: Session, payload: OfflineLeadCreate) -> Lead:
    phone = _format_phone(db, payload.phone_country_iso2, payload.phone_local)
    email = _offline_email(payload, phone)

    existing_email = db.query(Lead.id).filter(Lead.email == email).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="A lead with this email already exists.")

    if phone:
        existing_phone = db.query(Lead.id).filter(Lead.phone_number == phone).first()
        if existing_phone:
            raise HTTPException(status_code=409, detail="A lead with this phone number already exists.")

    if payload.location and payload.location.country_iso2:
        if not get_country_by_iso2(db, payload.location.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")

    full_name = _compose_full_name(payload.first_name, payload.middle_name, payload.last_name)
    location_str = _build_location_string(db, payload)
    academic_summary = _build_academic_summary(db, payload)
    study_interest = resolve_study_interest_fields(db, payload)

    lead = Lead(
        full_name=full_name,
        email=email,
        phone_number=phone,
        channel=LeadChannel.OFFLINE,
        source=OFFLINE_SOURCE,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        preferred_country=str(study_interest.get("target_destination") or "")[:100] or None,
        academic_summary=academic_summary,
        current_location=location_str,
        additional_data=_build_additional_data(db, payload),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    from app.services.student_status_service import on_lead_created

    on_lead_created(db, lead, source="Offline Leads")
    return lead


def get_offline_lead(db: Session, lead_id: int) -> Lead:
    lead = _base_all_leads_query(db).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


def check_offline_lead_duplicates(
    db: Session,
    *,
    email: str,
    phone_country_iso2: str,
    phone_local: str,
    exclude_lead_id: int | None = None,
) -> dict[str, bool]:
    normalized_email = email.strip().lower()
    email_taken = False
    if normalized_email:
        email_query = db.query(Lead.id).filter(Lead.email == normalized_email)
        if exclude_lead_id:
            email_query = email_query.filter(Lead.id != exclude_lead_id)
        email_taken = email_query.first() is not None

    phone_taken = False
    local_digits = re.sub(r"\D", "", phone_local or "")
    if phone_country_iso2 and len(local_digits) == 10:
        phone = _format_phone(db, phone_country_iso2, local_digits)
        phone_query = db.query(Lead.id).filter(Lead.phone_number == phone)
        if exclude_lead_id:
            phone_query = phone_query.filter(Lead.id != exclude_lead_id)
        phone_taken = phone_query.first() is not None

    return {"email_taken": email_taken, "phone_taken": phone_taken}


def update_offline_lead(db: Session, lead_id: int, payload: OfflineLeadCreate) -> Lead:
    lead = get_offline_lead(db, lead_id)
    phone = _format_phone(db, payload.phone_country_iso2, payload.phone_local)
    email = _offline_email(payload, phone)

    existing_email = (
        db.query(Lead.id).filter(Lead.email == email, Lead.id != lead_id).first()
    )
    if existing_email:
        raise HTTPException(status_code=409, detail="A lead with this email already exists.")

    existing_phone = (
        db.query(Lead.id).filter(Lead.phone_number == phone, Lead.id != lead_id).first()
    )
    if existing_phone:
        raise HTTPException(status_code=409, detail="A lead with this phone number already exists.")

    if payload.location and payload.location.country_iso2:
        if not get_country_by_iso2(db, payload.location.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")

    full_name = _compose_full_name(payload.first_name, payload.middle_name, payload.last_name)
    location_str = _build_location_string(db, payload)
    academic_summary = _build_academic_summary(db, payload)
    study_interest = resolve_study_interest_fields(db, payload)

    extra = _extract_additional(lead)
    inactive_previous_stage = extra.get("inactive_previous_stage")
    merged = {**extra, **_build_additional_data(db, payload)}
    if inactive_previous_stage is not None:
        merged["inactive_previous_stage"] = inactive_previous_stage

    if not payload.middle_name or not payload.middle_name.strip():
        merged.pop("middle_name", None)
    if not payload.date_of_birth:
        merged.pop("date_of_birth", None)
    if not payload.education or not resolve_education_payload(db, payload.education):
        merged.pop("education", None)
    if not (payload.location and payload.location.has_content()):
        merged.pop("location", None)

    lead.full_name = full_name
    lead.email = email
    lead.phone_number = phone
    lead.preferred_country = str(study_interest.get("target_destination") or "")[:100] or None
    lead.academic_summary = academic_summary
    lead.current_location = location_str
    lead.additional_data = merged

    db.commit()
    db.refresh(lead)
    return lead


def set_offline_lead_active(
    db: Session,
    lead_id: int,
    *,
    is_active: bool,
    reasons: list[str],
    changed_by_user_id: int | None = None,
    changed_by: str | None = None,
) -> Lead:
    """Toggle lead active/inactive without deleting; write an audit log row."""
    from app.constants.lead_status_change import normalize_status_reasons
    from app.models.lead_status_change_log import LeadStatusChangeLog

    lead = get_offline_lead(db, lead_id)
    normalized_reasons = normalize_status_reasons(is_active, reasons)
    if not normalized_reasons:
        raise HTTPException(status_code=400, detail="Select at least one valid reason.")

    previous_status = "inactive" if lead.archived_at is not None else "active"
    new_status = "active" if is_active else "inactive"
    if previous_status == new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Lead is already {new_status}.",
        )

    extra = _extract_additional(lead)

    if is_active:
        lead.archived_at = None
        previous = extra.pop("inactive_previous_stage", None)
        if previous:
            try:
                lead.stage = LeadStage(previous)
            except ValueError:
                lead.stage = LeadStage.AI_ACTIVE
        elif lead.stage == LeadStage.ARCHIVE:
            lead.stage = LeadStage.AI_ACTIVE
        lead.additional_data = extra or None
    else:
        stage_value = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
        if "ARCHIVE" not in stage_value.upper():
            extra["inactive_previous_stage"] = stage_value
            lead.stage = LeadStage.ARCHIVE
        lead.additional_data = extra
        lead.archived_at = datetime.now(timezone.utc)

    db.add(
        LeadStatusChangeLog(
            lead_id=lead.id,
            previous_status=previous_status,
            new_status=new_status,
            reasons=normalized_reasons,
            changed_by_user_id=changed_by_user_id,
            changed_by=(changed_by or "").strip() or None,
        )
    )
    db.commit()
    db.refresh(lead)
    return lead
