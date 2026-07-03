#!/usr/bin/env python3
"""Backfill Lead: New status for leads missing a baseline journey row.

Run on staging after migrations when leads have no Lead: New row in status_history.
Opening View Journey also backfills one lead at a time; use this script for bulk repair.

Usage:
  python scripts/backfill_lead_new_status.py --dry-run
  python scripts/backfill_lead_new_status.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.db.register_models import register_all_models

register_all_models()

from app.db.database import SessionLocal
from app.models.lead import Lead
from app.services.student_status_service import (
    _lead_new_history_exists,
    ensure_lead_new_journey_baseline,
)


def backfill(*, dry_run: bool) -> int:
    db = SessionLocal()
    try:
        leads = db.query(Lead).order_by(Lead.id.asc()).all()
        missing = [lead for lead in leads if not _lead_new_history_exists(db, lead.id)]
        if not missing:
            print("All leads already have a Lead: New journey row.")
            return 0

        print(f"Found {len(missing)} lead(s) without Lead: New in status_history.")
        updated = 0

        for lead in missing:
            print(
                f"  lead id={lead.id} name={lead.full_name!r} "
                f"phone={lead.phone_number!r} status_definition_id={lead.status_definition_id}"
            )
            if dry_run:
                continue
            if ensure_lead_new_journey_baseline(db, lead, source="backfill script"):
                updated += 1

        if dry_run:
            print("Dry run only — no changes made.")
            return 0

        print(f"Backfilled Lead: New for {updated} lead(s).")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Lead: New for legacy leads.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Refusing to modify the database without --yes.", file=sys.stderr)
        print("Preview: python scripts/backfill_lead_new_status.py --dry-run", file=sys.stderr)
        return 2

    return backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
