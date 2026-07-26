"""Tests for Meta WhatsApp interactive intake delivery."""

from app.services.admissions_intake_flow import IntakeReply
from app.services.meta_whatsapp_interactive import (
    compose_intake_message_text,
    compose_intake_plain_text_fallback,
)
from app.services.twilio_whatsapp_interactive import (
    ListPickerPayload,
    QuickReplyPayload,
    build_text_fallback,
)


def test_compose_intake_message_text_keeps_prompt_only_for_dates():
    reply = IntakeReply(
        text="Perfect! *Tap the button below* to choose your *consultation date*.",
        list_picker=ListPickerPayload(
            kind="date",
            body="Pick a date",
            button="Choose date",
            items=[
                {"id": "date:2026-06-30", "item": "Mon, Jun 30, 2026", "description": "Open"},
                {"id": "date:2026-07-01", "item": "Wed, Jul 01, 2026", "description": "Open"},
            ],
        ),
    )
    body = compose_intake_message_text(reply)
    assert body == "Perfect! *Tap the button below* to choose your *consultation date*."
    assert "1. Mon, Jun 30, 2026" not in body
    assert "Reply with the number" not in body


def test_compose_intake_plain_text_fallback_includes_numbered_dates():
    reply = IntakeReply(
        text="Please pick a consultation date.",
        list_picker=ListPickerPayload(
            kind="date",
            body="Pick a date",
            button="Choose date",
            items=[
                {"id": "date:2026-06-30", "item": "Mon, Jun 30, 2026", "description": "Open"},
                {"id": "date:2026-07-01", "item": "Wed, Jul 01, 2026", "description": "Open"},
            ],
        ),
    )
    body = compose_intake_plain_text_fallback(reply)
    assert "Please pick a consultation date." in body
    assert "1. Mon, Jun 30, 2026" in body
    assert "2. Wed, Jul 01, 2026" in body
    assert "Reply with the number" not in body


def test_compose_intake_message_text_keeps_prompt_only_for_times():
    reply = IntakeReply(
        text="*Tap below* to choose your *consultation time*.\n\nReply with the number of your choice:",
        quick_reply=QuickReplyPayload(
            kind="time",
            body="ignored",
            actions=[
                {"id": "time:10", "title": "10:00 AM"},
                {"id": "time:14", "title": "02:00 PM"},
            ],
        ),
    )
    body = compose_intake_message_text(reply)
    assert body == "*Tap below* to choose your *consultation time*."
    assert "Reply with the number" not in body
    assert "1. 10:00 AM" not in body


def test_confirmation_quick_reply_removes_number_prompt():
    confirmation = (
        "Perfect, Hey! ✅ *Your consultation is confirmed* for "
        "*Mon, Jul 27, 2026* at *10:00 AM*.\n\n"
        "An *Edutrust* admissions advisor will call you at that time."
    )
    payload = QuickReplyPayload(
        kind="consent",
        body=f"{confirmation}\n\nReply with the number of your choice:",
        actions=[
            {"id": "reschedule", "title": "Reschedule"},
            {"id": "cancel", "title": "Cancel"},
        ],
    )

    assert build_text_fallback(payload) == confirmation
