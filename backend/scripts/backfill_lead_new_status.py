#!/usr/bin/env python3
"""Backfill Lead: New status for leads created before the pipeline status system.

Run on staging after migrations when existing leads have NULL status_definition_id
and an empty status_history — Journey will otherwise show no entries.

Usage:
  python scripts/backfill_lead_new_status.py --dry-run
  python scripts/backfill_lead_new_status.py --yes
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.db.register_models import register_all_models

register_all_models()

from app.db.database import SessionLocal
from app.models.lead import Lead
from app.models.status_history import ChangedByType, StatusHistory
from app.services.status_definition_service import STATUS_LEAD_NEW

SOURCE_COMMENT = "Backfill: Lead: New for pre-migration lead."


def backfill(*, dry_run: bool) -> int:
    db = SessionLocal()
    try:
        leads = (
            db.query(Lead)
            .filter(Lead.status_definition_id.is_(None))
            .order_by(Lead.id.asc())
            .all()
        )
        if not leads:
            print("No leads with NULL status_definition_id — nothing to backfill.")
            return 0

        print(f"Found {len(leads)} lead(s) without pipeline status.")
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for lead in leads:
            history_count = (
                db.query(StatusHistory.id)
                .filter(StatusHistory.student_id == lead.id)
                .count()
            )
            print(
                f"  lead id={lead.id} name={lead.full_name!r} "
                f"phone={lead.phone_number!r} history_rows={history_count}"
            )
            if dry_run:
                continue

            if history_count == 0:
                db.add(
                    StatusHistory(
                        student_id=lead.id,
                        status_id=STATUS_LEAD_NEW,
                        changed_by_type=ChangedByType.SYSTEM,
                        comments=SOURCE_COMMENT,
                        created_at=now,
                    )
                )
            lead.status_definition_id = STATUS_LEAD_NEW
            lead.status_entered_at = now

        if dry_run:
            print("Dry run only — no changes made.")
            return 0

        db.commit()
        print(f"Backfilled Lead: New for {len(leads)} lead(s).")
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
