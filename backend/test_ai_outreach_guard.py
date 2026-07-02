from unittest.mock import MagicMock

import pytest

from app.services.twilio_ai_conversation import (
    assert_ai_outreach_allowed,
    lead_has_prior_ai_outreach,
)


def test_lead_has_prior_ai_outreach_detects_advisor_message():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = 99
    assert lead_has_prior_ai_outreach(db, lead_id=7) is True


def test_lead_has_prior_ai_outreach_false_when_no_messages():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert lead_has_prior_ai_outreach(db, lead_id=7) is False


def test_assert_ai_outreach_allowed_blocks_duplicate_without_force_restart(monkeypatch):
    db = MagicMock()
    lead = MagicMock()
    lead.id = 12

    monkeypatch.setattr(
        "app.services.twilio_ai_conversation.lead_has_prior_ai_outreach",
        lambda _db, _lead_id: True,
    )

    with pytest.raises(ValueError, match="already in progress"):
        assert_ai_outreach_allowed(db, lead, force_restart=False)
