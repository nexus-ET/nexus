"""Tests for booking assignment notification chat persistence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.notification_service import persist_booking_confirmation_in_chat


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
