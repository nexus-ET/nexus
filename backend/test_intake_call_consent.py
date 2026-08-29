"""Tests for the CALL_CONSENT step and the booking steps that follow it.

Covers the consultation-consent reply arriving as a Meta interactive button id,
as the button title, and as free text, plus the PICK_DATE / PICK_TIME hand-offs,
so an interactive payload change can never leave the intake without a next step.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services import admissions_intake_flow as flow
from app.services.admissions_intake_flow import (
    CALL_CONSENT_NO_BUTTON_ID,
    CALL_CONSENT_NO_TITLE,
    CALL_CONSENT_YES_BUTTON_ID,
    CALL_CONSENT_YES_TITLE,
    INTAKE_STEP_CALL_CONSENT,
    INTAKE_STEP_COMPLETE,
    INTAKE_STEP_PICK_DATE,
    INTAKE_STEP_PICK_TIME,
    _build_call_consent_quick_reply,
    _parse_time_selection,
    _parse_yes_no,
    process_intake_message,
)

OFFERED_DATES = [date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20)]

SLOTS = [
    SimpleNamespace(id=354, slot_date=date(2026, 8, 18), slot_time="10:00"),
    SimpleNamespace(id=355, slot_date=date(2026, 8, 18), slot_time="11:00"),
    SimpleNamespace(id=356, slot_date=date(2026, 8, 18), slot_time="12:00"),
    SimpleNamespace(id=357, slot_date=date(2026, 8, 18), slot_time="13:00"),
    SimpleNamespace(id=358, slot_date=date(2026, 8, 18), slot_time="14:00"),
    SimpleNamespace(id=359, slot_date=date(2026, 8, 18), slot_time="15:00"),
    SimpleNamespace(id=360, slot_date=date(2026, 8, 18), slot_time="16:00"),
    SimpleNamespace(id=361, slot_date=date(2026, 8, 18), slot_time="17:00"),
]


def _consent_lead(step: str = INTAKE_STEP_CALL_CONSENT, **overrides):
    context = {
        "target_degree": "Master's Degree (1-2 years)",
        "target_program": "Master's Degree (1-2 years)",
        "preferred_course": "Engineering",
        "target_major": "Engineering",
        "target_country": "Australia",
    }
    context.update(overrides.pop("context", {}))
    lead = SimpleNamespace(
        id=27,
        full_name="Ishq",
        intake_step=step,
        intake_context=json.dumps(context),
        preferred_country="Australia",
        current_location=None,
        phone_number="+918754545407",
        academic_summary="Degree: Master's Degree (1-2 years) | Major: Engineering | Country: Australia",
        english_test_scores=None,
        test_scores=None,
        consultation_scheduled_at=None,
        wants_consultation_call=None,
        stage=None,
        is_human_locked=False,
    )
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


@pytest.fixture
def booking_env(monkeypatch):
    """Stub calendar/booking lookups so intake steps run against a MagicMock session."""
    monkeypatch.setattr(flow, "_available_dates", lambda db, limit=8: list(OFFERED_DATES))
    monkeypatch.setattr(flow, "_available_times_for_date", lambda db, slot_day: list(SLOTS))
    monkeypatch.setattr(flow, "_get_active_consultation_booking", lambda db, lead: None)
    monkeypatch.setattr(flow, "is_whatsapp_flow_enabled", lambda: False)
    return MagicMock()


def _run_intake(db, lead, text):
    with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
        return asyncio.run(process_intake_message(db, lead, text, MagicMock(is_active=False)))


def test_consent_quick_reply_payload_is_parseable() -> None:
    """Every id and title we actually send must resolve to a yes/no decision."""
    payload = _build_call_consent_quick_reply("Would you like a free consultation call?")
    expected = {
        CALL_CONSENT_YES_BUTTON_ID: True,
        CALL_CONSENT_YES_TITLE: True,
        CALL_CONSENT_NO_BUTTON_ID: False,
        CALL_CONSENT_NO_TITLE: False,
    }
    assert len(payload.actions) == 2
    for action in payload.actions:
        assert _parse_yes_no(action["id"]) is expected[action["id"]]
        assert _parse_yes_no(action["title"]) is expected[action["title"]]


@pytest.mark.parametrize(
    "reply",
    ["yes", "Yes, please", "*Yes, please*", "yes please", "consent_yes", "consent:yes", "Sure", "yep"],
)
def test_parse_yes_no_accepts_consent_yes_variants(reply: str) -> None:
    assert _parse_yes_no(reply) is True


@pytest.mark.parametrize(
    "reply",
    ["no", "No thanks", "*No thanks*", "No thanks!", "consent_no", "consent:no", "nope", "not now"],
)
def test_parse_yes_no_accepts_consent_no_variants(reply: str) -> None:
    assert _parse_yes_no(reply) is False


def test_consent_button_id_advances_to_date_picker(booking_env) -> None:
    lead = _consent_lead()

    reply = _run_intake(booking_env, lead, CALL_CONSENT_YES_BUTTON_ID)

    assert lead.intake_step == INTAKE_STEP_PICK_DATE
    assert lead.wants_consultation_call is True
    assert reply.text.strip()
    assert reply.list_picker is not None
    assert [item["id"] for item in reply.list_picker.items] == [
        f"date:{slot_day.isoformat()}" for slot_day in OFFERED_DATES
    ]


def test_consent_button_title_advances_to_date_picker(booking_env) -> None:
    lead = _consent_lead()

    reply = _run_intake(booking_env, lead, CALL_CONSENT_YES_TITLE)

    assert lead.intake_step == INTAKE_STEP_PICK_DATE
    assert lead.wants_consultation_call is True
    assert reply.list_picker is not None


def test_consent_decline_closes_politely(booking_env) -> None:
    lead = _consent_lead()

    reply = _run_intake(booking_env, lead, CALL_CONSENT_NO_TITLE)

    assert lead.intake_step == INTAKE_STEP_COMPLETE
    assert lead.wants_consultation_call is False
    assert reply.text.strip()
    assert reply.quick_reply is not None


def test_unrecognized_consent_reply_reprompts_with_buttons(booking_env) -> None:
    lead = _consent_lead()

    reply = _run_intake(booking_env, lead, "hmmmm")

    assert lead.intake_step == INTAKE_STEP_CALL_CONSENT
    assert reply.text.strip()
    assert reply.quick_reply is not None


def test_date_list_id_advances_to_time_picker(booking_env) -> None:
    lead = _consent_lead(
        step=INTAKE_STEP_PICK_DATE,
        wants_consultation_call=True,
        context={"date_options": [slot_day.isoformat() for slot_day in OFFERED_DATES]},
    )

    reply = _run_intake(booking_env, lead, "date:2026-08-18")

    assert lead.intake_step == INTAKE_STEP_PICK_TIME
    context = json.loads(lead.intake_context)
    assert context["selected_date"] == "2026-08-18"
    assert reply.text.strip()
    assert [item["id"] for item in reply.list_picker.items] == [f"time:{slot.id}" for slot in SLOTS]
    assert all("description" not in item for item in reply.list_picker.items)
    assert all(len(item["item"]) <= 24 for item in reply.list_picker.items)


def test_unrecognized_date_reply_resends_date_picker(booking_env) -> None:
    lead = _consent_lead(
        step=INTAKE_STEP_PICK_DATE,
        wants_consultation_call=True,
        context={"date_options": [slot_day.isoformat() for slot_day in OFFERED_DATES]},
    )

    reply = _run_intake(booking_env, lead, "whenever works")

    assert lead.intake_step == INTAKE_STEP_PICK_DATE
    assert reply.text.strip()
    assert reply.list_picker is not None


def test_time_selection_resolves_button_id_and_label() -> None:
    for index, slot in enumerate(SLOTS, start=1):
        assert _parse_time_selection(f"time:{slot.id}", SLOTS) == index


@pytest.mark.parametrize(
    ("reply", "expected_index"),
    [
        ("5:00 PM", 8),
        ("Selected 5:00 PM", 8),
        ("2:00 PM", 5),
        ("2pm", 5),
        ("14:00", 5),
        ("10:00 AM", 1),
        ("3", 3),
    ],
)
def test_time_label_is_not_mistaken_for_a_list_index(reply: str, expected_index: int) -> None:
    assert _parse_time_selection(reply, SLOTS) == expected_index


def test_unavailable_explicit_time_reprompts_instead_of_guessing() -> None:
    assert _parse_time_selection("6:30 PM", SLOTS) is None


def test_time_button_id_completes_the_booking(booking_env, monkeypatch) -> None:
    lead = _consent_lead(
        step=INTAKE_STEP_PICK_TIME,
        wants_consultation_call=True,
        context={
            "selected_date": "2026-08-18",
            "time_slot_ids": [slot.id for slot in SLOTS],
        },
    )
    finalized: dict[str, object] = {}

    def _fake_finalize(db, target_lead, selected_date, slot_id, first_name):
        finalized.update(selected_date=selected_date, slot_id=slot_id, first_name=first_name)
        target_lead.intake_step = INTAKE_STEP_COMPLETE
        return flow.IntakeReply(text="Your consultation is confirmed.")

    monkeypatch.setattr(flow, "_finalize_consultation_booking", _fake_finalize)

    reply = _run_intake(booking_env, lead, "time:361")

    assert finalized == {
        "selected_date": date(2026, 8, 18),
        "slot_id": 361,
        "first_name": "Ishq",
    }
    assert lead.intake_step == INTAKE_STEP_COMPLETE
    assert reply.text.strip()
