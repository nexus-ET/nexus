"""Tests for Meta WhatsApp interactive intake delivery."""

from app.services.admissions_intake_flow import IntakeReply
from app.services.meta_whatsapp_interactive import compose_intake_message_text
from app.services.twilio_whatsapp_interactive import ListPickerPayload, QuickReplyPayload


def test_compose_intake_message_text_includes_numbered_dates():
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
    body = compose_intake_message_text(reply)
    assert "Please pick a consultation date." in body
    assert "1. Mon, Jun 30, 2026" in body
    assert "2. Wed, Jul 01, 2026" in body
    assert "reply *1*" in body.lower()


def test_compose_intake_message_text_includes_time_options():
    reply = IntakeReply(
        text="Date selected: Mon, Jun 30, 2026. Now choose a time.",
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
    assert "Date selected" in body
    assert "1. 10:00 AM" in body
    assert "2. 02:00 PM" in body
