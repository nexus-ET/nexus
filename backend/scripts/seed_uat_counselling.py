#!/usr/bin/env python3
"""Seed / repair UAT counselling fixture (default lead 27 + ishq@edutrust.in).

Ensures lead 27 has a SCHEDULED counselling booking assigned to the UAT admin
so Playwright specs can open DISCOVERY / PROFILE tabs on /students/counselling/:id.

Usage:
  python scripts/seed_uat_counselling.py
  python scripts/seed_uat_counselling.py --lead-id 27 --admin-email ishq@edutrust.in
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.db.register_models import register_all_models

register_all_models()

from app.db.database import SessionLocal
from app.services.uat_counselling_seed import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_LEAD_ID,
    ensure_uat_counselling_booking,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lead-id", type=int, default=DEFAULT_LEAD_ID)
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = ensure_uat_counselling_booking(
            db,
            lead_id=args.lead_id,
            admin_email=args.admin_email,
        )
        print(json.dumps(result, indent=2, default=str))
        print(
            f"\nSet UAT_BOOKING_ID={result['booking_id']} in uat/.env if it differs.",
            file=sys.stderr,
        )
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        db.rollback()
        return 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
