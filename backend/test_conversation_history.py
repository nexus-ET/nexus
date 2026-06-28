"""Tests for WhatsApp conversation history windowing."""

from types import SimpleNamespace

from app.services.twilio_ai_conversation import (
    OUTREACH_SESSION_MARKER,
    _session_start_index,
)


def _msg(sender: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(sender=sender, text=text)


def test_session_start_index_uses_latest_welcome():
    rows = [
        _msg("candidate", "Gggggg"),
        _msg("advisor", "old reply"),
        _msg("advisor", f"Hi Ish! {OUTREACH_SESSION_MARKER}"),
        _msg("candidate", "Hello"),
    ]
    assert _session_start_index(rows) == 2


def test_session_start_index_without_welcome_keeps_all():
    rows = [_msg("candidate", "Gggggg"), _msg("advisor", "old reply")]
    assert _session_start_index(rows) == 0
