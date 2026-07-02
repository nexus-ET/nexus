"""Tests for inbound WhatsApp intake routing and full-name progression."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.lead import LeadStage
from app.services.admissions_intake_flow import (
    INTAKE_STEP_COMPLETE,
    INTAKE_STEP_CURRENT_LOCATION,
    INTAKE_STEP_FULL_NAME,
    _looks_like_full_name,
    process_intake_message,
)
from app.services.lead_conversation import find_lead_for_inbound_whatsapp
from app.services.twilio_ai_conversation import handle_ai_active_inbound


def test_looks_like_full_name_requires_first_and_last() -> None:
    assert _looks_like_full_name("Priya Sharma")
    assert not _looks_like_full_name("Priya")
    assert not _looks_like_full_name("ab")
    assert not _looks_like_full_name("WhatsApp Contact (+911234567890)")


def test_find_lead_for_inbound_whatsapp_prefers_active_intake_over_handoff() -> None:
    now = datetime.utcnow()
    outreach_lead = SimpleNamespace(
        id=10,
        phone_number="+919876543210",
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        intake_step=INTAKE_STEP_FULL_NAME,
        updated_at=now,
    )
    handoff_lead = SimpleNamespace(
        id=20,
        phone_number="+919876543210",
        stage=LeadStage.HANDOFF,
        is_human_locked=True,
        intake_step=INTAKE_STEP_COMPLETE,
        updated_at=now,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [handoff_lead, outreach_lead]

    with patch(
        "app.services.lead_conversation.lead_has_advisor_messages",
        side_effect=lambda _db, lead_id: lead_id == 10,
    ):
        matched = find_lead_for_inbound_whatsapp(db, "919876543210")

    assert matched is outreach_lead


def test_process_intake_full_name_advances_to_location() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="WhatsApp Contact (+911234567890)",
            intake_step=INTAKE_STEP_FULL_NAME,
            intake_context=None,
            preferred_country=None,
            current_location=None,
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        from app.config import settings

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "Priya Sharma",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_CURRENT_LOCATION
        assert lead.full_name == "Priya Sharma"
        assert "city and country" in reply.text.lower()

    asyncio.run(_run())


def test_handle_ai_active_inbound_processes_intake_before_inactive_agent_handoff() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="WhatsApp Contact (+911234567890)",
            intake_step=INTAKE_STEP_FULL_NAME,
            intake_context=None,
            preferred_country=None,
            current_location=None,
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
            stage=LeadStage.AI_ACTIVE,
            is_human_locked=False,
        )
        db = MagicMock()
        db.refresh = MagicMock()
        db.commit = MagicMock()

        intake_reply = SimpleNamespace(
            text="Thanks, Priya! Which city and country are you in right now?",
            confidence=1.0,
        )

        with (
            patch(
                "app.services.twilio_ai_conversation.get_runtime_agent_config",
                return_value=SimpleNamespace(is_active=False, keywords_trigger="human,advisor"),
            ),
            patch(
                "app.services.twilio_ai_conversation.process_intake_message",
                new_callable=AsyncMock,
                return_value=intake_reply,
            ) as process_intake,
            patch(
                "app.services.twilio_ai_conversation.persist_and_send_intake_reply",
                new_callable=AsyncMock,
            ),
            patch("app.services.twilio_ai_conversation._audit_ai_turn"),
            patch(
                "app.services.twilio_ai_conversation._execute_escalation_handoff",
                new_callable=AsyncMock,
            ) as escalate,
        ):
            result = await handle_ai_active_inbound(db, lead, "Priya Sharma", "+911234567890")

        process_intake.assert_awaited_once()
        escalate.assert_not_awaited()
        assert result == [intake_reply.text]

    asyncio.run(_run())


def test_handle_ai_active_inbound_silent_after_confirmed_booking() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=2,
            full_name="Priya Sharma",
            intake_step=INTAKE_STEP_COMPLETE,
            intake_context=None,
            preferred_country="UK",
            current_location="Mumbai, India",
            phone_number="+919876543210",
            academic_summary=None,
            consultation_scheduled_at=datetime(2026, 7, 15, 14, 0),
            wants_consultation_call=True,
            stage=LeadStage.AI_ACTIVE,
            is_human_locked=False,
        )
        db = MagicMock()
        db.refresh = MagicMock()
        db.commit = MagicMock()

        with (
            patch(
                "app.services.twilio_ai_conversation.get_runtime_agent_config",
                return_value=SimpleNamespace(is_active=True, keywords_trigger="human,advisor"),
            ),
            patch(
                "app.services.twilio_ai_conversation.handle_post_intake_booking_message",
                return_value=None,
            ),
            patch(
                "app.services.twilio_ai_conversation.persist_and_send_intake_reply",
                new_callable=AsyncMock,
            ) as send_reply,
        ):
            result = await handle_ai_active_inbound(db, lead, "hello", "+919876543210")

        send_reply.assert_not_awaited()
        assert result == []

    asyncio.run(_run())
