"""Tests for status_transitions lifecycle paths, permissions, and express comments."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.status_transition import TransitionType
from app.services.status_transition_permissions import can_use_restricted_lifecycle_transition
from app.services.status_transition_service import (
    build_express_transition_comment,
    can_transition_to,
    collect_skipped_standard_path_stages,
)


def _user(*, superuser: bool = False, role_name: str = "Student Advisor") -> SimpleNamespace:
    return SimpleNamespace(
        is_superuser=superuser,
        admin_role_ref=SimpleNamespace(name=role_name),
        role=role_name,
    )


def test_manager_can_use_restricted_transitions() -> None:
    assert can_use_restricted_lifecycle_transition(_user(role_name="Student Manager")) is True
    assert can_use_restricted_lifecycle_transition(_user(role_name="Student Advisor")) is False
    assert can_use_restricted_lifecycle_transition(_user(superuser=True)) is True


def test_collect_skipped_standard_path_stages_for_new_to_counselling() -> None:
    db = MagicMock()

    definitions = {
        1: SimpleNamespace(id=1, stage_name="Lead: New", next_stage_id=2),
        2: SimpleNamespace(id=2, stage_name="Lead: Outreach", next_stage_id=3),
        3: SimpleNamespace(id=3, stage_name="Lead: Engagement", next_stage_id=4),
        4: SimpleNamespace(id=4, stage_name="Lead: Session Booked", next_stage_id=12),
        12: SimpleNamespace(id=12, stage_name="Counselling: Scheduled", next_stage_id=13),
    }

    def _get_definition(_db, status_id: int):
        return definitions[status_id]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.status_transition_service.get_status_definition",
            _get_definition,
        )
        skipped = collect_skipped_standard_path_stages(db, 1, 12)

    assert skipped == [
        "Lead: Outreach",
        "Lead: Engagement",
        "Lead: Session Booked",
    ]


def test_build_express_transition_comment_includes_skipped_stages() -> None:
    db = MagicMock()

    definitions = {
        3: SimpleNamespace(id=3, stage_name="Lead: Engagement", next_stage_id=4),
        4: SimpleNamespace(id=4, stage_name="Lead: Session Booked", next_stage_id=5),
        12: SimpleNamespace(id=12, stage_name="Counselling: Scheduled", next_stage_id=13),
        18: SimpleNamespace(id=18, stage_name="Document: In Preparation", next_stage_id=19),
    }

    def _get_definition(_db, status_id: int):
        return definitions[status_id]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.status_transition_service.get_status_definition",
            _get_definition,
        )
        monkeypatch.setattr(
            "app.services.status_transition_service.collect_skipped_standard_path_stages",
            lambda *_args, **_kwargs: ["Lead: Session Booked", "Counselling: Scheduled"],
        )
        comment = build_express_transition_comment(
            db,
            from_status_id=3,
            to_status_id=18,
            user_comment="Student already has docs ready.",
        )

    assert "Express jump performed" in comment
    assert "Document: In Preparation" in comment
    assert "Student already has docs ready." in comment


def test_express_transition_requires_manager_permission(monkeypatch) -> None:
    db = MagicMock()
    configured = SimpleNamespace(
        transition_type=TransitionType.EXPRESS,
        to_status_id=12,
    )

    monkeypatch.setattr(
        "app.services.status_transition_service._definition_exists",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "app.services.status_transition_service._lookup_transition_row",
        lambda *_args, **_kwargs: configured,
    )

    blocked = can_transition_to(
        db,
        1,
        12,
        transition_type="express",
        acting_user=_user(role_name="Student Advisor"),
    )
    allowed = can_transition_to(
        db,
        1,
        12,
        transition_type="express",
        acting_user=_user(role_name="Student Manager"),
    )

    assert blocked.allowed is False
    assert "Unauthorized Attempt" in blocked.reason
    assert allowed.allowed is True
    assert allowed.transition_type == "express"
