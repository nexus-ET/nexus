"""Tests for WhatsApp reschedule/cancel routing and pipeline status capture."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.lead import LeadStage
from app.services.admissions_intake_flow import (
    INTAKE_STEP_COMPLETE,
    INTAKE_STEP_PICK_DATE,
    INTAKE_STEP_PICK_TIME,
    ListPickerPayload,
    handle_post_intake_booking_message,
    is_cancel_command,
)
from app.services.status_transition_service import can_transition_to
from app.services.twilio_ai_conversation import handle_ai_active_inbound


@pytest.mark.parametrize(
    "message",
    [
        "cancel",
        "*cancel*",
        "Cancel",
        "cancel.",
        "cancel please",
        "please cancel",
        "cancel my appointment",
        "cancel appointment",
        "I want to cancel",
    ],
)
def test_is_cancel_command_recognizes_common_phrases(message: str) -> None:
    assert is_cancel_command(message)


def test_engagement_can_transition_to_session_rescheduled() -> None:
    db = MagicMock()

    def _exists(_db, status_id: int) -> bool:
        return status_id in {3, 5}

    def _get_definition(_db, status_id: int):
        return SimpleNamespace(
            id=status_id,
            stage_name="Lead: Engagement" if status_id == 3 else "Lead: Session Rescheduled",
            next_stage_id=4,
        )

    with (
        patch(
            "app.services.status_transition_service._definition_exists",
            side_effect=_exists,
        ),
        patch(
            "app.services.status_transition_service.get_status_definition",
            side_effect=_get_definition,
        ),
    ):
        result = can_transition_to(db, 3, 5)
    assert result.allowed is True


def test_reschedule_from_pick_time_shows_date_picker() -> None:
    selected = (date.today() + timedelta(days=3)).isoformat()
    lead = SimpleNamespace(
        id=1,
        full_name="Ishq Test",
        intake_step=INTAKE_STEP_PICK_TIME,
        intake_context=json.dumps({"selected_date": selected, "time_slot_ids": [1, 2]}),
        consultation_scheduled_at=datetime.combine(date.fromisoformat(selected), datetime.min.time()),
        wants_consultation_call=True,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        calendar_booking_id="NEXUS-SLOT-1",
    )
    db = MagicMock()
    db.refresh = MagicMock()
    db.commit = MagicMock()

    with (
        patch(
            "app.services.admissions_intake_flow.release_lead_consultation_slot",
        ) as release_slot,
        patch(
            "app.services.admissions_intake_flow._reset_booking_intake_context",
        ) as reset_context,
        patch(
            "app.services.admissions_intake_flow._build_date_picker_payload",
        ) as build_date_picker,
        patch(
            "app.services.admissions_intake_flow._build_booking_flow_payload",
            return_value=None,
        ),
        patch(
            "app.services.messaging.get_active_provider",
            return_value="whatsapp",
        ),
        patch(
            "app.services.student_status_service.on_session_rescheduled",
        ) as on_rescheduled,
    ):
        build_date_picker.return_value = ListPickerPayload(
            kind="date",
            body="Pick a date",
            button="Choose date",
            items=[{"id": "date:2026-07-10", "item": "Thu 10 Jul", "description": "Tap"}],
        )
        reply = handle_post_intake_booking_message(db, lead, "reschedule")

    assert reply is not None
    assert reply.list_picker is not None
    assert reply.list_picker.button == "Choose date"
    assert lead.intake_step == INTAKE_STEP_PICK_DATE
    release_slot.assert_called_once()
    reset_context.assert_called_once()
    on_rescheduled.assert_called_once()


def test_handle_ai_active_reschedule_skips_process_intake_when_pick_time() -> None:
    selected = (date.today() + timedelta(days=3)).isoformat()
    lead = SimpleNamespace(
        id=2,
        full_name="Ishq Test",
        intake_step=INTAKE_STEP_PICK_TIME,
        intake_context=json.dumps({"selected_date": selected}),
        consultation_scheduled_at=datetime(2026, 7, 10, 14, 0),
        wants_consultation_call=True,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
    )
    db = MagicMock()
    db.refresh = MagicMock()
    db.commit = MagicMock()

    booking_reply = SimpleNamespace(
        text="Pick a new date",
        confidence=1.0,
        suppress_outbound=False,
        list_picker=SimpleNamespace(button="Choose date"),
    )

    async def _run() -> None:
        with (
            patch(
                "app.services.twilio_ai_conversation.get_runtime_agent_config",
                return_value=SimpleNamespace(
                    is_active=True,
                    keywords_trigger="human",
                    ai_model="test-model",
                ),
            ),
            patch(
                "app.services.twilio_ai_conversation.handle_post_intake_booking_message",
                return_value=booking_reply,
            ) as handle_booking,
            patch(
                "app.services.twilio_ai_conversation.process_intake_message",
                new_callable=AsyncMock,
            ) as process_intake,
            patch(
                "app.services.twilio_ai_conversation.persist_and_send_intake_reply",
                new_callable=AsyncMock,
            ),
            patch("app.services.twilio_ai_conversation._audit_ai_turn"),
        ):
            result = await handle_ai_active_inbound(db, lead, "reschedule", "+918754545407")

        handle_booking.assert_called_once()
        process_intake.assert_not_awaited()
        assert result == ["Pick a new date"]

    asyncio.run(_run())


def test_cancel_from_pick_time_returns_confirmation_not_time_picker() -> None:
    selected = (date.today() + timedelta(days=3)).isoformat()
    lead = SimpleNamespace(
        id=3,
        full_name="Ishq Test",
        intake_step=INTAKE_STEP_PICK_TIME,
        intake_context=json.dumps({"selected_date": selected, "time_slot_ids": [1, 2]}),
        consultation_scheduled_at=datetime(2026, 7, 10, 14, 0),
        wants_consultation_call=True,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        calendar_booking_id="NEXUS-SLOT-1",
    )
    db = MagicMock()
    db.refresh = MagicMock()
    db.commit = MagicMock()

    with (
        patch(
            "app.services.admissions_intake_flow.release_lead_consultation_slot",
        ) as release_slot,
        patch(
            "app.services.admissions_intake_flow._reset_booking_intake_context",
        ) as reset_context,
        patch(
            "app.services.student_status_service.on_session_cancelled",
        ) as on_cancelled,
    ):
        reply = handle_post_intake_booking_message(db, lead, "cancel")

    assert reply is not None
    assert reply.list_picker is None
    assert reply.quick_reply is None
    assert "cancelled" in reply.text.lower()
    assert lead.intake_step == INTAKE_STEP_COMPLETE
    release_slot.assert_called_once()
    reset_context.assert_called_once()
    on_cancelled.assert_called_once()


def test_handle_ai_active_cancel_skips_process_intake_when_pick_time() -> None:
    selected = (date.today() + timedelta(days=3)).isoformat()
    lead = SimpleNamespace(
        id=4,
        full_name="Ishq Test",
        intake_step=INTAKE_STEP_PICK_TIME,
        intake_context=json.dumps({"selected_date": selected}),
        consultation_scheduled_at=datetime(2026, 7, 10, 14, 0),
        wants_consultation_call=True,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
    )
    db = MagicMock()
    db.refresh = MagicMock()
    db.commit = MagicMock()

    booking_reply = SimpleNamespace(
        text="Your appointment has been cancelled.",
        confidence=1.0,
        suppress_outbound=False,
        list_picker=None,
        quick_reply=None,
    )

    async def _run() -> None:
        with (
            patch(
                "app.services.twilio_ai_conversation.get_runtime_agent_config",
                return_value=SimpleNamespace(
                    is_active=True,
                    keywords_trigger="human",
                    ai_model="test-model",
                ),
            ),
            patch(
                "app.services.twilio_ai_conversation.handle_post_intake_booking_message",
                return_value=booking_reply,
            ) as handle_booking,
            patch(
                "app.services.twilio_ai_conversation.process_intake_message",
                new_callable=AsyncMock,
            ) as process_intake,
            patch(
                "app.services.twilio_ai_conversation.persist_and_send_intake_reply",
                new_callable=AsyncMock,
            ),
            patch("app.services.twilio_ai_conversation._audit_ai_turn"),
        ):
            result = await handle_ai_active_inbound(db, lead, "cancel", "+918754545407")

        handle_booking.assert_called_once()
        process_intake.assert_not_awaited()
        assert result == ["Your appointment has been cancelled."]

    asyncio.run(_run())
