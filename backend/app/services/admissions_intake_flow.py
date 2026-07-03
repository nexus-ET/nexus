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
    "germany": "Germany",
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
    "china": "China",
    "south korea": "South Korea",
    "korea": "South Korea",
}


def _normalize_country_name(raw: str) -> str | None:
    token = (raw or "").strip()
    if not token:
        return None
    key = re.sub(r"[^\w\s.]", "", token).lower().strip()
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


def is_reschedule_command(text: str) -> bool:
    command_text = _normalize_management_command(text)
    lowered = command_text.lower()
    return bool(RESCHEDULE_PATTERN.search(command_text)) or lowered in {
        "reschedule",
        "change slot",
        "change appointment",
    }


def is_cancel_command(text: str) -> bool:
    command_text = _normalize_management_command(text)
    if not command_text:
        return False
    lowered = command_text.lower()
    if CANCEL_PATTERN.match(command_text) or CANCEL_COMMAND_PATTERN.search(command_text):
        return True
    return lowered == "cancel" or lowered.startswith("cancel ")


def is_post_intake_management_command(text: str) -> bool:
    """Reschedule/cancel/thanks/booking-info commands handled outside intake steps."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if is_reschedule_command(cleaned) or is_cancel_command(cleaned):
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
    if len(cleaned) < 2:
        return None
    if cleaned.lower().startswith("whatsapp contact"):
        return None
    if not re.search(r"[a-zA-Z]", cleaned):
        return None
    return _normalize_intake_name(cleaned)


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
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=FULL_NAME; Ask once more for the student's name.",
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
        if len(text) < 2:
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task="INTAKE_STEP=LOCATION; Location answer was too short. Ask again for city and country.",
                incoming_text=text,
            )
        lead.current_location = text
        study = resolve_lead_study_interest(lead)
        if lead_has_complete_study_interest(lead):
            _persist_resolved_study_interest(db, lead, study)
            lead.intake_step = INTAKE_STEP_ENGLISH_SCORES
            db.commit()
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=(
                    f"INTAKE_STEP=ENGLISH; Location saved as {lead.current_location!r}. "
                    f"Their target is already {study.get('course') or study.get('program')} "
                    f"in {lead.preferred_country}. Ask for English test scores or invite them to reply skip."
                ),
                incoming_text=text,
            )
        lead.intake_step = INTAKE_STEP_TARGET_COUNTRY
        _prepare_target_step_prefill(db, lead, study)
        db.commit()
        return await _agent_intake_reply(
            db,
            lead,
            runtime_config,
            task=build_target_intake_task(lead),
            incoming_text=text,
        )

    if step == INTAKE_STEP_TARGET_COUNTRY:
        if lead_has_complete_study_interest(lead):
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

        study = resolve_lead_study_interest(lead)
        _prepare_target_step_prefill(db, lead, study)
        context = _load_context(lead)
        pending_country = (context.get("pending_country") or "").strip()
        pending_program = (context.get("pending_program") or "").strip()

        interest = _extract_study_interest(text)
        country = (interest.get("country") or pending_country).strip()
        program = (interest.get("program") or pending_program).strip()

        if not country and len(text.strip()) >= 2 and not program:
            country = _normalize_country_name(text.strip()) or text.strip()
        if not program and len(text.strip()) >= 2 and not country:
            program = text.strip()

        if not country or len(country) < 2:
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=build_target_intake_task(lead),
                incoming_text=text,
            )
        if not program:
            context["pending_country"] = _normalize_country_name(country) or country.title()
            context.pop("pending_program", None)
            _save_context(db, lead, context)
            return await _agent_intake_reply(
                db,
                lead,
                runtime_config,
                task=(
                    "INTAKE_STEP=TARGET; Country noted but course/program missing. "
                    f"Pending country: {context['pending_country']}. Ask only for course/program."
                ),
                incoming_text=text,
            )

        lead.preferred_country = _normalize_country_name(country) or country.title()
        context["preferred_course"] = program
        context.pop("pending_country", None)
        context.pop("pending_program", None)
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
    from app.services.lead_study_interest import (
        build_target_intake_task,
        hydrate_lead_study_interest,
        lead_has_complete_study_interest,
        resolve_lead_study_interest,
    )

    hydrate_lead_study_interest(db, lead, commit=False)
    step = get_intake_step(lead)
    if step == INTAKE_STEP_TARGET_COUNTRY:
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
    return interest


def _resolve_intake_restart_step(lead: Lead, incoming_hint: str | None = None) -> str:
    from app.services.lead_study_interest import lead_has_complete_study_interest

    if _lead_has_real_name(lead):
        if not lead.current_location:
            return INTAKE_STEP_CURRENT_LOCATION
        if not lead_has_complete_study_interest(lead):
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


def _clear_booking_selection_context(context: dict[str, Any]) -> None:
    context.pop("selected_date", None)
    context.pop("time_slot_ids", None)
    context.pop("date_options", None)


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
    if is_cancel_command(cleaned):
        return True
    if BOOKING_INFO_PATTERN.search(cleaned):
        return True
    if lead.consultation_scheduled_at and _parse_choice_number(cleaned, 10):
        return False
    return False


def handle_post_intake_booking_message(db: Session, lead: Lead, incoming_text: str) -> IntakeReply | None:
    text = (incoming_text or "").strip()
    step = get_intake_step(lead)
    if step in {INTAKE_STEP_PICK_DATE, INTAKE_STEP_PICK_TIME} and not is_post_intake_management_command(
        text
    ):
        return None

    command_text = _strip_booking_markdown(text)
    lowered = command_text.lower()
    first = (lead.full_name or "there").split()[0]

    if THANKS_PATTERN.match(text):
        if lead.consultation_scheduled_at:
            return IntakeReply(
                text=(
                    f"You're welcome, {first}! We'll speak with you at your scheduled time. 👋"
                )
            )
        return IntakeReply(
            text=f"You're welcome, {first}! Feel free to message anytime if you have questions."
        )

    if is_cancel_command(text):
        had_booking = bool(lead.consultation_scheduled_at)
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
                text=(
                    f"Done, {first}. Your consultation appointment has been cancelled.\n\n"
                    f"Reply *reschedule* anytime if you'd like to book a new slot.\n\n"
                    f"{_appointment_management_note()}"
                )
            )
        return IntakeReply(
            text=f"{first}, you don't have an active appointment to cancel. Reply *reschedule* to book one."
        )

    if is_reschedule_command(text):
        had_booking = bool(lead.consultation_scheduled_at)
        previous_summary = (
            format_booking_summary(lead)
            if had_booking
            else f"{first}, let's schedule your consultation."
        )
        release_lead_consultation_slot(db, lead)
        _reset_booking_intake_context(db, lead)
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
        "preferred_course": study_fields.get("preferred_course") or context.get("preferred_course"),
        "target_program": study_fields.get("target_program") or context.get("target_program"),
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
