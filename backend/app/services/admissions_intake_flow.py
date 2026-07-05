from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.consultation_slot import ConsultationSlot
from app.models.lead import Lead, LeadStage
from app.services.public_holiday_service import is_bookable_day
from app.services.twilio_whatsapp_interactive import FlowPayload, ListPickerPayload, QuickReplyPayload
from app.services.whatsapp_flow_config import (
    build_flow_token,
    get_whatsapp_flow_id,
    is_whatsapp_flow_enabled,
)

logger = logging.getLogger(__name__)

INTAKE_STEP_WELCOME = "WELCOME"
INTAKE_STEP_FULL_NAME = "FULL_NAME"
INTAKE_STEP_CURRENT_LOCATION = "CURRENT_LOCATION"
INTAKE_STEP_TARGET_DEGREE = "TARGET_DEGREE"
INTAKE_STEP_TARGET_MAJOR = "TARGET_MAJOR"
INTAKE_STEP_TARGET_COUNTRY = "TARGET_COUNTRY"
INTAKE_STEP_ENGLISH_SCORES = "ENGLISH_SCORES"
INTAKE_STEP_GRE_SCORE = "GRE_SCORE"
INTAKE_STEP_GMAT_SCORE = "GMAT_SCORE"
INTAKE_STEP_CALL_CONSENT = "CALL_CONSENT"
INTAKE_STEP_PICK_DATE = "PICK_DATE"
INTAKE_STEP_PICK_TIME = "PICK_TIME"
INTAKE_STEP_MARKETING_CONSENT = "MARKETING_CONSENT"
INTAKE_STEP_COMPLETE = "COMPLETE"

DEFAULT_SLOT_TIMES = ("10:00", "14:00", "16:00")
BRAND_NAME = "Edutrust"
NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 75
INTAKE_TEXT_MIN_LENGTH = 2
INTAKE_TEXT_MAX_LENGTH = 50
SCORE_MAX_LENGTH = 20
MAJOR_MIN_LENGTH = INTAKE_TEXT_MIN_LENGTH
MAJOR_MAX_LENGTH = INTAKE_TEXT_MAX_LENGTH

DEGREE_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "degree:bachelors",
        "label": "Bachelor's Degree (3-4 years)",
        "short": "Bachelor's Degree",
        "description": "3-4 years",
    },
    {
        "id": "degree:masters",
        "label": "Master's Degree (1-2 years)",
        "short": "Master's Degree",
        "description": "1-2 years",
    },
    {
        "id": "degree:integrated_masters",
        "label": "Integrated master's (3-5 years)",
        "short": "Integrated master's",
        "description": "3-5 years",
    },
    {
        "id": "degree:doctorate",
        "label": "Doctorate (3-7 years)",
        "short": "Doctorate",
        "description": "3-7 years",
    },
)

_COUNTRY_ALIASES: dict[str, str] = {
    "usa": "USA",
    "us": "USA",
    "u.s.": "USA",
    "u.s.a": "USA",
    "u.s.a.": "USA",
    "america": "USA",
    "uk": "UK",
    "u.k.": "UK",
    "britain": "UK",
    "england": "UK",
    "uae": "UAE",
    "canada": "Canada",
    "australia": "Australia",
    "au": "Australia",
    "germany": "Germany",
    "de": "Germany",
    "france": "France",
    "ireland": "Ireland",
    "netherlands": "Netherlands",
    "holland": "Netherlands",
    "spain": "Spain",
    "italy": "Italy",
    "india": "India",
    "singapore": "Singapore",
    "new zealand": "New Zealand",
    "nz": "New Zealand",
    "sweden": "Sweden",
    "norway": "Norway",
    "finland": "Finland",
    "denmark": "Denmark",
    "switzerland": "Switzerland",
    "japan": "Japan",
    "jp": "Japan",
    "china": "China",
    "south korea": "South Korea",
    "korea": "South Korea",
}


def _normalize_country_name(raw: str) -> str | None:
    token = (raw or "").strip()
    if not token:
        return None
    key = re.sub(r"[^\w\s]", "", token).lower().strip()
    key = re.sub(r"\s+", " ", key)
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    canonical_by_lower = {value.lower(): value for value in _COUNTRY_ALIASES.values()}
    if key in canonical_by_lower:
        return canonical_by_lower[key]
    return None


def _strip_booking_markdown(text: str) -> str:
    return re.sub(r"[*_]", "", (text or "").strip())


RESCHEDULE_PATTERN = re.compile(
    r"(reschedule|change|move|update|switch|pick another|different|new)\s+"
    r"(slot|appointment|booking|call|time|date|schedule)|"
    r"(change|move|reschedule)\s+(my|the)\s+(slot|appointment|booking|call)|"
    r"^reschedule$|^change slot$|^change appointment$",
    re.IGNORECASE,
)
BOOKING_INFO_PATTERN = re.compile(
    r"(when is my|what time is my|my appointment|my booking|my scheduled|"
    r"when am i scheduled|confirm my (slot|appointment|booking|call)|"
    r"what(?:'s| is) my (slot|appointment|booking|call))",
    re.IGNORECASE,
)
THANKS_PATTERN = re.compile(
    r"^(?:ok(?:ay)?|thanks?(?: you)?|thank u|got it|cool|great|perfect|sounds good)[\s!.,👍✅]*$",
    re.IGNORECASE,
)
CANCEL_PATTERN = re.compile(
    r"^\*?cancel\*?(?:\s+(?:appointment|booking|my appointment|my booking|slot|call))?\*?$",
    re.IGNORECASE,
)
CANCEL_COMMAND_PATTERN = re.compile(
    r"(?:^|\b)(?:please\s+)?cancel(?:\s+please)?(?:\s+it|\s+this|\s+that|\s+now)?\s*$|"
    r"\b(?:i\s+)?(?:want|need|would like|'d like)\s+to\s+cancel\b|"
    r"\bcancel\s+(?:my|the|this|our)\s+(?:slot|appointment|booking|call|session|consultation)\b",
    re.IGNORECASE,
)


def _normalize_management_command(text: str) -> str:
    command_text = _strip_booking_markdown(text).strip()
    return re.sub(r"[^\w\s'+-]+$", "", command_text).strip()


BOOKING_RESCHEDULE_BUTTON_ID = "booking:reschedule"
BOOKING_CANCEL_BUTTON_ID = "booking:cancel"
BOOKING_BOOK_SESSION_BUTTON_ID = "booking:book_session"
BOOKING_NOT_INTERESTED_BUTTON_ID = "booking:not_interested"
MARKETING_OPT_IN_BUTTON_ID = "marketing:yes"
MARKETING_OPT_OUT_BUTTON_ID = "marketing:no"


def _normalize_booking_button_reply(text: str) -> str:
    """Map WhatsApp button ids/titles to booking command text."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    lowered = cleaned.lower()
    if lowered in {BOOKING_RESCHEDULE_BUTTON_ID, BOOKING_BOOK_SESSION_BUTTON_ID, "reschedule", "book session"}:
        return "reschedule"
    if lowered in {BOOKING_CANCEL_BUTTON_ID, "cancel"}:
        return "cancel"
    if lowered in {BOOKING_NOT_INTERESTED_BUTTON_ID, "not interested"}:
        return "not interested"
    if cleaned == "Reschedule":
        return "reschedule"
    if cleaned == "Book Session":
        return "reschedule"
    if cleaned == "Cancel":
        return "cancel"
    if cleaned == "Not Interested":
        return "not interested"
    return cleaned


def _normalize_marketing_button_reply(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    lowered = cleaned.lower()
    if lowered in {MARKETING_OPT_IN_BUTTON_ID, "yes please"}:
        return "marketing yes"
    if lowered in {MARKETING_OPT_OUT_BUTTON_ID, "do not send"}:
        return "marketing no"
    if cleaned == "Yes Please":
        return "marketing yes"
    if cleaned == "Do Not Send":
        return "marketing no"
    return cleaned


def is_reschedule_command(text: str) -> bool:
    command_text = _normalize_management_command(_normalize_booking_button_reply(text))
    lowered = command_text.lower()
    return bool(RESCHEDULE_PATTERN.search(command_text)) or lowered in {
        "reschedule",
        "change slot",
        "change appointment",
    }


def is_cancel_command(text: str) -> bool:
    command_text = _normalize_management_command(_normalize_booking_button_reply(text))
    if not command_text:
        return False
    lowered = command_text.lower()
    if CANCEL_PATTERN.match(command_text) or CANCEL_COMMAND_PATTERN.search(command_text):
        return True
    return lowered == "cancel" or lowered.startswith("cancel ")


def is_not_interested_command(text: str) -> bool:
    command_text = _normalize_management_command(_normalize_booking_button_reply(text))
    return command_text.lower() == "not interested"


def is_marketing_opt_in_command(text: str) -> bool:
    return _normalize_marketing_button_reply(text).lower() == "marketing yes"


def is_marketing_opt_out_command(text: str) -> bool:
    return _normalize_marketing_button_reply(text).lower() == "marketing no"


def is_post_intake_management_command(text: str) -> bool:
    """Reschedule/cancel/thanks/booking-info commands handled outside intake steps."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if is_reschedule_command(cleaned) or is_cancel_command(cleaned):
        return True
    if is_not_interested_command(cleaned):
        return True
    if is_marketing_opt_in_command(cleaned) or is_marketing_opt_out_command(cleaned):
        return True
    if THANKS_PATTERN.match(cleaned):
        return True
    return bool(BOOKING_INFO_PATTERN.search(cleaned))


@dataclass
class IntakeReply:
    text: str
    list_picker: ListPickerPayload | None = None
    quick_reply: QuickReplyPayload | None = None
    whatsapp_flow: FlowPayload | None = None
    confidence: float = 1.0
    suppress_outbound: bool = False


async def _agent_intake_reply(
    db: Session,
    lead: Lead,
    runtime_config,
    *,
    task: str,
    incoming_text: str = "",
    extra_context: str = "",
    **reply_kwargs,
) -> IntakeReply:
    from app.config import settings
    from app.services.intake_templates import render_deterministic_intake_text

    if settings.NEXUS_APPOINTMENTS_ONLY:
        text = render_deterministic_intake_text(lead, task=task, incoming_text=incoming_text)
        return IntakeReply(text=text, confidence=1.0, **reply_kwargs)

    from app.services.ai_service import compose_agent_message

    result = await compose_agent_message(
        db,
        runtime_config,
        lead,
        task=task,
        incoming_text=incoming_text,
        extra_context=extra_context,
    )
    text = (result.text or "").strip()
    if not text:
        text = render_deterministic_intake_text(lead, task=task, incoming_text=incoming_text)
        confidence = 1.0 if text else 0.0
    else:
        confidence = result.confidence
    return IntakeReply(text=text, confidence=confidence, **reply_kwargs)


def _normalize_slot_time(slot_time: str) -> str:
    parts = (slot_time or "").strip().split(":")
    if len(parts) >= 2:
        return f"{int(parts[0]):02d}:{parts[1][:2]}"
    return (slot_time or "").strip()


def _load_context(lead: Lead) -> dict[str, Any]:
    raw = getattr(lead, "intake_context", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _save_context(db: Session, lead: Lead, context: dict[str, Any]) -> None:
    lead.intake_context = json.dumps(context) if context else None
    db.commit()


def _persist_resolved_study_interest(
    db: Session,
    lead: Lead,
    study: dict[str, str | None],
) -> None:
    if study.get("country"):
        lead.preferred_country = study["country"]
    context = _load_context(lead)
    if study.get("course"):
        context["preferred_course"] = study["course"]
    if study.get("program"):
        context["target_program"] = study["program"]
    if study.get("course"):
        lead.academic_summary = f"Course: {study['course']}"
    context.pop("pending_country", None)
    context.pop("pending_program", None)
    _save_context(db, lead, context)


def _prepare_target_step_prefill(
    db: Session,
    lead: Lead,
    study: dict[str, str | None],
) -> None:
    context = _load_context(lead)
    country = (study.get("country") or "").strip()
    course = (study.get("course") or study.get("program") or "").strip()
    if country:
        lead.preferred_country = country
        context["pending_country"] = country
    if course:
        context["pending_program"] = course
        if study.get("course"):
            context["preferred_course"] = study["course"]
        elif study.get("program"):
            context["target_program"] = study["program"]
    _save_context(db, lead, context)


async def _handle_study_plan_confirmation(
    db: Session,
    lead: Lead,
    incoming_text: str,
    runtime_config,
) -> IntakeReply:
    from app.services.study_plan_extraction import (
        build_study_plan_confirmation_message,
        load_pending_study_plan,
        persist_confirmed_study_plan,
    )

    context = _load_context(lead)
    pending = load_pending_study_plan(context, lead)
    first = (lead.full_name or "there").split()[0]
    consent = _parse_yes_no(incoming_text)

    if consent is True:
        if pending.status != "complete":
            context.pop("awaiting_study_confirmation", None)
            _save_context(db, lead, context)
            return await _handle_study_plan_whatsapp_collection(db, lead, incoming_text, runtime_config)
        persist_confirmed_study_plan(db, lead, context, pending)
        lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=ENGLISH; Target saved as {pending.field} "
                f"({pending.level}) in {lead.preferred_country}. "
                "Ask for English test scores or invite them to reply skip."
            ),
            incoming_text=incoming_text,
        )

    if consent is False:
        for key in (
            "awaiting_study_confirmation",
            "pending_study_level",
            "pending_study_field",
            "pending_program",
            "pending_country",
        ):
            context.pop(key, None)
        lead.preferred_country = None
        _save_context(db, lead, context)
        return IntakeReply(
            text=(
                f"No problem, {first}. Tell me your target country and the course or program "
                "you want to study (for example: *MBA in UK*)."
            )
        )

    context.pop("awaiting_study_confirmation", None)
    _save_context(db, lead, context)
    return await _handle_study_plan_whatsapp_collection(db, lead, incoming_text, runtime_config)


async def _handle_study_plan_whatsapp_collection(
    db: Session,
    lead: Lead,
    incoming_text: str,
    runtime_config,
) -> IntakeReply:
    from app.config import settings
    from app.services.study_plan_extraction import (
        build_study_plan_confirmation_message,
        build_study_plan_followup_message,
        extract_study_plan_from_message,
        load_pending_study_plan,
        rule_based_study_plan_extraction,
    )

    context = _load_context(lead)
    pending = load_pending_study_plan(context, lead)

    if settings.NEXUS_APPOINTMENTS_ONLY:
        extraction = rule_based_study_plan_extraction(incoming_text, pending=pending)
    else:
        extraction = await extract_study_plan_from_message(
            incoming_text,
            runtime_config=runtime_config,
            pending=pending,
        )

    context.update(extraction.to_context())
    first = (lead.full_name or "there").split()[0]

    if extraction.status == "complete":
        context["awaiting_study_confirmation"] = True
        _save_context(db, lead, context)
        return IntakeReply(text=build_study_plan_confirmation_message(first, extraction))

    _save_context(db, lead, context)
    followup = build_study_plan_followup_message(extraction)
    return IntakeReply(text=followup)


def get_intake_step(lead: Lead) -> str:
    step = getattr(lead, "intake_step", None)
    return step or INTAKE_STEP_WELCOME


def is_intake_complete(lead: Lead) -> bool:
    return get_intake_step(lead) == INTAKE_STEP_COMPLETE


def ensure_consultation_slots(db: Session, days_ahead: int = 21) -> None:
    """Keep ConsultationSlot rows aligned with counselling schedule availability."""
    from app.services.counselling_service import get_bookable_slot_starts, list_whatsapp_bookable_dates

    dedupe_consultation_slots(db)
    bookable_dates = list_whatsapp_bookable_dates(db, limit=days_ahead)
    if not bookable_dates:
        today = date.today()
        bookable_dates = [
            today + timedelta(days=offset)
            for offset in range(1, days_ahead + 1)
            if is_bookable_day(db, today + timedelta(days=offset))
        ]

    for slot_day in bookable_dates:
        slot_starts = get_bookable_slot_starts(db, slot_day)
        slot_times = (
            [_normalize_slot_time(start.strftime("%H:%M")) for start in slot_starts]
            if slot_starts
            else [_normalize_slot_time(slot_time) for slot_time in DEFAULT_SLOT_TIMES]
        )
        for normalized_time in slot_times:
            exists = (
                db.query(ConsultationSlot.id)
                .filter(
                    ConsultationSlot.slot_date == slot_day,
                    ConsultationSlot.slot_time == normalized_time,
                )
                .first()
            )
            if not exists:
                db.add(ConsultationSlot(slot_date=slot_day, slot_time=normalized_time))
    db.commit()


def _ensure_slots_for_day(db: Session, slot_day: date) -> None:
    """Fast path: ensure slot rows exist for one bookable day only."""
    from app.services.counselling_service import get_bookable_slot_starts

    if not is_bookable_day(db, slot_day):
        return

    slot_starts = get_bookable_slot_starts(db, slot_day)
    slot_times = (
        [_normalize_slot_time(start.strftime("%H:%M")) for start in slot_starts]
        if slot_starts
        else [_normalize_slot_time(slot_time) for slot_time in DEFAULT_SLOT_TIMES]
    )
    added = False
    for normalized_time in slot_times:
        exists = (
            db.query(ConsultationSlot.id)
            .filter(
                ConsultationSlot.slot_date == slot_day,
                ConsultationSlot.slot_time == normalized_time,
            )
            .first()
        )
        if not exists:
            db.add(ConsultationSlot(slot_date=slot_day, slot_time=normalized_time))
            added = True
    if added:
        db.commit()


def _ensure_slots_for_dates(db: Session, slot_days: list[date]) -> None:
    for slot_day in slot_days:
        _ensure_slots_for_day(db, slot_day)


def dedupe_consultation_slots(db: Session) -> None:
    rows = (
        db.query(ConsultationSlot)
        .order_by(
            ConsultationSlot.slot_date.asc(),
            ConsultationSlot.slot_time.asc(),
            ConsultationSlot.lead_id.desc().nullslast(),
            ConsultationSlot.id.asc(),
        )
        .all()
    )
    keepers: dict[tuple[date, str], ConsultationSlot] = {}
    delete_ids: list[int] = []

    for row in rows:
        normalized_time = _normalize_slot_time(row.slot_time)
        if row.slot_time != normalized_time:
            row.slot_time = normalized_time
        key = (row.slot_date, normalized_time)
        existing = keepers.get(key)
        if existing is None:
            keepers[key] = row
            continue
        if row.lead_id and not existing.lead_id:
            delete_ids.append(existing.id)
            keepers[key] = row
        else:
            delete_ids.append(row.id)

    if delete_ids:
        db.query(ConsultationSlot).filter(ConsultationSlot.id.in_(delete_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def _format_slot_date(slot_day: date) -> str:
    return slot_day.strftime("%a, %b %d, %Y")


def _format_slot_time(slot_time: str) -> str:
    try:
        hour, minute = slot_time.split(":")
        parsed = datetime.strptime(f"{hour}:{minute}", "%H:%M")
        return parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return slot_time


def _get_active_consultation_booking(db: Session, lead: Lead):
    from app.models.counselling_booking import CounsellingBooking
    from app.services.counselling_service import PENDING_STATUS, SCHEDULED_STATUS

    return (
        db.query(CounsellingBooking)
        .filter(
            CounsellingBooking.lead_id == lead.id,
            CounsellingBooking.status.in_([PENDING_STATUS, SCHEDULED_STATUS]),
        )
        .order_by(CounsellingBooking.updated_at.desc(), CounsellingBooking.id.desc())
        .first()
    )


def _lead_has_active_consultation_booking(db: Session, lead: Lead) -> bool:
    if lead.consultation_scheduled_at:
        return True
    return _get_active_consultation_booking(db, lead) is not None


def _build_consultation_session_profile_fields(
    db: Session | None,
    lead: Lead,
    *,
    step: str,
    context: dict[str, Any],
) -> dict[str, Any | None]:
    from app.models.user import User
    from app.services.counselling_service import _format_admin_name

    session_date: str | None = None
    session_time: str | None = None
    counsellor_name: str | None = None

    selected_raw = context.get("selected_date")
    pending_date = str(context.get("pending_session_date_label") or "").strip() or None
    pending_time = str(context.get("pending_session_time_label") or "").strip() or None
    in_time_step = step == INTAKE_STEP_PICK_TIME

    if in_time_step and selected_raw:
        try:
            session_date = pending_date or _format_slot_date(date.fromisoformat(str(selected_raw)))
        except ValueError:
            session_date = pending_date
        session_time = pending_time or "Pending selection"

    if not session_date or (not session_time and not in_time_step):
        booking = _get_active_consultation_booking(db, lead) if db is not None else None
        if booking:
            session_date = session_date or _format_slot_date(booking.scheduled_time.date())
            session_time = session_time or _format_slot_time(booking.scheduled_time.strftime("%H:%M"))
            if booking.admin_id and db is not None:
                admin = db.query(User).filter(User.id == booking.admin_id).first()
                if admin:
                    counsellor_name = _format_admin_name(admin)
        else:
            scheduled_at = getattr(lead, "consultation_scheduled_at", None)
            if scheduled_at:
                session_date = session_date or _format_slot_date(scheduled_at.date())
                session_time = session_time or _format_slot_time(scheduled_at.strftime("%H:%M"))

    if session_date and not session_time and in_time_step:
        session_time = pending_time or "Pending selection"

    return {
        "consultation_session_date": session_date,
        "consultation_session_time": session_time,
        "assigned_counsellor_name": counsellor_name,
    }


def _available_dates(db: Session, limit: int = 8) -> list[date]:
    from app.services.counselling_service import list_whatsapp_bookable_dates

    dates = list_whatsapp_bookable_dates(db, limit=limit)
    if not dates:
        rows = (
            db.query(ConsultationSlot.slot_date)
            .filter(ConsultationSlot.lead_id.is_(None), ConsultationSlot.slot_date >= date.today())
            .distinct()
            .order_by(ConsultationSlot.slot_date.asc())
            .limit(limit)
            .all()
        )
        dates = [row[0] for row in rows if is_bookable_day(db, row[0])]

    if dates:
        _ensure_slots_for_dates(db, dates[:limit])
    return dates[:limit]


def _available_times_for_date(db: Session, slot_day: date) -> list[ConsultationSlot]:
    from app.services.counselling_service import get_bookable_slot_starts

    if not is_bookable_day(db, slot_day):
        return []
    _ensure_slots_for_day(db, slot_day)
    bookable_starts = get_bookable_slot_starts(db, slot_day)
    allowed_times = {_normalize_slot_time(start.strftime("%H:%M")) for start in bookable_starts}

    rows = (
        db.query(ConsultationSlot)
        .filter(
            ConsultationSlot.slot_date == slot_day,
            ConsultationSlot.lead_id.is_(None),
        )
        .order_by(ConsultationSlot.slot_time.asc(), ConsultationSlot.id.asc())
        .all()
    )
    unique: list[ConsultationSlot] = []
    seen_times: set[str] = set()
    for row in rows:
        normalized = _normalize_slot_time(row.slot_time)
        if normalized in seen_times:
            continue
        if allowed_times and normalized not in allowed_times:
            continue
        seen_times.add(normalized)
        unique.append(row)
    return unique


def _parse_yes_no(text: str) -> bool | None:
    lower = text.lower().strip()
    if lower in {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "confirm", "yes, please"}:
        return True
    if lower in {"no", "n", "nope", "not now", "later", "skip", "no thanks"}:
        return False
    if lower == "yes" or lower.startswith("yes,"):
        return True
    if lower == "no" or lower.startswith("no,"):
        return False
    if "yes" in lower and "no" not in lower:
        return True
    if "no" in lower and "yes" not in lower:
        return False
    return None


def _parse_choice_number(text: str, max_option: int) -> int | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered.startswith(("date:", "time:")):
        return None
    match = re.search(r"\b(\d{1,2})\b", cleaned)
    if not match:
        return None
    choice = int(match.group(1))
    if 1 <= choice <= max_option:
        return choice
    return None


def _is_skip(text: str) -> bool:
    return text.strip().lower() in {"skip", "na", "n/a", "none", "no", "not yet", "don't have", "dont have"}


def _looks_like_full_name(text: str) -> bool:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 3:
        return False
    if cleaned.lower().startswith("whatsapp contact"):
        return False
    parts = [part for part in cleaned.split(" ") if part]
    if len(parts) < 2:
        return False
    return all(re.search(r"[a-zA-Z]", part) for part in parts[:2])


def _normalize_intake_name(text: str) -> str:
    return " ".join((text or "").split()).title()


def _accept_intake_name_reply(text: str) -> str | None:
    """
    Normalize a student's name reply after the combined outreach template.

    Accepts single names (e.g. Ishq) — the template already asked for full name.
    """
    cleaned = " ".join((text or "").split())
    if len(cleaned) < NAME_MIN_LENGTH or len(cleaned) > NAME_MAX_LENGTH:
        return None
    if cleaned.lower().startswith("whatsapp contact"):
        return None
    if not re.search(r"[a-zA-Z]", cleaned):
        return None
    return _normalize_intake_name(cleaned)


def _normalize_intake_text_reply(
    text: str,
    *,
    min_length: int = INTAKE_TEXT_MIN_LENGTH,
    max_length: int = INTAKE_TEXT_MAX_LENGTH,
) -> str | None:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < min_length or len(cleaned) > max_length:
        return None
    if not re.search(r"[a-zA-Z]", cleaned):
        return None
    return cleaned


_COUNTRY_RESOLUTION_PROMPT = """You normalize study destination country names for a CRM.
Given user input, return ONLY the canonical English country name.
- Expand ISO codes: AU -> Australia, US -> USA, UK -> UK, JP -> Japan, NZ -> New Zealand
- Fix typos: Astralia -> Australia
- If already correct, return unchanged
- If not a valid country, return exactly: INVALID
Output only the country name, no punctuation or explanation."""


def _normalize_target_country_reply(text: str) -> str | None:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < INTAKE_TEXT_MIN_LENGTH or len(cleaned) > INTAKE_TEXT_MAX_LENGTH:
        return None
    normalized = _normalize_country_name(cleaned)
    if normalized:
        return normalized
    if re.search(r"[a-zA-Z]", cleaned):
        return cleaned.title()
    return None


async def _resolve_country_with_llm(raw: str, runtime_config) -> str | None:
    from app.services.ai_service import call_agent_llm

    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    messages = [
        {"role": "system", "content": _COUNTRY_RESOLUTION_PROMPT},
        {"role": "user", "content": cleaned},
    ]
    try:
        result = await call_agent_llm(runtime_config.ai_model, messages)
        candidate = (result.text or "").strip().split("\n")[0].strip().strip("\"'.,")
        if not candidate or candidate.upper() == "INVALID":
            return None
        normalized = _normalize_country_name(candidate)
        if normalized:
            return normalized
        if re.match(r"^[A-Za-z][A-Za-z\s'-]{1,48}$", candidate):
            return candidate.title() if candidate.islower() else candidate
    except Exception:
        logger.exception("Country LLM resolution failed for %r", raw)
    return None


async def _resolve_target_country_reply(text: str, runtime_config) -> str | None:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < INTAKE_TEXT_MIN_LENGTH or len(cleaned) > INTAKE_TEXT_MAX_LENGTH:
        return None
    normalized = _normalize_country_name(cleaned)
    if normalized:
        return normalized
    llm_country = await _resolve_country_with_llm(cleaned, runtime_config)
    if llm_country:
        return llm_country
    return _normalize_target_country_reply(text)


def _normalize_score_reply(text: str) -> str | None:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    if _is_skip(cleaned):
        return cleaned
    if len(cleaned) > SCORE_MAX_LENGTH:
        return None
    return cleaned


def _degree_option_by_id(option_id: str) -> dict[str, str] | None:
    normalized = (option_id or "").strip().lower()
    for option in DEGREE_OPTIONS:
        if option["id"].lower() == normalized:
            return option
    return None


def _parse_degree_selection(text: str) -> str | None:
    """Resolve a degree choice from list/button id, label, or numbered fallback."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    lowered = cleaned.lower()
    if lowered.startswith("degree:"):
        option = _degree_option_by_id(lowered)
        return option["label"] if option else None

    if lowered.isdigit():
        index = int(lowered)
        if 1 <= index <= len(DEGREE_OPTIONS):
            return DEGREE_OPTIONS[index - 1]["label"]

    for option in DEGREE_OPTIONS:
        if lowered == option["label"].lower() or lowered == option["short"].lower():
            return option["label"]
        if option["short"].lower() in lowered or option["label"].lower() in lowered:
            return option["label"]

    keyword_map = {
        "bachelor": DEGREE_OPTIONS[0]["label"],
        "master": DEGREE_OPTIONS[1]["label"],
        "integrated": DEGREE_OPTIONS[2]["label"],
        "doctorate": DEGREE_OPTIONS[3]["label"],
        "phd": DEGREE_OPTIONS[3]["label"],
        "doctoral": DEGREE_OPTIONS[3]["label"],
    }
    for keyword, label in keyword_map.items():
        if keyword in lowered:
            return label
    return None


def _normalize_major_reply(text: str) -> str | None:
    return _normalize_intake_text_reply(text)


def _build_degree_list_picker(body: str) -> ListPickerPayload:
    return ListPickerPayload(
        kind="consent",
        body=body,
        button="Choose program",
        items=[
            {
                "id": option["id"],
                "item": option["short"],
                "description": option["description"],
            }
            for option in DEGREE_OPTIONS
        ],
    )


async def _degree_step_reply(
    db: Session,
    lead: Lead,
    runtime_config,
    *,
    task: str,
    incoming_text: str = "",
) -> IntakeReply:
    rendered = await _agent_intake_reply(
        db,
        lead,
        runtime_config,
        task=task,
        incoming_text=incoming_text,
    )
    return IntakeReply(
        text=rendered.text,
        confidence=rendered.confidence,
        list_picker=_build_degree_list_picker(rendered.text),
    )


def _load_target_degree(context: dict[str, Any]) -> str:
    return str(context.get("target_degree") or context.get("target_program") or "").strip()


def _load_target_major(context: dict[str, Any]) -> str:
    explicit = str(context.get("target_major") or "").strip()
    if explicit:
        return explicit
    # In degree → major → country flow, target_program holds the degree label until major is captured.
    if str(context.get("target_degree") or "").strip():
        return ""
    return str(context.get("preferred_course") or "").strip()


def _uses_degree_major_country_flow(context: dict[str, Any]) -> bool:
    return bool(_load_target_degree(context)) and not context.get("awaiting_study_confirmation")


async def process_intake_message(
    db: Session,
    lead: Lead,
    incoming_text: str,
    runtime_config,
) -> IntakeReply:
    from app.services.lead_study_interest import (
        build_target_intake_task,
        hydrate_lead_study_interest,
        lead_has_complete_study_interest,
        resolve_lead_study_interest,
    )

    hydrate_lead_study_interest(db, lead, commit=False)
    step = get_intake_step(lead)
    text = (incoming_text or "").strip()
    first = (lead.full_name or "there").split()[0]

    if step in {INTAKE_STEP_WELCOME, ""} or not getattr(lead, "intake_step", None):
        accepted = _accept_intake_name_reply(text)
        if accepted:
            lead.full_name = accepted
            lead.intake_step = INTAKE_STEP_CURRENT_LOCATION
            db.commit()
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=(
                    f"INTAKE_STEP=LOCATION; Student name saved as {lead.full_name!r}. "
                    "Ask for their current city and country."
                ),
                incoming_text=text,
            )
        lead.intake_step = INTAKE_STEP_FULL_NAME
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=WELCOME; Open the WhatsApp intake and ask for the student's full name.",
            incoming_text=text,
        )

    if step == INTAKE_STEP_FULL_NAME:
        accepted = _accept_intake_name_reply(text)
        if not accepted:
            cleaned_len = len(" ".join((text or "").split()))
            if cleaned_len > NAME_MAX_LENGTH:
                task = (
                    f"INTAKE_STEP=FULL_NAME; Name was too long (max {NAME_MAX_LENGTH} characters). "
                    "Ask once more for the student's name."
                )
            else:
                task = "INTAKE_STEP=FULL_NAME; Ask once more for the student's name."
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=task,
                incoming_text=text,
            )
        lead.full_name = accepted
        lead.intake_step = INTAKE_STEP_CURRENT_LOCATION
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=LOCATION; Student name saved as {lead.full_name!r}. "
                "Ask for their current city and country."
            ),
            incoming_text=text,
        )

    if step == INTAKE_STEP_CURRENT_LOCATION:
        location = _normalize_intake_text_reply(text)
        if not location:
            if len((text or "").strip()) > INTAKE_TEXT_MAX_LENGTH:
                task = (
                    f"INTAKE_STEP=LOCATION; Reply was too long (max {INTAKE_TEXT_MAX_LENGTH} characters). "
                    "Ask again for city and country."
                )
            else:
                task = "INTAKE_STEP=LOCATION; Location answer was too short. Ask again for city and country."
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=task,
                incoming_text=text,
            )
        lead.current_location = location
        lead.intake_step = INTAKE_STEP_TARGET_DEGREE
        db.commit()
        return await _degree_step_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=DEGREE; Location saved as {lead.current_location!r}. "
                "Ask which program (degree) they are targeting and invite them to tap the button below to choose."
            ),
            incoming_text=text,
        )

    if step == INTAKE_STEP_TARGET_DEGREE:
        degree = _parse_degree_selection(text)
        if not degree:
            return await _degree_step_reply(
                db,
                lead,
                runtime_config,
                task=(
                    "INTAKE_STEP=DEGREE; Degree choice was not recognized. "
                    "Ask them to tap the button below and choose one of the four program options."
                ),
                incoming_text=text,
            )
        context = _load_context(lead)
        context["target_degree"] = degree
        context["target_program"] = degree
        lead.intake_context = json.dumps(context)
        lead.intake_step = INTAKE_STEP_TARGET_MAJOR
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=MAJOR; Degree saved as {degree!r}. "
                "Ask which major they are targeting. Give examples like Computer Science or Business Administration."
            ),
            incoming_text=text,
        )

    if step == INTAKE_STEP_TARGET_MAJOR:
        major = _normalize_major_reply(text)
        if not major:
            if len((text or "").strip()) > INTAKE_TEXT_MAX_LENGTH:
                task = (
                    f"INTAKE_STEP=MAJOR; Reply was too long (max {INTAKE_TEXT_MAX_LENGTH} characters). "
                    "Ask again for their intended major with examples like Computer Science or Business Administration."
                )
            else:
                task = (
                    "INTAKE_STEP=MAJOR; Major answer was invalid. "
                    "Ask again for their intended major with examples like Computer Science or Business Administration."
                )
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=task,
                incoming_text=text,
            )
        context = _load_context(lead)
        context["preferred_course"] = major
        context["target_major"] = major
        degree = _load_target_degree(context)
        lead.academic_summary = f"Degree: {degree} | Major: {major}" if degree else f"Major: {major}"
        lead.intake_context = json.dumps(context)
        lead.intake_step = INTAKE_STEP_TARGET_COUNTRY
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=COUNTRY; Major saved as {major!r}. "
                "Ask which country they are targeting with examples like US, UK, JP, AU, NZ."
            ),
            incoming_text=text,
        )

    if step == INTAKE_STEP_TARGET_COUNTRY:
        context = _load_context(lead)
        if _uses_degree_major_country_flow(context):
            country = await _resolve_target_country_reply(text, runtime_config)
            if not country:
                if len((text or "").strip()) > INTAKE_TEXT_MAX_LENGTH:
                    task = (
                        f"INTAKE_STEP=COUNTRY; Reply was too long (max {INTAKE_TEXT_MAX_LENGTH} characters). "
                        "Ask again which country they are targeting with examples US, UK, JP, AU, NZ."
                    )
                else:
                    task = (
                        "INTAKE_STEP=COUNTRY; Country answer was invalid. "
                        "Ask again which country they are targeting with examples US, UK, JP, AU, NZ."
                    )
                return await _agent_intake_reply(
                    db,
                    lead,
                    runtime_config,
                    task=task,
                    incoming_text=text,
                )
            lead.preferred_country = country
            context["target_country"] = country
            degree = _load_target_degree(context)
            major = _load_target_major(context)
            lead.academic_summary = f"Degree: {degree} | Major: {major} | Country: {country}"
            lead.intake_context = json.dumps(context)
            lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
            db.commit()
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=(
                    f"INTAKE_STEP=ENGLISH; Country saved as {country!r}. "
                    "Ask for English test scores (IELTS, TOEFL, PTE, or Duolingo) or invite them to reply skip."
                ),
                incoming_text=text,
            )

        if lead_has_complete_study_interest(lead):
            context = _load_context(lead)
            if not context.get("awaiting_study_confirmation"):
                study = resolve_lead_study_interest(lead)
                _persist_resolved_study_interest(db, lead, study)
                lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
                db.commit()
                return await _agent_intake_reply(
                    db,
                    lead,
                    runtime_config,
                    task=(
                        f"INTAKE_STEP=ENGLISH; Target saved as {study.get('course') or study.get('program')} "
                        f"in {lead.preferred_country}. Ask for English test scores or invite them to reply skip."
                    ),
                    incoming_text=text,
                )

        context = _load_context(lead)
        if context.get("awaiting_study_confirmation"):
            return await _handle_study_plan_confirmation(db, lead, text, runtime_config)

        study = resolve_lead_study_interest(lead)
        _prepare_target_step_prefill(db, lead, study)
        return await _handle_study_plan_whatsapp_collection(db, lead, text, runtime_config)

    if step == INTAKE_STEP_ENGLISH_SCORES:
        if _is_skip(text):
            lead.english_test_scores = "Not provided yet"
        else:
            score = _normalize_score_reply(text)
            if not score:
                return await _agent_intake_reply(
                    db,
                    lead,
                    runtime_config,
                    task=(
                        f"INTAKE_STEP=ENGLISH; Score reply was too long (max {SCORE_MAX_LENGTH} characters). "
                        "Ask for English test scores or invite them to reply skip."
                    ),
                    incoming_text=text,
                )
            lead.english_test_scores = score
        lead.intake_step = INTAKE_STEP_GRE_SCORE
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=GRE; Ask for GRE score or invite them to reply skip.",
            incoming_text=text,
        )

    if step == INTAKE_STEP_GRE_SCORE:
        if _is_skip(text):
            lead.gre_score = "Not provided"
        else:
            score = _normalize_score_reply(text)
            if not score:
                return await _agent_intake_reply(
                    db,
                    lead,
                    runtime_config,
                    task=(
                        f"INTAKE_STEP=GRE; Score reply was too long (max {SCORE_MAX_LENGTH} characters). "
                        "Ask for GRE score or invite them to reply skip."
                    ),
                    incoming_text=text,
                )
            lead.gre_score = score
        lead.intake_step = INTAKE_STEP_GMAT_SCORE
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=GMAT; Ask for GMAT score or invite them to reply skip.",
            incoming_text=text,
        )

    if step == INTAKE_STEP_GMAT_SCORE:
        if _is_skip(text):
            lead.gmat_score = "Not provided"
        else:
            score = _normalize_score_reply(text)
            if not score:
                return await _agent_intake_reply(
                    db,
                    lead,
                    runtime_config,
                    task=(
                        f"INTAKE_STEP=GMAT; Score reply was too long (max {SCORE_MAX_LENGTH} characters). "
                        "Ask for GMAT score or invite them to reply skip."
                    ),
                    incoming_text=text,
                )
            lead.gmat_score = score
        lead.test_scores = (
            f"English: {lead.english_test_scores or 'N/A'} | "
            f"GRE: {lead.gre_score or 'N/A'} | "
            f"GMAT: {lead.gmat_score or 'N/A'}"
        )
        lead.intake_step = INTAKE_STEP_CALL_CONSENT
        db.commit()
        consent_reply = await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=CONSENT; Ask if they want an admissions advisor to call and guide them through applications.",
            incoming_text=text,
        )
        return IntakeReply(
            text=consent_reply.text,
            confidence=consent_reply.confidence,
            quick_reply=_build_call_consent_quick_reply(consent_reply.text),
        )

    if step == INTAKE_STEP_MARKETING_CONSENT:
        marketing_reply = _handle_marketing_consent_selection(
            db,
            lead,
            text,
            (lead.full_name or "there").split()[0],
        )
        if marketing_reply:
            return marketing_reply

    if step == INTAKE_STEP_CALL_CONSENT:
        consent = _parse_yes_no(text)
        if consent is None:
            prompt = await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=CONSENT; Ask them to choose yes or no about an advisor call.",
                incoming_text=text,
            )
            return IntakeReply(
                text=prompt.text,
                confidence=prompt.confidence,
                quick_reply=_build_call_consent_quick_reply(prompt.text),
            )
        lead.wants_consultation_call = consent
        if not consent:
            lead.intake_step = INTAKE_STEP_COMPLETE
            db.commit()
            return await _complete_without_call_reply(db, lead, runtime_config)
        lead.intake_step = INTAKE_STEP_PICK_DATE
        db.commit()
        return await _booking_step_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=PICK_DATE; Student agreed to a consultation. Invite them to choose a consultation date.",
        )

    if step == INTAKE_STEP_PICK_DATE:
        management_reply = handle_post_intake_booking_message(db, lead, text)
        if management_reply:
            return management_reply

        dates = _offered_dates_for_lead(db, lead)
        if not dates:
            dates = _available_dates(db)
            dates = _offered_dates_for_lead(db, lead) or dates
        if not dates:
            lead.intake_step = INTAKE_STEP_COMPLETE
            db.commit()
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=PICK_DATE; No consultation slots are available. Explain an advisor will schedule manually.",
                incoming_text=text,
            )
        selected_date = _resolve_selected_date(text, dates)
        if selected_date is None:
            return await _booking_step_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=PICK_DATE; Ask the student to pick a consultation date from the menu or reply with a list number.",
            )
        slots = _available_times_for_date(db, selected_date)
        if not slots:
            return await _booking_step_reply(
                db,
                lead,
                runtime_config,
                task=(
                    f"INTAKE_STEP=PICK_DATE; No times remain on {selected_date.isoformat()}. "
                    "Ask them to choose another date."
                ),
            )
        context = _load_context(lead)
        context["selected_date"] = selected_date.isoformat()
        context["pending_session_date_label"] = _format_slot_date(selected_date)
        context.pop("pending_session_time_label", None)
        _save_context(db, lead, context)
        lead.intake_step = INTAKE_STEP_PICK_TIME
        db.commit()
        return await _intake_reply_for_time_step(
            db,
            lead,
            runtime_config,
            selected_date,
            task=(
                f"INTAKE_STEP=PICK_TIME; Date {selected_date.isoformat()} selected. "
                "Ask them to choose a consultation time."
            ),
        )

    if step == INTAKE_STEP_PICK_TIME:
        management_reply = handle_post_intake_booking_message(db, lead, text)
        if management_reply:
            return management_reply

        context = _load_context(lead)
        selected_raw = context.get("selected_date")
        if not selected_raw:
            lead.intake_step = INTAKE_STEP_PICK_DATE
            db.commit()
            return await _booking_step_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=PICK_DATE; Restart date selection for the consultation.",
            )
        selected_date = date.fromisoformat(selected_raw)
        slots = _available_times_for_date(db, selected_date)
        if not slots:
            lead.intake_step = INTAKE_STEP_PICK_DATE
            db.commit()
            return await _booking_step_reply(
                db,
                lead,
                runtime_config,
                task=(
                    f"INTAKE_STEP=PICK_DATE; Date {selected_date.isoformat()} is no longer available. "
                    "Ask for another date."
                ),
            )
        choice = _parse_time_selection(text, slots, context)
        if choice is None:
            return await _intake_reply_for_time_step(
                db,
                lead,
                runtime_config,
                selected_date,
                task=(
                    f"INTAKE_STEP=PICK_TIME; Ask the student to choose a time on {selected_date.isoformat()}."
                ),
            )
        return _finalize_consultation_booking(db, lead, selected_date, slots[choice - 1].id, first)

    return await _complete_without_call_reply(db, lead, runtime_config)


async def _complete_without_call_reply(db: Session, lead: Lead, runtime_config) -> IntakeReply:
    context = _load_context(lead)
    rendered = await _agent_intake_reply(
        db,
        lead,
        runtime_config,
        task=(
            "INTAKE_STEP=COMPLETE; Summarize the saved profile details and invite the student to ask admissions questions."
        ),
        extra_context=(
            f"Location: {lead.current_location or 'unknown'}; "
            f"Target country: {lead.preferred_country or 'unknown'}; "
            f"Course: {context.get('preferred_course') or 'unknown'}; "
            f"Test scores: {lead.test_scores or 'unknown'}"
        ),
    )
    body = (rendered.text or "").strip()
    return IntakeReply(
        text=body,
        confidence=rendered.confidence,
        quick_reply=_build_pre_booking_session_quick_reply(body),
    )


async def get_current_step_reply(db: Session, lead: Lead, runtime_config) -> IntakeReply:
    from app.services.lead_study_interest import (
        build_target_intake_task,
        hydrate_lead_study_interest,
        lead_has_complete_study_interest,
        resolve_lead_study_interest,
    )

    hydrate_lead_study_interest(db, lead, commit=False)
    step = get_intake_step(lead)
    if step == INTAKE_STEP_TARGET_COUNTRY:
        context = _load_context(lead)
        if _uses_degree_major_country_flow(context):
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=(
                    "INTAKE_STEP=COUNTRY; Resume intake and ask which country they are targeting. "
                    "Give examples like US, UK, JP, AU, NZ."
                ),
            )
        study = resolve_lead_study_interest(lead)
        if lead_has_complete_study_interest(lead):
            _persist_resolved_study_interest(db, lead, study)
            step = INTAKE_STEP_ENGLISH_SCORES
            lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
            db.commit()
        else:
            _prepare_target_step_prefill(db, lead, study)
            db.commit()
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=build_target_intake_task(lead),
            )
    if step == INTAKE_STEP_TARGET_DEGREE:
        return await _degree_step_reply(
            db,
            lead,
            runtime_config,
            task=(
                "INTAKE_STEP=DEGREE; Resume intake and ask which program (degree) they are targeting. "
                "Invite them to tap the button below to choose."
            ),
        )
    if step == INTAKE_STEP_TARGET_MAJOR:
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                "INTAKE_STEP=MAJOR; Resume intake and ask which major they are targeting. "
                "Give examples like Computer Science or Business Administration."
            ),
        )
    if step in {INTAKE_STEP_WELCOME, INTAKE_STEP_FULL_NAME, ""} or not getattr(lead, "intake_step", None):
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=WELCOME; Resume intake and ask for the student's full name.",
        )
    if step == INTAKE_STEP_PICK_DATE:
        return await _booking_step_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=PICK_DATE; Prompt the student to choose a consultation date.",
        )
    if step == INTAKE_STEP_PICK_TIME:
        context = _load_context(lead)
        selected_raw = context.get("selected_date")
        if selected_raw:
            selected_date = date.fromisoformat(selected_raw)
            return await _intake_reply_for_time_step(
                db,
                lead,
                runtime_config,
                selected_date,
                task=(
                    f"INTAKE_STEP=PICK_TIME; Ask the student to choose a time on {selected_date.isoformat()}."
                ),
            )
        return await _booking_step_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=PICK_DATE; Prompt the student to choose a consultation date.",
        )
    step_tasks = {
        INTAKE_STEP_CURRENT_LOCATION: "INTAKE_STEP=LOCATION; Ask for current city and country.",
        INTAKE_STEP_TARGET_MAJOR: (
            "INTAKE_STEP=MAJOR; Ask which major they are targeting with examples "
            "like Computer Science or Business Administration."
        ),
        INTAKE_STEP_TARGET_COUNTRY: (
            "INTAKE_STEP=COUNTRY; Ask which country they are targeting with examples US, UK, JP, AU, NZ."
        ),
        INTAKE_STEP_ENGLISH_SCORES: "INTAKE_STEP=ENGLISH; Ask for English test scores or skip.",
        INTAKE_STEP_GRE_SCORE: "INTAKE_STEP=GRE; Ask for GRE score or skip.",
        INTAKE_STEP_GMAT_SCORE: "INTAKE_STEP=GMAT; Ask for GMAT score or skip.",
        INTAKE_STEP_CALL_CONSENT: "INTAKE_STEP=CONSENT; Ask if they want an advisor call.",
    }
    if step == INTAKE_STEP_CALL_CONSENT:
        rendered = await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=step_tasks[step],
        )
        return IntakeReply(
            text=rendered.text,
            confidence=rendered.confidence,
            quick_reply=_build_call_consent_quick_reply(rendered.text),
        )
    task = step_tasks.get(
        step,
        "INTAKE_STEP=WELCOME; Continue the WhatsApp intake from the current step.",
    )
    return await _agent_intake_reply(db, lead, runtime_config, task=task)


def _lead_has_real_name(lead: Lead) -> bool:
    """True when the lead already has an acceptable student name (single or full)."""
    return _accept_intake_name_reply((lead.full_name or "").strip()) is not None


def _extract_study_interest(text: str) -> dict[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}

    interest: dict[str, str] = {}

    leading_match = re.match(r"^(\S+)\s+(.+)$", cleaned)
    if leading_match:
        leading_country = _normalize_country_name(leading_match.group(1))
        if leading_country:
            interest["country"] = leading_country
            interest["program"] = leading_match.group(2).strip(" .")
            return interest

    in_country_match = re.search(
        r"^(.{2,80}?)\s+in\s+([A-Za-z][A-Za-z\s\-]{0,40})$",
        cleaned,
        re.IGNORECASE,
    )
    if in_country_match:
        tail = in_country_match.group(2).strip(" .")
        tail_country = _normalize_country_name(tail)
        if tail_country:
            interest["program"] = in_country_match.group(1).strip(" .")
            interest["country"] = tail_country
            return interest

    study_match = re.search(
        r"study(?:\s+abroad)?\s+(.+?)\s+(?:in|at|to)\s+([A-Za-z][A-Za-z\s\-]{1,40})",
        cleaned,
        re.IGNORECASE,
    )
    if study_match:
        tail_country = _normalize_country_name(study_match.group(2).strip(" ."))
        if tail_country:
            interest["program"] = study_match.group(1).strip(" .")
            interest["country"] = tail_country
            return interest

    country_match = re.search(
        r"\b(?:in|to|for)\s+([A-Za-z][A-Za-z\s\-]{0,40})\b",
        cleaned,
        re.IGNORECASE,
    )
    if country_match:
        normalized = _normalize_country_name(country_match.group(1).strip(" ."))
        if normalized:
            interest["country"] = normalized
    if re.search(r"\b(study|course|program|degree|design|fashion|mba|ms|bachelor)\b", cleaned, re.I):
        interest["program"] = cleaned

    standalone_country = _normalize_country_name(cleaned)
    if standalone_country and len(cleaned.split()) <= 3:
        interest["country"] = standalone_country
        return interest

    return interest


def _resolve_intake_restart_step(lead: Lead, incoming_hint: str | None = None) -> str:
    del incoming_hint
    context = _load_context(lead)

    if _lead_has_real_name(lead):
        if not lead.current_location:
            return INTAKE_STEP_CURRENT_LOCATION
        if not _load_target_degree(context):
            return INTAKE_STEP_TARGET_DEGREE
        if not _load_target_major(context):
            return INTAKE_STEP_TARGET_MAJOR
        if not (lead.preferred_country or "").strip():
            return INTAKE_STEP_TARGET_COUNTRY
        return INTAKE_STEP_ENGLISH_SCORES
    return INTAKE_STEP_FULL_NAME


def begin_whatsapp_intake_session(
    db: Session,
    lead: Lead,
    *,
    incoming_hint: str | None = None,
    force_full_restart: bool = False,
) -> None:
    """
    Start (or restart) the structured WhatsApp intake questionnaire.
    """
    from app.services.lead_study_interest import hydrate_lead_study_interest

    hydrate_lead_study_interest(db, lead, commit=False)
    interest = _extract_study_interest(incoming_hint or "")

    if force_full_restart:
        lead.intake_step = INTAKE_STEP_FULL_NAME
        lead.current_location = None
        context = {"study_interest": interest} if interest else {}
        lead.intake_context = json.dumps(context) if context else None
    else:
        context = _load_context(lead)
        if interest:
            context["study_interest"] = interest
        if not _lead_has_real_name(lead):
            lead.intake_step = INTAKE_STEP_FULL_NAME
        else:
            lead.intake_step = _resolve_intake_restart_step(lead, incoming_hint)
        lead.intake_context = json.dumps(context) if context else None

    db.commit()


def _appointment_management_note() -> str:
    return "Use the buttons below to *Reschedule* or *Cancel* your appointment."


def _pre_booking_session_note() -> str:
    return "Tap a button below to *Book Session* or let us know if you're *Not Interested*."


def _build_appointment_management_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[
            {"id": BOOKING_RESCHEDULE_BUTTON_ID, "title": "Reschedule"},
            {"id": BOOKING_CANCEL_BUTTON_ID, "title": "Cancel"},
        ],
    )


def _build_pre_booking_session_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[
            {"id": BOOKING_BOOK_SESSION_BUTTON_ID, "title": "Book Session"},
            {"id": BOOKING_NOT_INTERESTED_BUTTON_ID, "title": "Not Interested"},
        ],
    )


def _build_marketing_consent_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[
            {"id": MARKETING_OPT_IN_BUTTON_ID, "title": "Yes Please"},
            {"id": MARKETING_OPT_OUT_BUTTON_ID, "title": "Do Not Send"},
        ],
    )


def _build_session_management_quick_reply(body: str, lead: Lead) -> QuickReplyPayload:
    if lead.consultation_scheduled_at:
        return _build_appointment_management_quick_reply(body)
    return _build_pre_booking_session_quick_reply(body)


def build_appointment_management_reply(message: str | None = None) -> IntakeReply:
    """Follow-up reply with reschedule/cancel quick-reply buttons."""
    body = message or (
        "You can *reschedule* or *cancel* your session anytime.\n"
        "*Tap a button below.*"
    )
    return IntakeReply(
        text=body,
        quick_reply=_build_appointment_management_quick_reply(body),
    )


def _build_reschedule_only_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[{"id": BOOKING_RESCHEDULE_BUTTON_ID, "title": "Reschedule"}],
    )


def _build_book_session_only_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[{"id": BOOKING_BOOK_SESSION_BUTTON_ID, "title": "Book Session"}],
    )


def _is_awaiting_marketing_consent(lead: Lead) -> bool:
    if get_intake_step(lead) == INTAKE_STEP_MARKETING_CONSENT:
        return True
    context = _load_context(lead)
    return bool(context.get("awaiting_marketing_consent"))


def _begin_marketing_consent_flow(db: Session, lead: Lead, first: str) -> IntakeReply:
    context = _load_context(lead)
    context["awaiting_marketing_consent"] = True
    _save_context(db, lead, context)
    lead.intake_step = INTAKE_STEP_MARKETING_CONSENT
    lead.wants_consultation_call = False
    db.commit()
    body = (
        f"Noted, {first}. Would you at least like to receive *timely information* "
        "on our offerings?"
    )
    return IntakeReply(
        text=body,
        quick_reply=_build_marketing_consent_quick_reply(body),
    )


def _handle_marketing_consent_selection(
    db: Session,
    lead: Lead,
    incoming_text: str,
    first: str,
) -> IntakeReply | None:
    if not _is_awaiting_marketing_consent(lead):
        return None

    if is_marketing_opt_in_command(incoming_text):
        from app.services.student_status_service import on_marketing_opt_in_selected

        context = _load_context(lead)
        context.pop("awaiting_marketing_consent", None)
        _save_context(db, lead, context)
        lead.intake_step = INTAKE_STEP_COMPLETE
        on_marketing_opt_in_selected(db, lead)
        db.commit()
        db.refresh(lead)
        return IntakeReply(
            text=(
                f"Great, {first}! *We'll share timely updates* about our offerings with you."
            )
        )

    if is_marketing_opt_out_command(incoming_text):
        from app.services.student_status_service import on_marketing_opt_out_selected

        context = _load_context(lead)
        context.pop("awaiting_marketing_consent", None)
        _save_context(db, lead, context)
        lead.intake_step = INTAKE_STEP_COMPLETE
        on_marketing_opt_out_selected(db, lead)
        db.commit()
        db.refresh(lead)
        return IntakeReply(
            text=f"Understood, {first}. *We won't send you any further messages.*"
        )

    body = (
        f"Please tap *Yes Please* or *Do Not Send*, {first}, "
        "so we know whether to share updates with you."
    )
    return IntakeReply(
        text=body,
        quick_reply=_build_marketing_consent_quick_reply(body),
    )


def _begin_reschedule_booking(db: Session, lead: Lead) -> None:
    """Start reschedule flow without clearing the confirmed session from the UI."""
    context = _load_context(lead)
    context["reschedule_in_progress"] = True
    _clear_booking_selection_context(context)
    context.pop("pending_session_date_label", None)
    context.pop("pending_session_time_label", None)
    _save_context(db, lead, context)


def _clear_booking_selection_context(context: dict[str, Any]) -> None:
    context.pop("selected_date", None)
    context.pop("time_slot_ids", None)
    context.pop("date_options", None)
    context.pop("pending_session_date_label", None)
    context.pop("pending_session_time_label", None)
    context.pop("reschedule_in_progress", None)


def release_lead_consultation_slot(db: Session, lead: Lead) -> None:
    from app.services.counselling_service import cancel_active_counselling_bookings_for_lead

    slot = db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).first()
    if slot:
        slot.lead_id = None
    lead.consultation_scheduled_at = None
    lead.calendar_booking_id = None
    cancel_active_counselling_bookings_for_lead(db, lead.id, commit=False)
    db.commit()


def _reset_booking_intake_context(db: Session, lead: Lead) -> None:
    context = _load_context(lead)
    preferred_course = context.get("preferred_course")
    _clear_booking_selection_context(context)
    if preferred_course:
        context["preferred_course"] = preferred_course
    _save_context(db, lead, context)


def format_booking_summary(
    lead: Lead,
    *,
    include_management_prompt: bool = True,
    db: Session | None = None,
) -> str:
    first = (lead.full_name or "there").split()[0]
    scheduled = lead.consultation_scheduled_at
    if not scheduled and db is not None:
        booking = _get_active_consultation_booking(db, lead)
        if booking:
            scheduled = booking.scheduled_time
    if not scheduled:
        if lead.wants_consultation_call:
            return (
                f"{first}, you don't have a consultation slot booked yet.\n"
                "Tap *Book Session* below to pick a date and time."
            )
        return (
            f"{first}, you haven't booked an advisor call.\n"
            "Tap *Book Session* below if you'd like to schedule one."
        )
    slot_day = scheduled.date()
    slot_time = scheduled.strftime("%H:%M")
    summary = (
        f"{first}, your consultation is scheduled for "
        f"*{_format_slot_date(slot_day)}* at *{_format_slot_time(slot_time)}*."
    )
    if include_management_prompt:
        return f"{summary}\n\n{_appointment_management_note()}"
    return summary


def is_booking_management_message(text: str, lead: Lead, flow_data: str | None = None) -> bool:
    if flow_data:
        return True
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if get_intake_step(lead) in {INTAKE_STEP_PICK_DATE, INTAKE_STEP_PICK_TIME}:
        return True
    if not is_intake_complete(lead):
        return False
    if RESCHEDULE_PATTERN.search(cleaned):
        return True
    if is_cancel_command(cleaned):
        return True
    if BOOKING_INFO_PATTERN.search(cleaned):
        return True
    if lead.consultation_scheduled_at and _parse_choice_number(cleaned, 10):
        return False
    return False


def handle_post_intake_booking_message(db: Session, lead: Lead, incoming_text: str) -> IntakeReply | None:
    text = _normalize_booking_button_reply((incoming_text or "").strip())
    step = get_intake_step(lead)
    if step in {INTAKE_STEP_PICK_DATE, INTAKE_STEP_PICK_TIME} and not is_post_intake_management_command(
        text
    ):
        return None

    command_text = _strip_booking_markdown(text)
    lowered = command_text.lower()
    first = (lead.full_name or "there").split()[0]

    marketing_reply = _handle_marketing_consent_selection(db, lead, incoming_text, first)
    if marketing_reply:
        return marketing_reply

    if is_not_interested_command(text):
        if _lead_has_active_consultation_booking(db, lead):
            return IntakeReply(
                text=(
                    f"{first}, you already have a *consultation scheduled*.\n"
                    "Tap *Cancel* below if you'd like to cancel it."
                ),
                quick_reply=_build_appointment_management_quick_reply(
                    _appointment_management_note()
                ),
            )
        return _begin_marketing_consent_flow(db, lead, first)

    if THANKS_PATTERN.match(text):
        if _lead_has_active_consultation_booking(db, lead):
            return IntakeReply(
                text=(
                    f"You're welcome, {first}! *We'll speak with you at your scheduled time.* 👋"
                )
            )
        return IntakeReply(
            text=f"You're welcome, {first}! Feel free to message anytime if you have questions."
        )

    if is_cancel_command(text):
        had_booking = _lead_has_active_consultation_booking(db, lead)
        release_lead_consultation_slot(db, lead)
        _reset_booking_intake_context(db, lead)
        lead.intake_step = INTAKE_STEP_COMPLETE
        lead.wants_consultation_call = True
        db.commit()
        db.refresh(lead)
        from app.services.student_status_service import on_session_cancelled

        on_session_cancelled(
            db,
            lead,
            source="whatsapp_cancel",
            had_active_booking=had_booking,
        )
        if had_booking:
            return IntakeReply(
                text=f"Done, {first}. *Your consultation appointment has been cancelled.*",
                quick_reply=_build_reschedule_only_quick_reply(
                    "*Would you like to book a new consultation slot?*"
                ),
            )
        return IntakeReply(
            text=(
                f"{first}, you don't have a consultation booked yet.\n"
                "Tap *Book Session* to schedule one, or *Not Interested* if you'd prefer not to."
            ),
            quick_reply=_build_pre_booking_session_quick_reply(
                "Choose an option below."
            ),
        )

    if is_reschedule_command(text):
        had_booking = _lead_has_active_consultation_booking(db, lead)
        previous_summary = (
            format_booking_summary(lead, db=db)
            if had_booking
            else f"{first}, let's schedule your consultation."
        )
        _begin_reschedule_booking(db, lead)
        lead.intake_step = INTAKE_STEP_PICK_DATE
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        lead.wants_consultation_call = True
        db.commit()
        db.refresh(lead)
        from app.services.student_status_service import on_session_rescheduled

        on_session_rescheduled(
            db,
            lead,
            source="whatsapp_reschedule",
            had_active_booking=had_booking,
        )
        return _booking_step_reply_sync(
            db,
            lead,
            (
                f"{previous_summary}\n\n"
                "*Tap below* to choose a new consultation date."
            ),
        )

    if BOOKING_INFO_PATTERN.search(text):
        if _lead_has_active_consultation_booking(db, lead):
            return IntakeReply(
                text=format_booking_summary(lead, include_management_prompt=False, db=db),
                quick_reply=_build_appointment_management_quick_reply(_appointment_management_note()),
            )
        return IntakeReply(
            text=format_booking_summary(lead, include_management_prompt=False, db=db),
            quick_reply=_build_pre_booking_session_quick_reply(_pre_booking_session_note()),
        )

    return None


def _normalize_time_label(label: str) -> str:
    return re.sub(r"[^0-9:a-z]", "", label.strip().lower())


def _offered_dates_for_lead(db: Session, lead: Lead, *, limit: int = 8) -> list[date]:
    """Dates the lead was shown in the date picker (stable across webhook turns)."""
    context = _load_context(lead)
    offered: list[date] = []
    for raw in context.get("date_options") or []:
        try:
            offered.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    if offered:
        return offered
    return _available_dates(db, limit=limit)


def _resolve_selected_date(text: str, dates: list[date]) -> date | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered.startswith("date:"):
        try:
            return date.fromisoformat(lowered.split(":", 1)[1])
        except ValueError:
            pass

    choice = _parse_date_selection(text, dates)
    if choice is not None:
        return dates[choice - 1]

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", cleaned)
    if iso_match:
        try:
            selected = date.fromisoformat(iso_match.group(1))
            if selected in dates:
                return selected
        except ValueError:
            pass
    return None


def _normalize_date_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.strip().lower())


def _parse_date_selection(text: str, dates: list[date]) -> int | None:
    cleaned = text.strip()
    lowered = cleaned.lower()

    if lowered.startswith("date:"):
        try:
            selected = date.fromisoformat(lowered.split(":", 1)[1])
            for index, slot_day in enumerate(dates, start=1):
                if slot_day == selected:
                    return index
        except ValueError:
            pass
        return None

    choice = _parse_choice_number(text, len(dates))
    if choice is not None:
        return choice

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", cleaned)
    if iso_match:
        try:
            selected = date.fromisoformat(iso_match.group(1))
            for index, slot_day in enumerate(dates, start=1):
                if slot_day == selected:
                    return index
        except ValueError:
            pass

    for index, slot_day in enumerate(dates, start=1):
        label = _format_slot_date(slot_day)
        if cleaned == label or lowered == label.lower():
            return index
        if _normalize_date_label(cleaned) == _normalize_date_label(label):
            return index
    return None


def _parse_time_selection(text: str, slots: list[ConsultationSlot], context: dict[str, Any] | None = None) -> int | None:
    cleaned = text.strip()
    lowered = cleaned.lower()

    if lowered.startswith("time:"):
        try:
            slot_id = int(lowered.split(":", 1)[1])
            for index, slot in enumerate(slots, start=1):
                if slot.id == slot_id:
                    return index
        except ValueError:
            pass
        return None

    choice = _parse_choice_number(text, len(slots))
    if choice is not None:
        return choice

    if cleaned.isdigit():
        slot_id = int(cleaned)
        for index, slot in enumerate(slots, start=1):
            if slot.id == slot_id:
                return index

    context = context or {}
    for index, slot_id in enumerate(context.get("time_slot_ids") or [], start=1):
        if index <= len(slots) and slots[index - 1].id == slot_id:
            if cleaned == str(slot_id) or lowered == f"time:{slot_id}":
                return index

    for index, slot in enumerate(slots, start=1):
        label = _format_slot_time(slot.slot_time)
        if cleaned == label or lowered == label.lower():
            return index
        if _normalize_time_label(cleaned) == _normalize_time_label(label):
            return index
    return None


def _finalize_consultation_booking(
    db: Session,
    lead: Lead,
    selected_date: date,
    slot_id: int,
    first_name: str,
) -> IntakeReply:
    if get_intake_step(lead) == INTAKE_STEP_COMPLETE and lead.consultation_scheduled_at:
        existing_slot = (
            db.query(ConsultationSlot)
            .filter(ConsultationSlot.lead_id == lead.id)
            .first()
        )
        if existing_slot:
            return IntakeReply(text="", suppress_outbound=True)

    release_lead_consultation_slot(db, lead)

    slot = (
        db.query(ConsultationSlot)
        .filter(
            ConsultationSlot.id == slot_id,
            ConsultationSlot.slot_date == selected_date,
            ConsultationSlot.lead_id.is_(None),
        )
        .first()
    )
    if not slot:
        lead.intake_step = INTAKE_STEP_PICK_TIME
        db.commit()
        return IntakeReply(
            text="*That time slot is no longer available.* Please choose another time.",
            quick_reply=_build_time_picker_payload(db, lead, selected_date),
        )

    slot.lead_id = lead.id
    scheduled = datetime.combine(
        slot.slot_date,
        datetime.strptime(_normalize_slot_time(slot.slot_time), "%H:%M").time(),
    )
    lead.consultation_scheduled_at = scheduled
    lead.calendar_booking_id = f"NEXUS-SLOT-{slot.id}"
    lead.intake_step = INTAKE_STEP_COMPLETE
    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    preserved_context = _load_context(lead)
    preferred_course = preserved_context.get("preferred_course")
    lead.intake_context = (
        json.dumps({"preferred_course": preferred_course}) if preferred_course else None
    )

    from app.services.counselling_service import upsert_pending_booking_for_lead

    from app.services.student_status_service import on_session_booked

    on_session_booked(db, lead)

    try:
        upsert_pending_booking_for_lead(db, lead, scheduled, commit=False)
    except HTTPException as exc:
        slot.lead_id = None
        lead.consultation_scheduled_at = None
        lead.calendar_booking_id = None
        lead.intake_step = INTAKE_STEP_PICK_TIME
        db.commit()
        return IntakeReply(
            text=f"{exc.detail} Please choose another time.",
            quick_reply=_build_time_picker_payload(db, lead, selected_date),
        )

    db.commit()

    confirmation = (
        f"Perfect, {first_name}! ✅ *Your consultation is confirmed* for "
        f"*{_format_slot_date(slot.slot_date)}* at *{_format_slot_time(slot.slot_time)}*.\n\n"
        f"An *{BRAND_NAME}* admissions advisor will call you at that time."
    )
    return IntakeReply(
        text=confirmation,
        quick_reply=_build_appointment_management_quick_reply(_appointment_management_note()),
    )


def _build_time_picker_payload(db: Session, lead: Lead, slot_day: date) -> QuickReplyPayload:
    slots = _available_times_for_date(db, slot_day)
    context = _load_context(lead)
    context["selected_date"] = slot_day.isoformat()
    context["time_slot_ids"] = [slot.id for slot in slots]
    _save_context(db, lead, context)
    actions = [
        {
            "id": f"time:{slot.id}",
            "title": _format_slot_time(slot.slot_time),
        }
        for slot in slots[:3]
    ]
    return QuickReplyPayload(
        kind="time",
        body=f"Tap a time for {_format_slot_date(slot_day)}:",
        actions=actions,
    )


def _build_time_list_picker_payload(db: Session, lead: Lead, slot_day: date) -> ListPickerPayload:
    slots = _available_times_for_date(db, slot_day)
    context = _load_context(lead)
    context["selected_date"] = slot_day.isoformat()
    context["time_slot_ids"] = [slot.id for slot in slots]
    _save_context(db, lead, context)
    items = [
        {
            "id": f"time:{slot.id}",
            "item": _format_slot_time(slot.slot_time),
            "description": "Consultation slot",
        }
        for slot in slots[:10]
    ]
    return ListPickerPayload(
        kind="time",
        body=f"*Tap below* to choose a time for *{_format_slot_date(slot_day)}*.",
        button="Choose time",
        items=items,
    )


async def _booking_step_reply(
    db: Session,
    lead: Lead,
    runtime_config,
    task: str,
) -> IntakeReply:
    rendered = await _agent_intake_reply(db, lead, runtime_config, task=task)
    picker = _build_date_picker_payload(db, lead)
    flow = _build_booking_flow_payload(lead)
    from app.services.messaging import PROVIDER_WHATSAPP, get_active_provider

    if flow and get_active_provider() != PROVIDER_WHATSAPP:
        return IntakeReply(
            text=rendered.text,
            confidence=rendered.confidence,
            whatsapp_flow=flow,
        )
    return IntakeReply(
        text=rendered.text,
        confidence=rendered.confidence,
        list_picker=picker,
    )


async def _intake_reply_for_time_step(
    db: Session,
    lead: Lead,
    runtime_config,
    selected_date: date,
    *,
    task: str,
) -> IntakeReply:
    slots = _available_times_for_date(db, selected_date)
    rendered = await _agent_intake_reply(db, lead, runtime_config, task=task)
    message = rendered.text
    if not slots:
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=PICK_TIME; No open consultation times remain on {selected_date.isoformat()}. "
                "Ask the student to choose another consultation date."
            ),
        )
    if len(slots) <= 3:
        picker = _build_time_picker_payload(db, lead, selected_date)
        picker = QuickReplyPayload(
            kind=picker.kind,
            body=message,
            actions=picker.actions,
        )
        return IntakeReply(text=message, confidence=rendered.confidence, quick_reply=picker)
    picker = _build_time_list_picker_payload(db, lead, selected_date)
    picker = ListPickerPayload(
        kind=picker.kind,
        body=message,
        button=picker.button,
        items=picker.items,
    )
    return IntakeReply(text=message, confidence=rendered.confidence, list_picker=picker)


def _build_call_consent_quick_reply(body: str) -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body=body,
        actions=[
            {"id": "yes", "title": "Yes, please"},
            {"id": "no", "title": "No thanks"},
        ],
    )


def _build_booking_flow_payload(lead: Lead) -> FlowPayload | None:
    flow_id = get_whatsapp_flow_id()
    if not is_whatsapp_flow_enabled() or not flow_id:
        return None
    return FlowPayload(
        body="*Tap below* to open the calendar and book your consultation.",
        flow_token=build_flow_token(lead.id),
        flow_id=flow_id,
        button="Book consultation",
    )


def _booking_step_reply_sync(db: Session, lead: Lead, text: str) -> IntakeReply:
    picker = _build_date_picker_payload(db, lead)
    flow = _build_booking_flow_payload(lead)
    from app.services.messaging import PROVIDER_WHATSAPP, get_active_provider

    if flow and get_active_provider() != PROVIDER_WHATSAPP:
        return IntakeReply(text=text, whatsapp_flow=flow)
    return IntakeReply(text=text, list_picker=picker)


def _build_date_picker_payload(db: Session, lead: Lead) -> ListPickerPayload:
    dates = _available_dates(db)
    context = _load_context(lead)
    context["date_options"] = [slot_day.isoformat() for slot_day in dates]
    _save_context(db, lead, context)
    items = [
        {
            "id": f"date:{slot_day.isoformat()}",
            "item": _format_slot_date(slot_day),
            "description": "Tap to select this date",
        }
        for slot_day in dates
    ]
    return ListPickerPayload(
        kind="date",
        body="*Tap the button below* to open the date menu and pick your *consultation day*.",
        button="Choose date",
        items=items,
    )


def process_flow_completion(db: Session, lead: Lead, flow_data_raw: str) -> IntakeReply | None:
    from app.services.whatsapp_flow_booking import complete_booking_from_flow, parse_flow_completion_payload

    try:
        payload = parse_flow_completion_payload(flow_data_raw)
    except (json.JSONDecodeError, TypeError):
        return None

    selected_date = payload.get("selected_date")
    selected_time = payload.get("selected_time")
    if not selected_date or not selected_time:
        return None

    try:
        return complete_booking_from_flow(db, lead, str(selected_date), str(selected_time))
    except ValueError as exc:
        return IntakeReply(text=f"Sorry, I couldn't complete that booking: {exc}")


async def get_current_step_prompt(db: Session, lead: Lead, runtime_config) -> str:
    reply = await get_current_step_reply(db, lead, runtime_config)
    return reply.text


INTAKE_STEP_LABELS: dict[str, str] = {
    INTAKE_STEP_WELCOME: "Welcome",
    INTAKE_STEP_FULL_NAME: "Full name",
    INTAKE_STEP_CURRENT_LOCATION: "Current location",
    INTAKE_STEP_TARGET_DEGREE: "Target degree",
    INTAKE_STEP_TARGET_MAJOR: "Target major",
    INTAKE_STEP_TARGET_COUNTRY: "Target country",
    INTAKE_STEP_ENGLISH_SCORES: "English test scores",
    INTAKE_STEP_GRE_SCORE: "GRE score",
    INTAKE_STEP_GMAT_SCORE: "GMAT score",
    INTAKE_STEP_CALL_CONSENT: "Advisor call",
    INTAKE_STEP_PICK_DATE: "Pick consultation date",
    INTAKE_STEP_PICK_TIME: "Pick consultation time",
    INTAKE_STEP_MARKETING_CONSENT: "Marketing consent",
    INTAKE_STEP_COMPLETE: "Intake complete",
}

INTAKE_STEP_ORDER: list[str] = [
    INTAKE_STEP_FULL_NAME,
    INTAKE_STEP_CURRENT_LOCATION,
    INTAKE_STEP_TARGET_DEGREE,
    INTAKE_STEP_TARGET_MAJOR,
    INTAKE_STEP_TARGET_COUNTRY,
    INTAKE_STEP_ENGLISH_SCORES,
    INTAKE_STEP_GRE_SCORE,
    INTAKE_STEP_GMAT_SCORE,
    INTAKE_STEP_CALL_CONSENT,
    INTAKE_STEP_PICK_DATE,
    INTAKE_STEP_PICK_TIME,
    INTAKE_STEP_COMPLETE,
]


def format_inbound_booking_selection(db: Session, text: str) -> str:
    """Turn Meta list/button ids into readable chat text for staff-facing history."""
    cleaned = (text or "").strip()
    lowered = cleaned.lower()
    if lowered.startswith("date:"):
        try:
            slot_day = date.fromisoformat(lowered.split(":", 1)[1])
            return f"Selected {_format_slot_date(slot_day)}"
        except ValueError:
            return cleaned
    if lowered.startswith("time:"):
        try:
            slot_id = int(lowered.split(":", 1)[1])
            slot = db.query(ConsultationSlot).filter(ConsultationSlot.id == slot_id).first()
            if slot:
                return f"Selected {_format_slot_time(slot.slot_time)}"
        except ValueError:
            return cleaned
    if lowered == BOOKING_RESCHEDULE_BUTTON_ID:
        return "Reschedule appointment"
    if lowered == BOOKING_BOOK_SESSION_BUTTON_ID:
        return "Book session"
    if lowered == BOOKING_NOT_INTERESTED_BUTTON_ID:
        return "Not interested"
    if lowered == BOOKING_CANCEL_BUTTON_ID:
        return "Cancel appointment"
    if lowered == MARKETING_OPT_IN_BUTTON_ID:
        return "Yes please (marketing updates)"
    if lowered == MARKETING_OPT_OUT_BUTTON_ID:
        return "Do not send (marketing updates)"
    if lowered.startswith("degree:"):
        option = _degree_option_by_id(lowered)
        if option:
            return f"Selected {option['label']}"
    return cleaned


def build_intake_profile_summary(
    lead: Lead,
    db: Session | None = None,
    *,
    refresh_lead: bool = True,
    include_booking_options: bool = True,
    include_session_fields: bool = True,
) -> dict[str, Any]:
    from app.services.lead_study_interest import study_interest_profile_fields

    step = get_intake_step(lead)
    context = _load_context(lead)
    study_fields = study_interest_profile_fields(lead)
    summary: dict[str, Any] = {
        "intake_step": step,
        "intake_step_label": INTAKE_STEP_LABELS.get(step, step.replace("_", " ").title()),
        "intake_complete": is_intake_complete(lead),
        "current_location": getattr(lead, "current_location", None),
        "preferred_country": study_fields.get("preferred_country") or lead.preferred_country,
        "preferred_course": _load_target_major(context) or None,
        "target_program": study_fields.get("target_program")
        or context.get("target_degree")
        or context.get("target_program"),
        "target_degree": _load_target_degree(context) or None,
        "target_major": _load_target_major(context) or None,
        "study_interest_complete": study_fields.get("study_interest_complete"),
        "english_test_scores": getattr(lead, "english_test_scores", None),
        "gre_score": getattr(lead, "gre_score", None),
        "gmat_score": getattr(lead, "gmat_score", None),
        "test_scores": lead.test_scores,
        "wants_consultation_call": getattr(lead, "wants_consultation_call", None),
        "consultation_scheduled_at": (
            lead.consultation_scheduled_at.isoformat()
            if getattr(lead, "consultation_scheduled_at", None)
            else None
        ),
        "calendar_booking_id": lead.calendar_booking_id,
        "available_consultation_dates": [],
        "available_consultation_times": [],
        "selected_consultation_date": context.get("selected_date"),
    }

    if include_session_fields:
        summary.update(
            _build_consultation_session_profile_fields(db, lead, step=step, context=context)
        )

    if db is None:
        return summary

    if refresh_lead:
        db.refresh(lead)
        step = get_intake_step(lead)
        context = _load_context(lead)
        summary["consultation_scheduled_at"] = (
            lead.consultation_scheduled_at.isoformat()
            if getattr(lead, "consultation_scheduled_at", None)
            else None
        )

    if not include_booking_options:
        return summary

    if step == INTAKE_STEP_PICK_DATE:
        dates = _available_dates(db)
        summary["available_consultation_dates"] = [
            {"date": slot_day.isoformat(), "label": _format_slot_date(slot_day)} for slot_day in dates
        ]

    if step == INTAKE_STEP_PICK_TIME:
        context = _load_context(lead)
        selected_raw = context.get("selected_date")
        if selected_raw:
            selected_date = date.fromisoformat(selected_raw)
            slots = _available_times_for_date(db, selected_date)
            summary["selected_consultation_date"] = selected_raw
            summary["available_consultation_times"] = [
                {"time": slot.slot_time, "label": _format_slot_time(slot.slot_time)} for slot in slots
            ]

    return summary
