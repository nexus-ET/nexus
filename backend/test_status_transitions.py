from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.status_transition_service import can_transition_to


def _definition(
    definition_id: int,
    stage_name: str,
    *,
    next_stage_id: int | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=definition_id,
        stage_name=stage_name,
        category="Lead",
        description=None,
        next_stage_id=next_stage_id,
    )


DEFINITIONS = {
    1: _definition(1, "Lead: New", next_stage_id=2),
    2: _definition(2, "Lead: Outreach", next_stage_id=3),
    3: _definition(3, "Lead: Engagement", next_stage_id=4),
    4: _definition(4, "Lead: Session Booked", next_stage_id=5),
    5: _definition(5, "Lead: Session Rescheduled", next_stage_id=3),
    6: _definition(6, "Lead: Session Cancelled", next_stage_id=3),
    12: _definition(12, "Counselling: Scheduled", next_stage_id=13),
    33: _definition(33, "Visa: Application Approved", next_stage_id=34),
    44: _definition(44, "Prospect: Cancelled & Closed", next_stage_id=11),
    45: _definition(45, "Prospect: Relaunch", next_stage_id=1),
}


@pytest.fixture
def patched_transition_env(monkeypatch):
    db = MagicMock()

    def _exists(_db, status_id: int) -> bool:
        return status_id in DEFINITIONS

    def _get_definition(_db, status_id: int):
        return DEFINITIONS[status_id]

    monkeypatch.setattr(
        "app.services.status_transition_service._definition_exists",
        _exists,
    )
    monkeypatch.setattr(
        "app.services.status_transition_service.get_status_definition",
        _get_definition,
    )
    monkeypatch.setattr(
        "app.services.status_transition_service._lookup_transition_row",
        lambda *_args, **_kwargs: None,
    )
    return db


def test_can_transition_forward_step(patched_transition_env):
    result = can_transition_to(patched_transition_env, 1, 2)
    assert result.allowed is True
    assert result.requires_override_comment is False


def test_can_transition_blocks_illegal_jump(patched_transition_env):
    result = can_transition_to(patched_transition_env, 1, 33)
    assert result.allowed is False
    assert "Illegal transition" in result.reason


def test_can_transition_admin_override_requires_comment(patched_transition_env):
    result = can_transition_to(patched_transition_env, 1, 33, allow_override=True)
    assert result.allowed is True
    assert result.requires_override_comment is True
    assert result.is_override is True


def test_terminal_status_blocks_automation(patched_transition_env):
    result = can_transition_to(patched_transition_env, 44, 2)
    assert result.allowed is False
    assert "Terminal" in result.reason


def test_terminal_relaunch_requires_admin(patched_transition_env):
    blocked = can_transition_to(patched_transition_env, 44, 45, allow_override=False)
    assert blocked.allowed is False

    allowed = can_transition_to(patched_transition_env, 44, 45, allow_override=True)
    assert allowed.allowed is True


def test_session_booked_allows_reschedule_and_cancel(patched_transition_env):
    reschedule = can_transition_to(patched_transition_env, 4, 5)
    cancel = can_transition_to(patched_transition_env, 4, 6)
    assert reschedule.allowed is True
    assert cancel.allowed is True


def test_engagement_allows_reschedule_and_cancel(patched_transition_env):
    reschedule = can_transition_to(patched_transition_env, 3, 5)
    cancel = can_transition_to(patched_transition_env, 3, 6)
    assert reschedule.allowed is True
    assert cancel.allowed is True


def test_repeat_reschedule_logs_again_with_force_repeat(patched_transition_env):
    blocked = can_transition_to(patched_transition_env, 5, 5)
    assert blocked.allowed is True
    assert "already set" in blocked.reason

    repeat = can_transition_to(patched_transition_env, 5, 5, force_repeat=True)
    assert repeat.allowed is True
    assert "Repeatable event" in repeat.reason


def test_cancelled_lead_can_rebook_or_repeat_cancel(patched_transition_env):
    assert can_transition_to(patched_transition_env, 6, 4).allowed is True
    assert can_transition_to(patched_transition_env, 6, 5).allowed is True
    assert can_transition_to(patched_transition_env, 6, 6, force_repeat=True).allowed is True
