from __future__ import annotations

import json
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

INTAKE_STEP_WELCOME = "WELCOME"
INTAKE_STEP_FULL_NAME = "FULL_NAME"
INTAKE_STEP_CURRENT_LOCATION = "CURRENT_LOCATION"
INTAKE_STEP_TARGET_COUNTRY = "TARGET_COUNTRY"
INTAKE_STEP_ENGLISH_SCORES = "ENGLISH_SCORES"
INTAKE_STEP_GRE_SCORE = "GRE_SCORE"
INTAKE_STEP_GMAT_SCORE = "GMAT_SCORE"
INTAKE_STEP_CALL_CONSENT = "CALL_CONSENT"
INTAKE_STEP_PICK_DATE = "PICK_DATE"
INTAKE_STEP_PICK_TIME = "PICK_TIME"
INTAKE_STEP_COMPLETE = "COMPLETE"

DEFAULT_SLOT_TIMES = ("10:00", "14:00", "16:00")

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


@dataclass
class IntakeReply:
    text: str
    list_picker: ListPickerPayload | None = None
    quick_reply: QuickReplyPayload | None = None
    whatsapp_flow: FlowPayload | None = None


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


def get_intake_step(lead: Lead) -> str:
    step = getattr(lead, "intake_step", None)
    return step or INTAKE_STEP_WELCOME


def is_intake_complete(lead: Lead) -> bool:
    return get_intake_step(lead) == INTAKE_STEP_COMPLETE


def ensure_consultation_slots(db: Session, days_ahead: int = 21) -> None:
    dedupe_consultation_slots(db)
    today = date.today()
    for offset in range(1, days_ahead + 1):
        slot_day = today + timedelta(days=offset)
        if not is_bookable_day(db, slot_day):
            continue
        for slot_time in DEFAULT_SLOT_TIMES:
            normalized_time = _normalize_slot_time(slot_time)
            exists = (
                db.query(ConsultationSlot.id)
                .filter(
                    ConsultationSlot.slot_date == slot_day,
                    ConsultationSlot.slot_time == normalized_time,
                )
                .first()
            )
            if exists:
                continue
            db.add(ConsultationSlot(slot_date=slot_day, slot_time=normalized_time))
    db.commit()


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


def _available_dates(db: Session, limit: int = 8) -> list[date]:
    rows = (
        db.query(ConsultationSlot.slot_date)
        .filter(ConsultationSlot.lead_id.is_(None), ConsultationSlot.slot_date >= date.today())
        .distinct()
        .order_by(ConsultationSlot.slot_date.asc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if is_bookable_day(db, row[0])]


def _available_times_for_date(db: Session, slot_day: date) -> list[ConsultationSlot]:
    if not is_bookable_day(db, slot_day):
        return []
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
    match = re.search(r"\b(\d{1,2})\b", text.strip())
    if not match:
        return None
    choice = int(match.group(1))
    if 1 <= choice <= max_option:
        return choice
    return None


def _is_skip(text: str) -> bool:
    return text.strip().lower() in {"skip", "na", "n/a", "none", "no", "not yet", "don't have", "dont have"}


def _looks_like_full_name(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 3:
        return False
    if cleaned.lower().startswith("whatsapp contact"):
        return False
    return bool(re.search(r"[a-zA-Z]", cleaned))


def start_intake_message() -> str:
    return (
        "Hello! 👋 I'm the Nexus Admissions AI Assistant.\n\n"
        "I'll ask a few quick questions to understand your profile and help with your admission journey.\n\n"
        "Let's begin — what is your full name?"
    )


def release_lead_consultation_slot(db: Session, lead: Lead) -> None:
    from app.services.counselling_service import cancel_active_counselling_bookings_for_lead

    slot = db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).first()
    if slot:
        slot.lead_id = None
    lead.consultation_scheduled_at = None
    lead.calendar_booking_id = None
    cancel_active_counselling_bookings_for_lead(db, lead.id, commit=False)
    db.commit()


def format_booking_summary(lead: Lead) -> str:
    first = (lead.full_name or "there").split()[0]
    if not lead.consultation_scheduled_at:
        if lead.wants_consultation_call:
            return (
                f"{first}, you don't have a consultation slot booked yet. "
                "Reply *reschedule* or *change slot* to pick a date and time."
            )
        return f"{first}, you haven't booked an advisor call. Reply *reschedule* if you'd like to schedule one."

    scheduled = lead.consultation_scheduled_at
    slot_day = scheduled.date()
    slot_time = scheduled.strftime("%H:%M")
    return (
        f"{first}, your consultation is scheduled for "
        f"{_format_slot_date(slot_day)} at {_format_slot_time(slot_time)}.\n\n"
        "Reply *change slot* or *reschedule* if you need a different date or time."
    )


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
    if BOOKING_INFO_PATTERN.search(cleaned):
        return True
    if lead.consultation_scheduled_at and _parse_choice_number(cleaned, 10):
        return False
    return bool(lead.consultation_scheduled_at and lead.wants_consultation_call)


def handle_post_intake_booking_message(db: Session, lead: Lead, incoming_text: str) -> IntakeReply | None:
    if get_intake_step(lead) in {INTAKE_STEP_PICK_DATE, INTAKE_STEP_PICK_TIME}:
        return None

    text = (incoming_text or "").strip()
    if RESCHEDULE_PATTERN.search(text) or text.lower() in {"reschedule", "change slot", "change appointment"}:
        release_lead_consultation_slot(db, lead)
        lead.intake_step = INTAKE_STEP_PICK_DATE
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        lead.wants_consultation_call = True
        db.commit()
        picker = _build_date_picker_payload(db, lead)
        flow = _build_booking_flow_payload(lead)
        return IntakeReply(
            text=(
                f"No problem, {(lead.full_name or 'there').split()[0]}! "
                "Let's pick a new consultation date."
            ),
            list_picker=None if flow else picker,
            whatsapp_flow=flow,
        )

    if BOOKING_INFO_PATTERN.search(text):
        return IntakeReply(text=format_booking_summary(lead))

    return None


def _normalize_time_label(label: str) -> str:
    return re.sub(r"[^0-9:a-z]", "", label.strip().lower())


def _normalize_date_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.strip().lower())


def _parse_date_selection(text: str, dates: list[date]) -> int | None:
    choice = _parse_choice_number(text, len(dates))
    if choice is not None:
        return choice

    cleaned = text.strip()
    lowered = cleaned.lower()

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", cleaned)
    if iso_match:
        try:
            selected = date.fromisoformat(iso_match.group(1))
            for index, slot_day in enumerate(dates, start=1):
                if slot_day == selected:
                    return index
        except ValueError:
            pass

    if lowered.startswith("date:"):
        try:
            selected = date.fromisoformat(lowered.split(":", 1)[1])
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
    choice = _parse_choice_number(text, len(slots))
    if choice is not None:
        return choice

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
            text="That time slot is no longer available. Please choose another time.",
            quick_reply=_build_time_picker_payload(db, lead, selected_date),
        )

    slot.lead_id = lead.id
    scheduled = datetime.combine(
        selected_date,
        datetime.strptime(_normalize_slot_time(slot.slot_time), "%H:%M").time(),
    )
    lead.consultation_scheduled_at = scheduled
    lead.calendar_booking_id = f"NEXUS-SLOT-{slot.id}"
    lead.intake_step = INTAKE_STEP_COMPLETE
    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    lead.intake_context = None

    from app.services.counselling_service import upsert_pending_booking_for_lead

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
        f"Perfect, {first_name}! ✅ Your consultation is confirmed for "
        f"{_format_slot_date(selected_date)} at {_format_slot_time(slot.slot_time)}.\n\n"
        "A Nexus advisor will call you at that time. "
        "Reply *change slot* to reschedule or *when is my appointment* to check your booking."
    )
    return IntakeReply(text=confirmation)


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


def _build_call_consent_quick_reply() -> QuickReplyPayload:
    return QuickReplyPayload(
        kind="consent",
        body="Would you like a Nexus admissions advisor to call and guide you through the application process?",
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
        body="Tap below to open the calendar and book your consultation.",
        flow_token=build_flow_token(lead.id),
        flow_id=flow_id,
        button="Book consultation",
    )


def _booking_step_reply(db: Session, lead: Lead, text: str) -> IntakeReply:
    flow = _build_booking_flow_payload(lead)
    if flow:
        return IntakeReply(text=text, whatsapp_flow=flow)
    return IntakeReply(text=text, list_picker=_build_date_picker_payload(db, lead))


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
        body="Tap the button below to open the date menu and pick your consultation day.",
        button="Choose date",
        items=items,
    )


def process_intake_message(db: Session, lead: Lead, incoming_text: str) -> IntakeReply:
    ensure_consultation_slots(db)
    step = get_intake_step(lead)
    text = (incoming_text or "").strip()
    first = (lead.full_name or "there").split()[0]

    if step in {INTAKE_STEP_WELCOME, ""} or not getattr(lead, "intake_step", None):
        if _looks_like_full_name(text):
            lead.full_name = text.title()
            lead.intake_step = INTAKE_STEP_CURRENT_LOCATION
            db.commit()
            return IntakeReply(
                text=f"Thanks, {lead.full_name.split()[0]}! Which city and country are you currently located in?"
            )
        lead.intake_step = INTAKE_STEP_FULL_NAME
        db.commit()
        return IntakeReply(text=start_intake_message())

    if step == INTAKE_STEP_FULL_NAME:
        if not _looks_like_full_name(text):
            return IntakeReply(
                text="Please share your full name as you'd like it on your application (first and last name)."
            )
        lead.full_name = text.title()
        lead.intake_step = INTAKE_STEP_CURRENT_LOCATION
        db.commit()
        return IntakeReply(
            text=f"Thanks, {lead.full_name.split()[0]}! Which city and country are you currently located in?"
        )

    if step == INTAKE_STEP_CURRENT_LOCATION:
        if len(text) < 2:
            return IntakeReply(
                text="Could you share your current city and country? For example: Colombo, Sri Lanka."
            )
        lead.current_location = text
        lead.intake_step = INTAKE_STEP_TARGET_COUNTRY
        db.commit()
        return IntakeReply(text="Great. Which country are you interested in studying in?")

    if step == INTAKE_STEP_TARGET_COUNTRY:
        if len(text) < 2:
            return IntakeReply(text="Which destination country are you considering for your studies?")
        lead.preferred_country = text
        lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
        db.commit()
        return IntakeReply(
            text=(
                "Got it. What are your English test scores (IELTS, TOEFL, PTE, or Duolingo)? "
                "If you haven't taken a test yet, reply *skip*."
            )
        )

    if step == INTAKE_STEP_ENGLISH_SCORES:
        lead.english_test_scores = "Not provided yet" if _is_skip(text) else text
        lead.intake_step = INTAKE_STEP_GRE_SCORE
        db.commit()
        return IntakeReply(text="What is your GRE score? Reply with the score or type *skip* if not applicable.")

    if step == INTAKE_STEP_GRE_SCORE:
        lead.gre_score = "Not provided" if _is_skip(text) else text
        lead.intake_step = INTAKE_STEP_GMAT_SCORE
        db.commit()
        return IntakeReply(text="What is your GMAT score? Reply with the score or type *skip* if not applicable.")

    if step == INTAKE_STEP_GMAT_SCORE:
        lead.gmat_score = "Not provided" if _is_skip(text) else text
        lead.test_scores = (
            f"English: {lead.english_test_scores or 'N/A'} | "
            f"GRE: {lead.gre_score or 'N/A'} | "
            f"GMAT: {lead.gmat_score or 'N/A'}"
        )
        lead.intake_step = INTAKE_STEP_CALL_CONSENT
        db.commit()
        return IntakeReply(
            text="Would you like a Nexus admissions advisor to call and guide you through the application process?",
            quick_reply=_build_call_consent_quick_reply(),
        )

    if step == INTAKE_STEP_CALL_CONSENT:
        consent = _parse_yes_no(text)
        if consent is None:
            return IntakeReply(
                text="Tap a button below, or reply *yes* / *no*.",
                quick_reply=_build_call_consent_quick_reply(),
            )
        lead.wants_consultation_call = consent
        if not consent:
            lead.intake_step = INTAKE_STEP_COMPLETE
            db.commit()
            return IntakeReply(text=_complete_without_call_message(lead))
        lead.intake_step = INTAKE_STEP_PICK_DATE
        db.commit()
        return _booking_step_reply(db, lead, "Great! Let's schedule your consultation.")

    if step == INTAKE_STEP_PICK_DATE:
        dates = _available_dates(db)
        if not dates:
            ensure_consultation_slots(db)
            dates = _available_dates(db)
        if not dates:
            lead.intake_step = INTAKE_STEP_COMPLETE
            db.commit()
            return IntakeReply(
                text=(
                    "I couldn't find open consultation slots right now. An advisor will contact you soon "
                    "to schedule a call manually."
                )
            )
        choice = _parse_date_selection(text, dates)
        if choice is None:
            return _booking_step_reply(db, lead, "Please pick a consultation date from the calendar.")
        selected_date = dates[choice - 1]
        context = _load_context(lead)
        context["selected_date"] = selected_date.isoformat()
        _save_context(db, lead, context)
        lead.intake_step = INTAKE_STEP_PICK_TIME
        db.commit()
        return IntakeReply(
            text=f"Date selected: {_format_slot_date(selected_date)}. Now choose a time.",
            quick_reply=_build_time_picker_payload(db, lead, selected_date),
        )

    if step == INTAKE_STEP_PICK_TIME:
        context = _load_context(lead)
        selected_raw = context.get("selected_date")
        if not selected_raw:
            lead.intake_step = INTAKE_STEP_PICK_DATE
            db.commit()
            return _booking_step_reply(db, lead, "Let's pick your consultation date again.")
        selected_date = date.fromisoformat(selected_raw)
        slots = _available_times_for_date(db, selected_date)
        if not slots:
            lead.intake_step = INTAKE_STEP_PICK_DATE
            db.commit()
            return _booking_step_reply(db, lead, "That date is no longer available. Please choose another date.")
        choice = _parse_time_selection(text, slots, context)
        if choice is None:
            return IntakeReply(
                text=f"Tap a time for {_format_slot_date(selected_date)}:",
                quick_reply=_build_time_picker_payload(db, lead, selected_date),
            )
        return _finalize_consultation_booking(db, lead, selected_date, slots[choice - 1].id, first)

    return IntakeReply(text=_complete_without_call_message(lead))


def _complete_without_call_message(lead: Lead) -> str:
    first = (lead.full_name or "there").split()[0]
    return (
        f"Thank you, {first}! ✅ I've saved your profile details.\n\n"
        f"• Location: {lead.current_location or '—'}\n"
        f"• Target country: {lead.preferred_country or '—'}\n"
        f"• Test scores: {lead.test_scores or '—'}\n\n"
        "Feel free to ask me any questions about programs, documents, or timelines."
    )


def get_current_step_reply(db: Session, lead: Lead) -> IntakeReply:
    step = get_intake_step(lead)
    if step in {INTAKE_STEP_WELCOME, INTAKE_STEP_FULL_NAME, ""} or not getattr(lead, "intake_step", None):
        return IntakeReply(text=start_intake_message())
    if step == INTAKE_STEP_PICK_DATE:
        return _booking_step_reply(db, lead, "Please choose your consultation date.")
    if step == INTAKE_STEP_PICK_TIME:
        context = _load_context(lead)
        selected_raw = context.get("selected_date")
        if selected_raw:
            selected_date = date.fromisoformat(selected_raw)
            return IntakeReply(
                text=f"Please choose a time on {_format_slot_date(selected_date)}.",
                quick_reply=_build_time_picker_payload(db, lead, selected_date),
            )
        return _booking_step_reply(db, lead, "Please choose your consultation date.")
    prompts = {
        INTAKE_STEP_CURRENT_LOCATION: "Which city and country are you currently located in?",
        INTAKE_STEP_TARGET_COUNTRY: "Which country are you interested in studying in?",
        INTAKE_STEP_ENGLISH_SCORES: (
            "What are your English test scores (IELTS, TOEFL, PTE, or Duolingo)? Reply *skip* if not yet taken."
        ),
        INTAKE_STEP_GRE_SCORE: "What is your GRE score? Reply with the score or type *skip*.",
        INTAKE_STEP_GMAT_SCORE: "What is your GMAT score? Reply with the score or type *skip*.",
        INTAKE_STEP_CALL_CONSENT: (
            "Would you like a Nexus admissions advisor to call and guide you through the application process?"
        ),
    }
    if step == INTAKE_STEP_CALL_CONSENT:
        return IntakeReply(text=prompts[step], quick_reply=_build_call_consent_quick_reply())
    return IntakeReply(text=prompts.get(step, start_intake_message()))


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
        confirmation = complete_booking_from_flow(db, lead, str(selected_date), str(selected_time))
        return IntakeReply(text=confirmation)
    except ValueError as exc:
        return IntakeReply(text=f"Sorry, I couldn't complete that booking: {exc}")


def get_current_step_prompt(db: Session, lead: Lead) -> str:
    return get_current_step_reply(db, lead).text


INTAKE_STEP_LABELS: dict[str, str] = {
    INTAKE_STEP_WELCOME: "Welcome",
    INTAKE_STEP_FULL_NAME: "Full name",
    INTAKE_STEP_CURRENT_LOCATION: "Current location",
    INTAKE_STEP_TARGET_COUNTRY: "Target country",
    INTAKE_STEP_ENGLISH_SCORES: "English test scores",
    INTAKE_STEP_GRE_SCORE: "GRE score",
    INTAKE_STEP_GMAT_SCORE: "GMAT score",
    INTAKE_STEP_CALL_CONSENT: "Advisor call",
    INTAKE_STEP_PICK_DATE: "Pick consultation date",
    INTAKE_STEP_PICK_TIME: "Pick consultation time",
    INTAKE_STEP_COMPLETE: "Intake complete",
}

INTAKE_STEP_ORDER: list[str] = [
    INTAKE_STEP_FULL_NAME,
    INTAKE_STEP_CURRENT_LOCATION,
    INTAKE_STEP_TARGET_COUNTRY,
    INTAKE_STEP_ENGLISH_SCORES,
    INTAKE_STEP_GRE_SCORE,
    INTAKE_STEP_GMAT_SCORE,
    INTAKE_STEP_CALL_CONSENT,
    INTAKE_STEP_PICK_DATE,
    INTAKE_STEP_PICK_TIME,
    INTAKE_STEP_COMPLETE,
]


def build_intake_profile_summary(lead: Lead, db: Session | None = None) -> dict[str, Any]:
    step = get_intake_step(lead)
    summary: dict[str, Any] = {
        "intake_step": step,
        "intake_step_label": INTAKE_STEP_LABELS.get(step, step.replace("_", " ").title()),
        "intake_complete": is_intake_complete(lead),
        "current_location": getattr(lead, "current_location", None),
        "preferred_country": lead.preferred_country,
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
        "selected_consultation_date": None,
    }

    if db is None:
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
