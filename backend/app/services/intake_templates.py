"""Deterministic WhatsApp intake copy — no LLM/API keys required."""



from __future__ import annotations



import json



from app.models.lead import Lead



BRAND_NAME = "Edutrust"



OUTREACH_FULL_NAME_PROMPT = (
    # Retained for backwards-compatible imports; full-name ask is skipped in intake.
    "What's your *full name*?"
)


OUTREACH_CONTINUE_PROMPT = (
    # Legacy copy — no longer sent as an outreach follow-up.
    # Students engage by messaging hi/hello, then intake advances to degree questions.
    'To continue your study abroad consultation, simply drop us a quick "hi" or "hello"!'
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
    """Legacy continue nudge (no longer sent after the welcome template)."""
    return OUTREACH_CONTINUE_PROMPT


def render_outreach_full_name_prompt() -> str:

    """Ask the student for their name during intake."""

    return OUTREACH_FULL_NAME_PROMPT





def student_first_name(lead: Lead) -> str:

    name = (lead.full_name or "").strip()

    if not name or "whatsapp contact" in name.lower():

        return "there"

    first = name.split()[0]

    if first.lower() in {"hey", "hi", "hello", "there"}:

        return "there"

    return first


def student_thanks_prefix(lead: Lead) -> str:
    """'Thanks, Priya! ' or 'Thanks! ' when no usable first name."""
    first = student_first_name(lead)
    if first == "there":
        return "Thanks! "
    return f"Thanks, {first}! "


def student_name_comma_prefix(lead: Lead) -> str:
    """'Priya, ' or empty string — never the awkward 'there, '."""
    first = student_first_name(lead)
    if first == "there":
        return ""
    return f"{first}, "





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
    thanks = student_thanks_prefix(lead)
    named = student_name_comma_prefix(lead)

    step = _resolve_step_from_task(task, lead)
    if step == INTAKE_STEP_CURRENT_LOCATION:
        step = INTAKE_STEP_TARGET_DEGREE
    if step in {INTAKE_STEP_ENGLISH_SCORES, INTAKE_STEP_GRE_SCORE, INTAKE_STEP_GMAT_SCORE}:
        step = INTAKE_STEP_CALL_CONSENT

    task_lower = (task or "").lower()



    if step in {INTAKE_STEP_WELCOME, INTAKE_STEP_FULL_NAME, ""}:

        # Full-name collection removed — templates should never emit the old booking ask.
        return render_deterministic_intake_text(
            lead,
            task="INTAKE_STEP=DEGREE; Ask which program (degree) they are targeting.",
        )



    if step == INTAKE_STEP_TARGET_DEGREE:

        if "not recognized" in task_lower:

            if named:
                return (
                    f"{named}let's find the right study path. 🎓 "
                    "*Open the program list* and choose the degree you are targeting."
                )
            return (
                "Let's find the right study path. 🎓 "
                "*Open the program list* and choose the degree you are targeting."
            )

        return (
            f"{thanks}🎓 *Which program (degree) would you like to study?*\n\n"
            "Open the program list to compare the available degree paths."
        )



    if step == INTAKE_STEP_TARGET_MAJOR:

        if "too long" in task_lower:

            if named:
                return (
                    f"{named}please keep your major to *50 characters* or less. "
                    "*Which major are you targeting?*\n"
                    "For example: *Computer Science*, *Business Administration*."
                )
            return (
                "Please keep your major to *50 characters* or less. "
                "*Which major are you targeting?*\n"
                "For example: *Computer Science*, *Business Administration*."
            )

        if "invalid" in task_lower:

            if named:
                return (
                    f"{named}please tell us your *intended major*.\n"
                    "For example: *Computer Science*, *Business Administration*."
                )
            return (
                "Please tell us your *intended major*.\n"
                "For example: *Computer Science*, *Business Administration*."
            )

        great = "Great!" if first == "there" else f"Great, {first}!"
        return (
            f"{great} 📚 *Which subject area excites you most?*\n\n"
            "Explore popular fields below, or type a different major."
        )



    if step == INTAKE_STEP_TARGET_COUNTRY:

        if "too long" in task_lower:

            if named:
                return (
                    f"{named}please keep your answer to *50 characters* or less. "
                    "*Which country are you targeting?*\n"
                    "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
                )
            return (
                "Please keep your answer to *50 characters* or less. "
                "*Which country are you targeting?*\n"
                "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
            )

        if "invalid" in task_lower:

            if named:
                return (
                    f"{named}please tell us *which country you are targeting*.\n"
                    "For example: *US*, *UK*, *JP*, *AU*, *NZ*."
                )
            return (
                "Please tell us *which country you are targeting*.\n"
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

                    f"{thanks}I've noted *{pending}*. "

                    "*What course or program* would you like to study there?"

                )

            if pending_course and not pending:

                return (

                    f"{thanks}I've noted your interest in *{pending_course}*. "

                    "*Which country* would you like to study in?"

                )

            if pending:

                return (

                    f"{thanks}I've noted *{pending}*. "

                    "*What course or program* would you like to study there?"

                )

            return f"{thanks}*Which country* would you like to study in?"

        prefilled_country = (lead.preferred_country or "").strip() or _pending_target_country(lead)

        if prefilled_country and "major saved" not in task_lower:

            return (

                f"{thanks}I've noted *{prefilled_country}*. "

                "*What course or program* would you like to study there?"

            )

        return (
            f"{thanks}🌍 *Where would you love to study?*\n\n"
            "Explore popular destinations such as the *UK*, *USA*, *Canada* and *Australia* below, "
            "or type another country."
        )



    if step == INTAKE_STEP_CALL_CONSENT:

        if named:
            return (
                f"{named}would you like a *free 1-to-1 consultation* with a *{BRAND_NAME}* "
                "admissions advisor? 🎯 Tap your choice below."
            )
        return (
            f"Would you like a *free 1-to-1 consultation* with a *{BRAND_NAME}* "
            "admissions advisor? 🎯 Tap your choice below."
        )



    if step == INTAKE_STEP_PICK_DATE:

        if "no consultation slots" in task_lower or "no open consultation" in task_lower:

            if named:
                return (
                    f"{named}consultation slots are being updated. "
                    "*An advisor will contact you shortly* to schedule your call."
                )
            return (
                "Consultation slots are being updated. "
                "*An advisor will contact you shortly* to schedule your call."
            )

        if "another date" in task_lower or "no times remain" in task_lower:

            if named:
                return (
                    f"{named}that date is full. *Tap below* to choose another consultation date."
                )
            return "That date is full. *Tap below* to choose another consultation date."

        perfect = "Perfect!" if first == "there" else f"Perfect, {first}!"
        return (
            f"{perfect} 📅 *Let's reserve your free advisor call.* "
            "Open the booking form to choose a date and time together."
        )



    if step == INTAKE_STEP_PICK_TIME:

        if "no open consultation times" in task_lower:

            if named:
                return (
                    f"{named}please choose another consultation date — "
                    "*no times are left on that day*."
                )
            return (
                "Please choose another consultation date — "
                "*no times are left on that day*."
            )

        if named:
            return f"{named}⏰ *choose the consultation time that suits you best*."
        return "⏰ *Choose the consultation time that suits you best.*"



    if step == INTAKE_STEP_COMPLETE:

        return (

            f"{thanks}*We've saved your profile.*\n"

            "Tap *Book Session* below to schedule a consultation, "

            "or *Not Interested* if you'd prefer not to."

        )



    return (

        f"{thanks}*Which program (degree) are you targeting?*\n\n"

        "*Tap the button below* to choose:\n"

        "• *Bachelor's Degree* (3-4 years)\n"

        "• *Master's Degree* (1-2 years)\n"

        "• *Integrated master's* (3-5 years)\n"

        "• *Doctorate* (3-7 years)"

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


