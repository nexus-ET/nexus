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
BRAND_NAME = "Edutrust"

RESCHEDULE_PATTERN = re.compile(
    r"(reschedule|change|move|update|switch|pick another|different|new)\s+"
    r"(slot|appointment|booking|call|time|date|schedule)|"
    r"(change|move|reschedule|cancel)\s+(my|the)\s+(slot|appointment|booking|call)|"
    r"^reschedule$|^change slot$|^change appointment$|^cancel appointment$|^cancel booking$",
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
    r"^cancel(?:\s+(?:appointment|booking|my appointment))?$",
    re.IGNORECASE,
)


@dataclass
class IntakeReply:
    text: str
    list_picker: ListPickerPayload | None = None
    quick_reply: QuickReplyPayload | None = None
    whatsapp_flow: FlowPayload | None = None
    confidence: float = 1.0


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
    return IntakeReply(text=result.text, confidence=result.confidence, **reply_kwargs)


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
    cleaned = text.strip()
    if len(cleaned) < 3:
        return False
    if cleaned.lower().startswith("whatsapp contact"):
        return False
    return bool(re.search(r"[a-zA-Z]", cleaned))


async def process_intake_message(
    db: Session,
    lead: Lead,
    incoming_text: str,
    runtime_config,
) -> IntakeReply:
    step = get_intake_step(lead)
    text = (incoming_text or "").strip()
    first = (lead.full_name or "there").split()[0]

    if step in {INTAKE_STEP_WELCOME, ""} or not getattr(lead, "intake_step", None):
        if _looks_like_full_name(text):
            lead.full_name = text.title()
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
        if not _looks_like_full_name(text):
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=FULL_NAME; Previous answer was not a valid full name. Ask again for first and last name.",
                incoming_text=text,
            )
        lead.full_name = text.title()
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
        if len(text) < 2:
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=LOCATION; Location answer was too short. Ask again for city and country.",
                incoming_text=text,
            )
        lead.current_location = text
        lead.intake_step = INTAKE_STEP_TARGET_COUNTRY
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task="INTAKE_STEP=TARGET; Ask which destination country and course/program they want to study.",
            incoming_text=text,
        )

    if step == INTAKE_STEP_TARGET_COUNTRY:
        interest = _extract_study_interest(text)
        country = (interest.get("country") or "").strip()
        program = (interest.get("program") or "").strip()
        if not country and len(text.strip()) >= 2 and not program:
            country = text.strip()
        if not country or len(country) < 2:
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=TARGET; Ask again for destination country and intended course/program.",
                incoming_text=text,
            )
        if not program:
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=TARGET; Country noted but course/program missing. Ask for both country and course.",
                incoming_text=text,
            )
        lead.preferred_country = country.title()
        context = _load_context(lead)
        context["preferred_course"] = program
        lead.academic_summary = f"Course: {program}"
        _save_context(db, lead, context)
        lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=(
                f"INTAKE_STEP=ENGLISH; Target saved as {program} in {lead.preferred_country}. "
                "Ask for English test scores or invite them to reply skip."
            ),
            incoming_text=text,
        )

    if step == INTAKE_STEP_ENGLISH_SCORES:
        lead.english_test_scores = "Not provided yet" if _is_skip(text) else text
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
        lead.gre_score = "Not provided" if _is_skip(text) else text
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
        lead.gmat_score = "Not provided" if _is_skip(text) else text
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
    return await _agent_intake_reply(
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


async def get_current_step_reply(db: Session, lead: Lead, runtime_config) -> IntakeReply:
    step = get_intake_step(lead)
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
        INTAKE_STEP_TARGET_COUNTRY: "INTAKE_STEP=TARGET; Ask for destination country and intended course.",
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
    name = (lead.full_name or "").strip()
    if not _looks_like_full_name(name):
        return False
    return "whatsapp contact" not in name.lower()


def _extract_study_interest(text: str) -> dict[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}

    interest: dict[str, str] = {}
    in_country_match = re.search(
        r"^(.{3,80}?)\s+in\s+([A-Za-z][A-Za-z\s\-]{2,40})$",
        cleaned,
        re.IGNORECASE,
    )
    if in_country_match:
        interest["program"] = in_country_match.group(1).strip(" .")
        interest["country"] = in_country_match.group(2).strip(" .")
        return interest

    study_match = re.search(
        r"study(?:\s+abroad)?\s+(.+?)\s+(?:in|at|to)\s+([A-Za-z][A-Za-z\s\-]{1,40})",
        cleaned,
        re.IGNORECASE,
    )
    if study_match:
        interest["program"] = study_match.group(1).strip(" .")
        interest["country"] = study_match.group(2).strip(" .")
        return interest

    country_match = re.search(
        r"\b(?:in|to|for)\s+([A-Za-z][A-Za-z\s\-]{2,40})\b",
        cleaned,
        re.IGNORECASE,
    )
    if country_match:
        interest["country"] = country_match.group(1).strip(" .")
    if re.search(r"\b(study|course|program|degree|design|fashion|mba|ms|bachelor)\b", cleaned, re.I):
        interest["program"] = cleaned
    return interest


def _resolve_intake_restart_step(lead: Lead, incoming_hint: str | None = None) -> str:
    interest = _extract_study_interest(incoming_hint or "")
    if interest.get("country") and _lead_has_real_name(lead):
        return INTAKE_STEP_TARGET_COUNTRY
    if _lead_has_real_name(lead):
        if not lead.current_location:
            return INTAKE_STEP_CURRENT_LOCATION
        if not lead.preferred_country:
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
    context = _load_context(lead)
    interest = _extract_study_interest(incoming_hint or "")
    if interest:
        context["study_interest"] = interest

    if force_full_restart or not _lead_has_real_name(lead):
        lead.intake_step = INTAKE_STEP_FULL_NAME
    else:
        lead.intake_step = _resolve_intake_restart_step(lead, incoming_hint)

    lead.intake_context = json.dumps(context) if context else None
    db.commit()


def _appointment_management_note() -> str:
    return (
        "You can reschedule or cancel anytime by messaging *reschedule* "
        "or *cancel* on WhatsApp."
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
                "Reply *reschedule* to pick a date and time."
            )
        return f"{first}, you haven't booked an advisor call. Reply *reschedule* if you'd like to schedule one."

    scheduled = lead.consultation_scheduled_at
    slot_day = scheduled.date()
    slot_time = scheduled.strftime("%H:%M")
    return (
        f"{first}, your consultation is scheduled for "
        f"{_format_slot_date(slot_day)} at {_format_slot_time(slot_time)}.\n\n"
        f"{_appointment_management_note()}"
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
    return False


def handle_post_intake_booking_message(db: Session, lead: Lead, incoming_text: str) -> IntakeReply | None:
    if get_intake_step(lead) in {INTAKE_STEP_PICK_DATE, INTAKE_STEP_PICK_TIME}:
        return None

    text = (incoming_text or "").strip()
    lowered = text.lower()
    first = (lead.full_name or "there").split()[0]

    if THANKS_PATTERN.match(text):
        if lead.consultation_scheduled_at:
            return IntakeReply(
                text=(
                    f"You're welcome, {first}! ✅\n\n"
                    f"{format_booking_summary(lead)}\n\n"
                    f"{_appointment_management_note()}"
                )
            )
        return IntakeReply(
            text=f"You're welcome, {first}! Feel free to message anytime if you have questions."
        )

    if CANCEL_PATTERN.match(text) or (
        "cancel" in lowered and "appointment" in lowered
    ):
        had_booking = bool(lead.consultation_scheduled_at)
        release_lead_consultation_slot(db, lead)
        lead.intake_step = INTAKE_STEP_COMPLETE
        lead.wants_consultation_call = True
        db.commit()
        if had_booking:
            return IntakeReply(
                text=(
                    f"Done, {first}. Your consultation appointment has been cancelled.\n\n"
                    f"Reply *reschedule* anytime if you'd like to book a new slot.\n\n"
                    f"{_appointment_management_note()}"
                )
            )
        return IntakeReply(
            text=f"{first}, you don't have an active appointment to cancel. Reply *reschedule* to book one."
        )

    if RESCHEDULE_PATTERN.search(text) or lowered in {
        "reschedule",
        "change slot",
        "change appointment",
    }:
        previous_summary = (
            format_booking_summary(lead)
            if lead.consultation_scheduled_at
            else f"{first}, let's schedule your consultation."
        )
        release_lead_consultation_slot(db, lead)
        lead.intake_step = INTAKE_STEP_PICK_DATE
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        lead.wants_consultation_call = True
        db.commit()
        return _booking_step_reply(
            db,
            lead,
            (
                f"{previous_summary}\n\n"
                "Tap below to choose a new consultation date."
            ),
        )

    if BOOKING_INFO_PATTERN.search(text):
        return IntakeReply(text=format_booking_summary(lead))

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
        slot.slot_date,
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
        f"{_format_slot_date(slot.slot_date)} at {_format_slot_time(slot.slot_time)}.\n\n"
        f"An {BRAND_NAME} admissions advisor will call you at that time.\n\n"
        f"{_appointment_management_note()}"
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
        body=f"Tap below to choose a time for {_format_slot_date(slot_day)}.",
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
        body="Tap below to open the calendar and book your consultation.",
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
        body="Tap the button below to open the date menu and pick your consultation day.",
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
        confirmation = complete_booking_from_flow(db, lead, str(selected_date), str(selected_time))
        return IntakeReply(text=confirmation)
    except ValueError as exc:
        return IntakeReply(text=f"Sorry, I couldn't complete that booking: {exc}")


async def get_current_step_prompt(db: Session, lead: Lead, runtime_config) -> str:
    reply = await get_current_step_reply(db, lead, runtime_config)
    return reply.text


INTAKE_STEP_LABELS: dict[str, str] = {
    INTAKE_STEP_WELCOME: "Welcome",
    INTAKE_STEP_FULL_NAME: "Full name",
    INTAKE_STEP_CURRENT_LOCATION: "Current location",
    INTAKE_STEP_TARGET_COUNTRY: "Target country & course",
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
    return cleaned


def build_intake_profile_summary(lead: Lead, db: Session | None = None) -> dict[str, Any]:
    step = get_intake_step(lead)
    context = _load_context(lead)
    summary: dict[str, Any] = {
        "intake_step": step,
        "intake_step_label": INTAKE_STEP_LABELS.get(step, step.replace("_", " ").title()),
        "intake_complete": is_intake_complete(lead),
        "current_location": getattr(lead, "current_location", None),
        "preferred_country": lead.preferred_country,
        "preferred_course": context.get("preferred_course"),
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
