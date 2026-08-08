#!/usr/bin/env python3
"""Advance candidate_test_scores.id sequence past existing rows."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services.candidate_test_scores_sequence import (
    sync_candidate_test_scores_id_sequence,
)


def main() -> int:
    db = SessionLocal()
    try:
        before = db.execute(
            text(
                "SELECT last_value, is_called FROM candidate_test_scores_id_seq"
            )
        ).fetchone()
        max_id = db.execute(text("SELECT MAX(id) FROM candidate_test_scores")).scalar()
        last = sync_candidate_test_scores_id_sequence(db)
        db.commit()
        print(
            f"candidate_test_scores: max_id={max_id} "
            f"seq_before={tuple(before) if before else None} seq_after={last}"
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
