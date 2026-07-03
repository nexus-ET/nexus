"""Tests for View Journey funnel status backfill and pipeline sync."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.student_status_service import (
    ensure_funnel_journey_history,
    resolve_effective_lead_status_id,
    sync_lead_pipeline_status_id,
)


def test_resolve_effective_lead_status_id_from_history() -> None:
    lead = SimpleNamespace(id=5, status_definition_id=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (2,)

    assert resolve_effective_lead_status_id(db, lead) == 2


def test_sync_lead_pipeline_status_id_updates_null_fk() -> None:
    lead = SimpleNamespace(
        id=5,
        status_definition_id=None,
        status_entered_at=None,
        updated_at=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (3,)

    changed = sync_lead_pipeline_status_id(db, lead)

    assert changed is True
    assert lead.status_definition_id == 3
    db.commit.assert_called_once()


def test_ensure_funnel_journey_history_backfills_outreach_and_engagement() -> None:
    lead = SimpleNamespace(
        id=7,
        status_definition_id=None,
        status_entered_at=None,
        updated_at=None,
        created_at=datetime(2026, 7, 1, 10, 0, 0),
    )
    db = MagicMock()

    new_def = SimpleNamespace(id=1, stage_name="Lead: New")
    outreach_def = SimpleNamespace(id=2, stage_name="Lead: Outreach")
    engagement_def = SimpleNamespace(id=3, stage_name="Lead: Engagement")

    def _history_exists(_db, _student_id, stage_name: str) -> bool:
        return stage_name in recorded_stages

    recorded_stages = {"Lead: New"}

    def _record_and_track(*args, **kwargs):
        stage_id = kwargs.get("status_id")
        if stage_id == 2:
            recorded_stages.add("Lead: Outreach")
        elif stage_id == 3:
            recorded_stages.add("Lead: Engagement")

    advisor_time = datetime(2026, 7, 1, 10, 5, 0)
    candidate_time = datetime(2026, 7, 1, 10, 10, 0)

    with (
        patch(
            "app.services.status_definitions_seed.ensure_status_definition_funnel_links",
            return_value=False,
        ),
        patch(
            "app.services.student_status_service._status_history_has_stage",
            side_effect=_history_exists,
        ),
        patch(
            "app.services.student_status_service.get_status_definition_by_name",
            side_effect=lambda _db, name: {
                "Lead: New": new_def,
                "Lead: Outreach": outreach_def,
                "Lead: Engagement": engagement_def,
            }.get(name),
        ),
        patch(
            "app.services.student_status_service.record_status_history",
            side_effect=_record_and_track,
        ) as record_history,
        patch("app.services.student_status_service.resolve_effective_lead_status_id", return_value=None),
        patch(
            "app.services.student_status_service._infer_funnel_history_time",
            side_effect=lambda _db, _lead, stage_name: {
                "Lead: New": datetime(2026, 7, 1, 10, 0, 0),
                "Lead: Outreach": advisor_time,
                "Lead: Engagement": candidate_time,
            }[stage_name],
        ),
    ):
        message_query = db.query.return_value.filter.return_value
        message_query.first.side_effect = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        changed = ensure_funnel_journey_history(db, lead, source="test")

    assert changed is True
    assert record_history.call_count == 2
    assert lead.status_definition_id == 3
