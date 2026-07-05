"""Deterministic WhatsApp intake copy — no LLM/API keys required."""

from __future__ import annotations

import json

from app.models.lead import Lead

BRAND_NAME = "Edutrust"

OUTREACH_FULL_NAME_PROMPT = (
    "To book your *free study abroad consultation*, simply *reply with your full name*."
)

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
INTAKE_STEP_COMPLETE = "COMPLETE"


def render_outreach_intake_followup() -> str:
    """Session message sent immediately after the WhatsApp outreach template."""
    return OUTREACH_FULL_NAME_PROMPT


def student_first_name(lead: Lead) -> str:
    name = (lead.full_name or "").strip()
    if not name or "whatsapp contact" in name.lower():
        return "there"
    first = name.split()[0]
    if first.lower() in {"hey", "hi", "hello", "there"}:
        return "there"
    return first


def _lead_intake_step(lead: Lead) -> str:
    step = getattr(lead, "intake_step", None)
    return step or INTAKE_STEP_WELCOME


def _resolve_step_from_task(task: str, lead: Lead) -> str:
    task_upper = (task or "").upper()
    markers = (
        ("INTAKE_STEP=WELCOME", INTAKE_STEP_FULL_NAME),
        ("INTAKE_STEP=FULL_NAME", INTAKE_STEP_FULL_NAME),
        ("INTAKE_STEP=LOCATION", INTAKE_STEP_CURRENT_LOCATION),
        ("INTAKE_STEP=DEGREE", INTAKE_STEP_TARGET_DEGREE),
        ("INTAKE_STEP=MAJOR", INTAKE_STEP_TARGET_MAJOR),
        ("INTAKE_STEP=COUNTRY", INTAKE_STEP_TARGET_COUNTRY),
        ("INTAKE_STEP=TARGET", INTAKE_STEP_TARGET_COUNTRY),
        ("INTAKE_STEP=ENGLISH", INTAKE_STEP_ENGLISH_SCORES),
        ("INTAKE_STEP=GRE", INTAKE_STEP_GRE_SCORE),
        ("INTAKE_STEP=GMAT", INTAKE_STEP_GMAT_SCORE),
        ("INTAKE_STEP=CONSENT", INTAKE_STEP_CALL_CONSENT),
        ("INTAKE_STEP=PICK_DATE", INTAKE_STEP_PICK_DATE),
        ("INTAKE_STEP=PICK_TIME", INTAKE_STEP_PICK_TIME),
        ("INTAKE_STEP=COMPLETE", INTAKE_STEP_COMPLETE),
    )
    for marker, step in markers:
        if marker in task_upper:
            return step
    return _lead_intake_step(lead)


def _pending_target_country(lead: Lead) -> str:
    raw = getattr(lead, "intake_context", None)
    if not raw:
        return ""
    try:
        context = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if isinstance(context, dict):
        return str(context.get("pending_country") or "").strip()
    return ""


def _pending_course_or_program(lead: Lead) -> str:
    raw = getattr(lead, "intake_context", None)
    if not raw:
        return ""
    try:
        context = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if isinstance(context, dict):
        pending = str(context.get("pending_program") or "").strip()
        if pending:
            return pending
        return str(context.get("preferred_course") or context.get("target_program") or "").strip()
    return ""


def render_deterministic_intake_text(
    lead: Lead,
    *,
    task: str = "",
    incoming_text: str = "",
) -> str:
    del incoming_text
    first = student_first_name(lead)
    step = _resolve_step_from_task(task, lead)
    task_lower = (task or "").lower()

    if step in {INTAKE_STEP_WELCOME, INTAKE_STEP_FULL_NAME, ""}:
        if "too long" in task_lower:
            return "Please *reply with your full name* (maximum *75 characters*)."
        return OUTREACH_FULL_NAME_PROMPT

    if step == INTAKE_STEP_CURRENT_LOCATION:
        if "too long" in task_lower:
            return (
                f"Please keep your location to *50 characters* or less, {first}. "
                "*Which city and country are you in right now?*"
            )
        if "too short" in task_lower:
            return f"Please tell us your *current city and country*, {first}."
        saved = (lead.full_name or first).split()[0] if lead.full_name else first
        return f"Thanks, *{saved}*! *Which city and country are you in right now?*"

    if step == INTAKE_STEP_TARGET_DEGREE:
        if "not recognized" in task_lower:
            return (
                f"{first}, please *tap the button below* and choose the *program (degree)* "
                "you are targeting."
            )
        return (
            f"Thanks, {first}! *Which program (degree) are you targeting?*\n\n"
            "*Tap the button below* to choose:\n"
            "• *Bachelor's Degree* (3-4 years)\n"
            "• *Master's Degree* (1-2 years)\n"
            "• *Integrated master's* (3-5 years)\n"
            "• *Doctorate* (3-7 years)"
        )

    if step == INTAKE_STEP_TARGET_MAJOR:
        if "too long" in task_lower:
            return (
                f"{first}, please keep your major to *50 characters* or less. "
                "*Which major are you targeting?*\n"
                "For example: *Computer Science*, *Business Administration*."
            )
        if "invalid" in task_lower:
            return (
                f"{first}, please tell us your *intended major*.\n"
                "For example: *Computer Science*, *Business Administration*."
            )
        return (
            f"Great, {first}! *Which major are you targeting?*\n\n"
            "For example: *Computer Science*, *Business Administration*."
        )

    if step == INTAKE_STEP_TARGET_COUNTRY:
        if "too long" in task_lower:
            return (
                f"{first}, please keep your answer to *50 characters* or less. "
                "*Which country are you targeting?*\n"
                "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
            )
        if "invalid" in task_lower:
            return (
                f"{first}, please tell us *which country you are targeting*.\n"
                "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
            )
        if (
            "country noted" in task_lower
            or "course/program missing" in task_lower
            or "destination country missing" in task_lower
            or "country missing" in task_lower
        ):
            pending = (lead.preferred_country or "").strip() or _pending_target_country(lead)
            pending_course = _pending_course_or_program(lead)
            if pending and pending_course:
                return (
                    f"Thanks, {first}! I've noted *{pending}*. "
                    "*What course or program* would you like to study there?"
                )
            if pending_course and not pending:
                return (
                    f"Thanks, {first}! I've noted your interest in *{pending_course}*. "
                    "*Which country* would you like to study in?"
                )
            if pending:
                return (
                    f"Thanks, {first}! I've noted *{pending}*. "
                    "*What course or program* would you like to study there?"
                )
            return f"Thanks, {first}! *Which country* would you like to study in?"
        prefilled_country = (lead.preferred_country or "").strip() or _pending_target_country(lead)
        if prefilled_country and "major saved" not in task_lower:
            return (
                f"Thanks, {first}! I've noted *{prefilled_country}*. "
                "*What course or program* would you like to study there?"
            )
        return (
            f"Thanks, {first}! *Which country are you targeting?*\n\n"
            "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
        )

    if step == INTAKE_STEP_ENGLISH_SCORES:
        if "too long" in task_lower:
            return (
                f"{first}, please keep your score to *20 characters* or less. "
                "Reply with your *English test score* or type *skip*."
            )
        return (
            f"*Do you have English test scores* (IELTS, TOEFL, PTE, or Duolingo), {first}?\n"
            "Reply with your score or type *skip*."
        )

    if step == INTAKE_STEP_GRE_SCORE:
        if "too long" in task_lower:
            return (
                f"{first}, please keep your score to *20 characters* or less. "
                "Reply with your *GRE score* or type *skip*."
            )
        return f"*Do you have a GRE score*, {first}? Reply with your score or type *skip*."

    if step == INTAKE_STEP_GMAT_SCORE:
        if "too long" in task_lower:
            return (
                f"{first}, please keep your score to *20 characters* or less. "
                "Reply with your *GMAT score* or type *skip*."
            )
        return f"*Do you have a GMAT score*, {first}? Reply with your score or type *skip*."

    if step == INTAKE_STEP_CALL_CONSENT:
        return (
            f"{first}, would you like a *free consultation call* with a *{BRAND_NAME}* "
            "admissions advisor? Tap *Yes, please* or *No thanks* below."
        )

    if step == INTAKE_STEP_PICK_DATE:
        if "no consultation slots" in task_lower or "no open consultation" in task_lower:
            return (
                f"{first}, consultation slots are being updated. "
                "*An advisor will contact you shortly* to schedule your call."
            )
        if "another date" in task_lower or "no times remain" in task_lower:
            return (
                f"{first}, that date is full. *Tap below* to choose another consultation date."
            )
        return f"Perfect, {first}! *Tap the button below* to choose your *consultation date*."

    if step == INTAKE_STEP_PICK_TIME:
        if "no open consultation times" in task_lower:
            return (
                f"{first}, please choose another consultation date — "
                "*no times are left on that day*."
            )
        return f"{first}, *tap below* to choose your *consultation time*."

    if step == INTAKE_STEP_COMPLETE:
        return (
            f"Thanks, {first}! *We've saved your profile.*\n"
            "Tap *Book Session* below to schedule a consultation, "
            "or *Not Interested* if you'd prefer not to."
        )

    return (
        f"Hi {first}! I'm here to help you book a consultation with *{BRAND_NAME}*.\n"
        "*Reply with your full name* to continue."
    )


def render_appointment_only_reply(lead: Lead, incoming_text: str = "") -> str:
    """Post-intake messaging when LLM is disabled — booking management only."""
    from app.services.admissions_intake_flow import format_booking_summary

    first = student_first_name(lead)
    del incoming_text
    if lead.consultation_scheduled_at or lead.wants_consultation_call:
        return format_booking_summary(lead)
    return (
        f"{first}, I can help you book a consultation with *{BRAND_NAME}*.\n"
        "Tap *Book Session* below to pick a date and time."
    )
