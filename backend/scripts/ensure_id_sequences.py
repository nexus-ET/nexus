#!/usr/bin/env python3
"""Advance serial id sequences past MAX(id) for tables that often desync after imports."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.db.database import SessionLocal

# Keep in sync with scripts/staging_post_deploy_smoke.py SEQUENCE_TABLES.
SEQUENCE_TABLES = (
    "candidate_test_scores",
    "navigation_pages",
    "role_page_permissions",
    "notification_logs",
    "counselling_bookings",
)


def sync_table(db, table: str) -> str:
    exists = db.execute(
        text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": table},
    ).scalar()
    if not exists:
        return f"{table}: missing"
    seq = db.execute(
        text("SELECT pg_get_serial_sequence(:table, 'id')"),
        {"table": table},
    ).scalar()
    if not seq:
        return f"{table}: no sequence"
    max_id = db.execute(text(f"SELECT MAX(id) FROM {table}")).scalar()
    last = db.execute(
        text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table}), 1),
                (SELECT EXISTS (SELECT 1 FROM {table}))
            )
            """
        )
    ).scalar()
    return f"{table}: max_id={max_id} seq={last}"


def main() -> int:
    db = SessionLocal()
    try:
        for table in SEQUENCE_TABLES:
            print(sync_table(db, table))
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
