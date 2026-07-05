#!/usr/bin/env python3
"""Verify status_definitions v3 and status_transitions after Alembic s5p8q1r54s0m."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
    )
    alembic_out = (result.stdout or "") + (result.stderr or "")
    if "s5p8q1r54s0m" not in alembic_out:
        print("FAIL: Alembic not at s5p8q1r54s0m")
        print(alembic_out)
        return 1

    engine = create_engine(settings.DATABASE_URL)
    insp = inspect(engine)
    if not insp.has_table("status_definitions") or not insp.has_table("status_transitions"):
        print("FAIL: required tables missing")
        return 1

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM status_definitions")).scalar()
        marketing = conn.execute(
            text("SELECT stage_name FROM status_definitions WHERE id = 10")
        ).scalar()
        counselling = conn.execute(
            text("SELECT stage_name FROM status_definitions WHERE id = 12")
        ).scalar()
        document = conn.execute(
            text("SELECT stage_name FROM status_definitions WHERE id = 18")
        ).scalar()
        relaunch = conn.execute(
            text("SELECT stage_name FROM status_definitions WHERE id = 45")
        ).scalar()
        transitions = conn.execute(
            text(
                "SELECT transition_type, COUNT(*) FROM status_transitions "
                "GROUP BY 1 ORDER BY 1"
            )
        ).all()
        express = conn.execute(
            text(
                "SELECT from_status_id, to_status_id FROM status_transitions "
                "WHERE transition_type = 'express' ORDER BY 1, 2"
            )
        ).all()

    print(f"Alembic head: s5p8q1r54s0m")
    print(f"status_definitions: {count} rows")
    print(f"  id 10: {marketing}")
    print(f"  id 12: {counselling}")
    print(f"  id 18: {document}")
    print(f"  id 45: {relaunch}")
    print(f"status_transitions: {transitions}")
    print(f"express paths: {express}")

    errors: list[str] = []
    if count != 45:
        errors.append(f"expected 45 status_definitions rows, got {count}")
    if marketing != "Lead: Marketing Enabled":
        errors.append(f"unexpected id 10: {marketing!r}")
    if counselling != "Counselling: Scheduled":
        errors.append(f"unexpected id 12: {counselling!r}")
    if document != "Document: In Preparation":
        errors.append(f"unexpected id 18: {document!r}")
    if relaunch != "Prospect: Relaunch":
        errors.append(f"unexpected id 45: {relaunch!r}")
    expected_express = {(1, 12), (3, 18), (13, 28)}
    if set(express) != expected_express:
        errors.append(f"express paths mismatch: {express} vs {expected_express}")

    if errors:
        for item in errors:
            print(f"FAIL: {item}")
        return 1

    print("OK — status_definitions v3 verified on development database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
