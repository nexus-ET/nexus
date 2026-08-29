"""Tests for inbound WhatsApp intake routing and full-name progression."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.lead import LeadStage
from app.services.admissions_intake_flow import (
    INTAKE_STEP_COMPLETE,
    INTAKE_STEP_FULL_NAME,
    INTAKE_STEP_TARGET_DEGREE,
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


def test_accept_intake_name_reply_accepts_single_name() -> None:
    from app.services.admissions_intake_flow import _accept_intake_name_reply

    assert _accept_intake_name_reply("Ishq") == "Ishq"
    assert _accept_intake_name_reply("Priya Sharma") == "Priya Sharma"
    assert _accept_intake_name_reply("a") is None


def test_accept_intake_name_reply_rejects_greetings() -> None:
    from app.services.admissions_intake_flow import _accept_intake_name_reply

    assert _accept_intake_name_reply("hi") is None
    assert _accept_intake_name_reply("Hello!") is None
    assert _accept_intake_name_reply("hey") is None
    assert _accept_intake_name_reply("Ishq") == "Ishq"


def test_lead_has_real_name_accepts_single_name() -> None:
    from types import SimpleNamespace

    from app.services.admissions_intake_flow import _lead_has_real_name

    assert _lead_has_real_name(SimpleNamespace(full_name="Ishq"))
    assert _lead_has_real_name(SimpleNamespace(full_name="Priya Sharma"))
    assert not _lead_has_real_name(SimpleNamespace(full_name="WhatsApp Contact (+911234567890)"))
    assert not _lead_has_real_name(SimpleNamespace(full_name="a"))


def test_begin_whatsapp_intake_force_restart_clears_stale_location() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.admissions_intake_flow import (
        INTAKE_STEP_TARGET_DEGREE,
        begin_whatsapp_intake_session,
    )

    lead = SimpleNamespace(
        full_name="Henry Ford",
        intake_step="TARGET_COUNTRY",
        current_location="Mumbai, India",
        intake_context='{"pending_country": "UK"}',
        preferred_country=None,
        additional_data=None,
    )
    db = MagicMock()
    begin_whatsapp_intake_session(db, lead, force_full_restart=True)
    assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
    assert lead.current_location is None
    assert lead.intake_context is None
    db.commit.assert_called_once()


def test_greeting_on_degree_step_does_not_use_there_prefix() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=3,
            full_name="WhatsApp Contact (+911234567890)",
            intake_step=INTAKE_STEP_TARGET_DEGREE,
            intake_context=None,
            preferred_country=None,
            current_location=None,
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
            additional_data=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        from app.config import settings

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "hello",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
        assert not reply.text.lower().startswith("there,")
        assert "there," not in reply.text.lower()
        assert "not recognized" not in reply.text.lower()
        assert "degree" in reply.text.lower()
        assert reply.list_picker is not None

    asyncio.run(_run())


def test_greeting_skips_full_name_and_asks_degree() -> None:
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
            additional_data=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        from app.config import settings

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "hi",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
        assert "full name" not in reply.text.lower()
        assert "free study abroad consultation" not in reply.text.lower()
        assert "there," not in reply.text.lower()
        assert "program (degree)" in reply.text.lower() or "degree" in reply.text.lower()
        assert reply.list_picker is not None

    asyncio.run(_run())


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


def test_process_intake_full_name_advances_to_degree() -> None:
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

        assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
        assert lead.full_name == "Priya Sharma"
        assert "program (degree)" in reply.text.lower()
        assert "city and country" not in reply.text.lower()

    asyncio.run(_run())


def test_process_intake_single_name_advances_to_degree() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Henry Ford",
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
                "Ishq",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
        assert lead.full_name == "Ishq"
        assert "program (degree)" in reply.text.lower()
        assert "city and country" not in reply.text.lower()
        assert "full first and last name" not in reply.text.lower()

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
            text="Thanks, Priya! Which program (degree) are you targeting?",
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


def test_no_thanks_on_call_consent_returns_management_buttons() -> None:
    async def _run() -> None:
        from app.services.admissions_intake_flow import (
            BOOKING_BOOK_SESSION_BUTTON_ID,
            BOOKING_NOT_INTERESTED_BUTTON_ID,
            INTAKE_STEP_CALL_CONSENT,
        )

        lead = SimpleNamespace(
            id=1,
            full_name="Sahil Kumar",
            intake_step=INTAKE_STEP_CALL_CONSENT,
            intake_context=None,
            preferred_country="UK",
            current_location="Mumbai, India",
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
            test_scores="English: 7.0",
            gre_score=None,
            gmat_score=None,
            english_test_scores="7.0",
        )
        db = MagicMock()
        db.commit = MagicMock()

        from app.config import settings

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "No thanks",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_COMPLETE
        assert lead.wants_consultation_call is False
        assert "saved your profile" in reply.text.lower()
        assert "book session" in reply.text.lower()
        assert reply.quick_reply is not None
        action_ids = [action["id"] for action in reply.quick_reply.actions]
        assert action_ids == [BOOKING_BOOK_SESSION_BUTTON_ID, BOOKING_NOT_INTERESTED_BUTTON_ID]

    asyncio.run(_run())


def test_not_interested_starts_marketing_consent_flow(monkeypatch) -> None:
    async def _run() -> None:
        from app.services.admissions_intake_flow import (
            INTAKE_STEP_COMPLETE,
            INTAKE_STEP_MARKETING_CONSENT,
            MARKETING_OPT_IN_BUTTON_ID,
            MARKETING_OPT_OUT_BUTTON_ID,
            handle_post_intake_booking_message,
        )

        monkeypatch.setattr(
            "app.services.admissions_intake_flow._lead_has_active_consultation_booking",
            lambda _db, _lead: False,
        )

        lead = SimpleNamespace(
            id=2,
            full_name="Sahil Kumar",
            intake_step=INTAKE_STEP_COMPLETE,
            intake_context=None,
            preferred_country="UK",
            current_location="Mumbai, India",
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=False,
            stage=LeadStage.AI_ACTIVE,
            is_human_locked=False,
        )
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        reply = handle_post_intake_booking_message(db, lead, "Not Interested")

        assert lead.intake_step == INTAKE_STEP_MARKETING_CONSENT
        assert "timely information" in reply.text.lower()
        assert reply.quick_reply is not None
        action_ids = [action["id"] for action in reply.quick_reply.actions]
        assert action_ids == [MARKETING_OPT_IN_BUTTON_ID, MARKETING_OPT_OUT_BUTTON_ID]

    asyncio.run(_run())
