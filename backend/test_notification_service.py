"""Tests for booking assignment notification chat persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.admissions_intake_flow import (
    BOOKING_CANCEL_BUTTON_ID,
    BOOKING_RESCHEDULE_BUTTON_ID,
    build_appointment_management_reply,
)
from app.services.notification_service import (
    NotificationService,
    persist_booking_confirmation_in_chat,
)


def test_build_appointment_management_reply_includes_buttons() -> None:
    reply = build_appointment_management_reply()
    assert "reschedule or cancel" in reply.text.lower()
    assert reply.quick_reply is not None
    action_ids = [action["id"] for action in reply.quick_reply.actions]
    assert action_ids == [BOOKING_RESCHEDULE_BUTTON_ID, BOOKING_CANCEL_BUTTON_ID]


def test_persist_booking_confirmation_in_chat_saves_advisor_message() -> None:
    lead = SimpleNamespace(id=27)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = lead

    with (
        patch(
            "app.services.notification_service._recent_identical_outbound",
            return_value=False,
        ),
        patch("app.services.notification_service.Message") as message_cls,
    ):
        message_cls.return_value = SimpleNamespace()
        saved = persist_booking_confirmation_in_chat(
            db,
            lead_id=27,
            candidate_phone="+918754545407",
            message="Hi Lemon, session with Ishq Ahmed is confirmed for Fri, Jul 03 at 10:00 AM.",
        )

    assert saved is True
    message_cls.assert_called_once()
    kwargs = message_cls.call_args.kwargs
    assert kwargs["lead_id"] == 27
    assert kwargs["sender"] == "advisor"
    assert "session with Ishq Ahmed is confirmed" in kwargs["text"]
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_persist_booking_confirmation_in_chat_skips_without_lead() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch(
        "app.services.notification_service.find_lead_by_phone",
        return_value=None,
    ):
        saved = persist_booking_confirmation_in_chat(
            db,
            lead_id=None,
            candidate_phone="+918754545407",
            message="Hi there",
        )

    assert saved is False
    db.add.assert_not_called()


def test_send_whatsapp_confirmation_sends_management_buttons_after_confirm() -> None:
    db = MagicMock()
    service = NotificationService(db)
    scheduled = datetime(2026, 7, 3, 10, 0)

    with (
        patch(
            "app.services.notification_service.send_message",
            new_callable=AsyncMock,
            return_value=True,
        ) as send_message,
        patch(
            "app.services.notification_service.persist_booking_confirmation_in_chat",
            return_value=True,
        ) as persist_chat,
        patch(
            "app.services.notification_service._send_whatsapp_appointment_management_followup",
            new_callable=AsyncMock,
            return_value="sent",
        ) as send_followup,
        patch(
            "app.services.notification_service._resolve_lead_for_booking_notification",
            return_value=None,
        ),
        patch.object(service, "_log_attempt"),
    ):
        status = asyncio.run(
            service.send_whatsapp_confirmation(
                booking_id=12,
                candidate_name="Lemon",
                admin_name="Ishq Ahmed",
                scheduled_time=scheduled,
                candidate_phone="+918754545407",
                lead_id=27,
            )
        )

    assert status == "sent"
    send_message.assert_awaited_once()
    persist_chat.assert_called_once()
    send_followup.assert_awaited_once_with(
        db,
        booking_id=12,
        lead_id=27,
        candidate_phone="+918754545407",
    )
