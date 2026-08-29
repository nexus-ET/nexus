"""Tests for Meta WhatsApp interactive intake delivery."""

from app.services.admissions_intake_flow import (
    IntakeReply,
    _build_country_list_picker,
    _build_degree_list_picker,
    _build_major_list_picker,
    _normalize_major_reply,
    _parse_degree_selection,
)
from app.services.meta_whatsapp_interactive import (
    _build_flow_payload,
    _build_list_payload,
    compose_intake_message_text,
    compose_intake_plain_text_fallback,
)
from app.services.twilio_whatsapp_interactive import (
    FlowPayload,
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


def test_meta_date_rows_are_single_line_with_complete_titles():
    picker = ListPickerPayload(
        kind="date",
        body="Pick a date",
        button="Choose date",
        items=[
            {
                "id": "date:2026-08-17",
                "item": "Today (Mon, Aug 17, 2026)",
                "description": "Available consultation day",
            },
            {
                "id": "date:2026-08-18",
                "item": "Tomorrow (Tue, Aug 18, 2026)",
                "description": "Available consultation day",
            },
            {
                "id": "date:2026-08-19",
                "item": "Wed, Aug 19, 2026",
                "description": "Available consultation day",
            },
        ],
    )

    payload = _build_list_payload("+919999999999", picker)
    rows = payload["interactive"]["action"]["sections"][0]["rows"]

    assert rows[0] == {
        "id": "date:2026-08-17",
        "title": "Today 17 Aug, 2026",
    }
    assert rows[1] == {
        "id": "date:2026-08-18",
        "title": "Tomorrow 18 Aug, 2026",
    }
    assert rows[2] == {
        "id": "date:2026-08-19",
        "title": "Wed 19 Aug, 2026",
    }
    assert "Today" in rows[0]["title"] and len(rows[0]["title"]) <= 24
    assert "Tomorrow" in rows[1]["title"] and len(rows[1]["title"]) <= 24
    assert all(len(row["title"]) <= 24 for row in rows)
    assert all("description" not in row for row in rows)


def test_meta_time_rows_are_single_line_and_keep_parseable_ids():
    picker = ListPickerPayload(
        kind="time",
        body="Pick a time",
        button="Choose time",
        items=[
            {"id": "time:49", "item": "10:00 AM", "description": "Consultation slot"},
            {"id": "time:52", "item": "5:00 PM"},
        ],
    )

    payload = _build_list_payload("+919999999999", picker)
    rows = payload["interactive"]["action"]["sections"][0]["rows"]

    assert rows == [
        {"id": "time:49", "title": "10:00 AM"},
        {"id": "time:52", "title": "5:00 PM"},
    ]
    assert all(len(row["title"]) <= 24 for row in rows)
    assert all("description" not in row for row in rows)


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


def test_country_picker_preserves_flags_for_meta_list_rows():
    picker = _build_country_list_picker("Which country are you considering?")
    payload = _build_list_payload("+919999999999", picker)
    rows = payload["interactive"]["action"]["sections"][0]["rows"]

    assert payload["interactive"]["action"]["button"] == "Explore countries"
    assert rows[0]["id"] == "UK"
    assert rows[0]["title"] == "🇬🇧 UK"
    assert any(row["title"] == "🇦🇺 Australia" for row in rows)


def test_major_picker_exposes_video_style_program_fields():
    picker = _build_major_list_picker("Which course or field interests you?")
    payload = _build_list_payload("+919999999999", picker)
    rows = payload["interactive"]["action"]["sections"][0]["rows"]

    assert payload["interactive"]["action"]["button"] == "Explore fields"
    assert [row["id"] for row in rows[:3]] == [
        "Computer Science",
        "Data Science & AI",
        "Business & Management",
    ]
    assert rows[0]["title"] == "💻 Computer Science"
    assert rows[2]["title"] == "💼 Business & Management"
    assert all(len(row["title"]) <= 24 for row in rows)
    assert _normalize_major_reply(rows[0]["title"]) == "Computer Science"


def test_degree_picker_uses_program_icons_with_parseable_titles():
    picker = _build_degree_list_picker("Which program level interests you?")
    payload = _build_list_payload("+919999999999", picker)
    rows = payload["interactive"]["action"]["sections"][0]["rows"]

    assert rows[0]["title"] == "🎓 Bachelor's Degree"
    assert all(row["title"].startswith("🎓 ") for row in rows)
    assert all(len(row["title"]) <= 24 for row in rows)
    assert _parse_degree_selection(rows[0]["title"]) == "Bachelor's Degree (3-4 years)"


def test_meta_flow_payload_opens_existing_booking_screen():
    payload = _build_flow_payload(
        "+919999999999",
        FlowPayload(
            body="Choose a date and time.",
            flow_token="nexus-lead-42-123",
            flow_id="987654321",
            button="Book consultation",
        ),
    )

    interactive = payload["interactive"]
    parameters = interactive["action"]["parameters"]
    assert interactive["type"] == "flow"
    assert parameters["flow_id"] == "987654321"
    assert parameters["flow_token"] == "nexus-lead-42-123"
    assert parameters["flow_action_payload"]["screen"] == "BOOKING"
