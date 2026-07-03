from unittest.mock import MagicMock, patch

from app.services.status_definitions_seed import seed_status_definitions_if_empty


def test_seed_status_definitions_if_empty_skips_when_rows_exist():
    db = MagicMock()
    db.query.return_value.limit.return_value.first.return_value = 1
    assert seed_status_definitions_if_empty(db) is False
    db.execute.assert_not_called()


def test_seed_status_definitions_if_empty_inserts_when_table_empty():
    db = MagicMock()
    db.query.return_value.limit.return_value.first.return_value = None
    assert seed_status_definitions_if_empty(db) is True
    assert db.execute.call_count >= 7
    db.commit.assert_called_once()
