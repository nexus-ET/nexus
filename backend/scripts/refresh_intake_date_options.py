#!/usr/bin/env python3
"""Drop cached WhatsApp date-picker options so the next prompt regenerates them.

Leads parked on PICK_DATE keep the day list they were last shown in
``intake_context.date_options``. After a change to the booking window (for
example enabling same-day consultations) that cached list is stale. Clearing it
makes the next PICK_DATE prompt rebuild from live availability; nothing else in
the conversation state is touched.

Usage (from backend root):
  .venv\\Scripts\\python.exe scripts/refresh_intake_date_options.py --dry-run
  .venv\\Scripts\\python.exe scripts/refresh_intake_date_options.py
  .venv\\Scripts\\python.exe scripts/refresh_intake_date_options.py --lead-id 27
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal  # noqa: E402
from app.db.register_models import register_all_models  # noqa: E402

register_all_models()

from app.models.lead import Lead  # noqa: E402
from app.services.admissions_intake_flow import (  # noqa: E402
    INTAKE_STEP_PICK_DATE,
    _available_dates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lead-id", type=int, default=None, help="Limit to a single lead.")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        fresh_dates = [slot_day.isoformat() for slot_day in _available_dates(db)]
        print(f"Live bookable dates: {fresh_dates}")

        query = db.query(Lead).filter(Lead.intake_step == INTAKE_STEP_PICK_DATE)
        if args.lead_id is not None:
            query = query.filter(Lead.id == args.lead_id)

        cleared = 0
        for lead in query.order_by(Lead.id.asc()).all():
            try:
                context = json.loads(lead.intake_context or "{}")
            except json.JSONDecodeError:
                context = {}
            stale = context.get("date_options")
            if not stale:
                continue
            if list(stale) == fresh_dates:
                print(f"lead#{lead.id}: already current")
                continue
            print(f"lead#{lead.id}: stale {stale} -> will regenerate on next prompt")
            if args.dry_run:
                continue
            context.pop("date_options", None)
            lead.intake_context = json.dumps(context) if context else None
            cleared += 1

        if args.dry_run:
            print("Dry run - no changes written.")
        else:
            db.commit()
            print(f"Cleared cached date options for {cleared} lead(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
