#!/usr/bin/env python3
"""Stamp staging alembic_version to head when schema is already present.

Use only when Hostinger staging schema was synced from develop (tables/indexes
already exist) but alembic_version lagged and upgrade keeps hitting Duplicate*.

  cd /var/www/nexus/backend && source .venv/bin/activate
  python scripts/heal_staging_alembic_stamp.py          # dry-run
  python scripts/heal_staging_alembic_stamp.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, inspect, text

from app.config import settings

HEAD = "jj0k1lbizlogo"

REQUIRED_TABLES = (
    "full_time_study_years",
    "intel_glossary",
    "intel_ai_chat_logs",
    "flowx_country_workflows",
    "flowx_enrollments",
    "flowx_pathway_registry",
)

REQUIRED_COLUMNS = (
    ("counselling_bookings", "intake_assessment"),
    ("businesses", "logo_path"),
    ("full_time_study_years", "level_id"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write alembic_version stamp")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        inspector = inspect(conn)
        missing_tables = [t for t in REQUIRED_TABLES if not inspector.has_table(t)]
        missing_cols: list[str] = []
        for table, col in REQUIRED_COLUMNS:
            if not inspector.has_table(table):
                missing_cols.append(f"{table}.{col} (table missing)")
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if col not in cols:
                missing_cols.append(f"{table}.{col}")

        current = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version rows:", [r[0] for r in current] or "(empty)")
        print("target head:", HEAD)
        if missing_tables:
            print("MISSING tables:", ", ".join(missing_tables))
        if missing_cols:
            print("MISSING columns:", ", ".join(missing_cols))
        if missing_tables or missing_cols:
            print("Refusing to stamp — run `alembic upgrade head` instead.")
            return 1

        print("Schema looks complete for head.")
        if not args.apply:
            print("Dry-run only. Re-run with --apply to stamp.")
            return 0

        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
            {"v": HEAD},
        )
        conn.commit()
        print(f"Stamped alembic_version -> {HEAD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
