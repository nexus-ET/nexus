"""Keep candidate_test_scores.id sequence ahead of existing rows.

Staging (and any DB that imported rows with explicit ids) can leave the
serial sequence at 1, causing UniqueViolation on the next INSERT.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_SYNC_SQL = text(
    """
    SELECT setval(
        pg_get_serial_sequence('candidate_test_scores', 'id'),
        COALESCE((SELECT MAX(id) FROM candidate_test_scores), 1),
        (SELECT EXISTS (SELECT 1 FROM candidate_test_scores))
    )
    """
)


def sync_candidate_test_scores_id_sequence(db: Session) -> int | None:
    """Advance the id sequence to MAX(id). Returns the new last_value when available."""
    result = db.execute(_SYNC_SQL).scalar()
    return int(result) if result is not None else None
