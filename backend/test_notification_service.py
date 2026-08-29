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
    assert "reschedule" in reply.text.lower()
    assert "cancel" in reply.text.lower()
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


def test_build_admin_assignment_whatsapp_message_is_lean_alert() -> None:
    from app.services.notification_service import _build_admin_assignment_whatsapp_message

    booking = SimpleNamespace(
        id=42,
        scheduled_time=datetime(2026, 7, 24, 15, 30),
        candidate_name="Aisha Khan",
        candidate_phone="+919876543210",
        candidate_email="aisha@example.com",
        status="SCHEDULED",
        notes="Prefers evening follow-up",
        lead_id=99,
    )
    db = MagicMock()

    with patch("app.config.settings.FRONTEND_URL", "https://app.example.com"):
        message = _build_admin_assignment_whatsapp_message(
            db,
            admin_name="Ishq Ahmed",
            booking=booking,
            lead=None,
        )

    assert "Hi Ishq Ahmed" in message
    assert "New booking assigned to you." in message
    assert "Aisha Khan" in message
    assert "Booking #42" in message
    assert "https://app.example.com/prospects/99" in message
    assert "IELTS" not in message
    assert "Prefers evening follow-up" not in message


def test_morning_digest_and_nudge_message_builders() -> None:
    from app.services.admin_session_reminders import (
        build_morning_digest_message,
        build_session_nudge_message,
        build_cancel_alert_message,
        build_reschedule_alert_message,
    )

    booking = SimpleNamespace(
        id=7,
        scheduled_time=datetime(2026, 7, 24, 10, 0),
        candidate_name="Ravi",
        lead_id=5,
    )

    with patch("app.config.settings.FRONTEND_URL", "https://app.example.com"):
        digest = build_morning_digest_message(
            admin_name="Counsellor",
            day_label="Fri, Jul 24 2026",
            bookings=[booking],
        )
        nudge = build_session_nudge_message(
            admin_name="Counsellor",
            booking=booking,
            minutes=15,
        )
        cancel = build_cancel_alert_message(
            admin_name="Counsellor",
            candidate_name="Ravi",
            scheduled_time=booking.scheduled_time,
            booking_id=7,
            lead_id=5,
        )
        reschedule = build_reschedule_alert_message(
            admin_name="Counsellor",
            candidate_name="Ravi",
            previous_time=booking.scheduled_time,
            booking_id=7,
            lead_id=5,
        )

    assert "Your counselling schedule" in digest
    assert "Ravi" in digest
    assert "in 15 mins" in nudge
    assert "cancelled" in cancel.lower()
    assert "rescheduled" in reschedule.lower()


def test_send_whatsapp_admin_assignment_sends_to_admin_phone() -> None:
    db = MagicMock()
    service = NotificationService(db)
    booking = SimpleNamespace(
        id=55,
        scheduled_time=datetime(2026, 7, 24, 11, 0),
        candidate_name="Ravi",
        candidate_phone="+911111111111",
        candidate_email=None,
        status="SCHEDULED",
        notes=None,
        outcome_key=None,
        lead_id=None,
    )
    admin = SimpleNamespace(id=7, phone_number="+918888888888")

    with (
        patch(
            "app.services.notification_service._build_admin_assignment_whatsapp_message",
            return_value="Hi Counsellor, assignment details",
        ),
        patch(
            "app.services.settings_service.get_bool_setting",
            return_value=True,
        ),
        patch(
            "app.services.notification_service._phone_has_open_whatsapp_window",
            return_value=True,
        ),
        patch(
            "app.services.notification_service.send_message",
            new_callable=AsyncMock,
            return_value=True,
        ) as send_message,
        patch.object(service, "_log_attempt") as log_attempt,
    ):
        status = asyncio.run(
            service.send_whatsapp_admin_assignment(
                booking=booking,
                admin=admin,
                admin_name="Counsellor",
                lead=None,
            )
        )

    assert status == "sent"
    send_message.assert_awaited_once_with("+918888888888", "Hi Counsellor, assignment details")
    log_attempt.assert_called_once()
    assert log_attempt.call_args.kwargs["channel"] == "whatsapp_admin"
    assert log_attempt.call_args.kwargs["status"] == "sent"


def test_send_whatsapp_admin_assignment_skips_without_phone() -> None:
    db = MagicMock()
    service = NotificationService(db)
    booking = SimpleNamespace(
        id=56,
        scheduled_time=datetime(2026, 7, 24, 11, 0),
        candidate_name="Ravi",
        candidate_phone="+911111111111",
        candidate_email=None,
        status="SCHEDULED",
        notes=None,
        lead_id=None,
    )
    admin = SimpleNamespace(id=8, phone_number=None)

    with (
        patch(
            "app.services.notification_service._build_admin_assignment_whatsapp_message",
            return_value="Hi Counsellor, assignment details",
        ),
        patch(
            "app.services.settings_service.get_bool_setting",
            return_value=True,
        ),
        patch(
            "app.services.notification_service.send_message",
            new_callable=AsyncMock,
            return_value=True,
        ) as send_message,
        patch.object(service, "_log_attempt") as log_attempt,
    ):
        status = asyncio.run(
            service.send_whatsapp_admin_assignment(
                booking=booking,
                admin=admin,
                admin_name="Counsellor",
                lead=None,
            )
        )

    assert status == "skipped"
    send_message.assert_not_awaited()
    assert log_attempt.call_args.kwargs["status"] == "skipped"
