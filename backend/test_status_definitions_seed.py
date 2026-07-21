from unittest.mock import MagicMock

from app.services.status_definitions_seed import (
    ensure_status_definition_funnel_links,
    seed_status_definitions_if_empty,
)


def test_seed_status_definitions_if_empty_is_disabled():
    db = MagicMock()
    db.query.return_value.limit.return_value.first.return_value = None
    assert seed_status_definitions_if_empty(db) is False
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_ensure_status_definition_funnel_links_is_disabled():
    db = MagicMock()
    assert ensure_status_definition_funnel_links(db) is False
    db.commit.assert_not_called()
