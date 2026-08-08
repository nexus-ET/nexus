#!/usr/bin/env python3
"""CLI for FlowX journey test seed / reset (default lead 27).

  python scripts/seed_flowx_lead27_journey_test.py
  python scripts/seed_flowx_lead27_journey_test.py --reset
  python scripts/seed_flowx_lead27_journey_test.py --lead-id 27 --reset
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
from app.services.flowx_journey_test_seed import (
    DEFAULT_LEAD_ID,
    reset_journey_test_data,
    seed_journey_test_data,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lead-id", type=int, default=DEFAULT_LEAD_ID)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete lead enrollments + FXTEST{lead} Academia institutions/geo",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.reset:
            result = reset_journey_test_data(db, args.lead_id)
        else:
            result = seed_journey_test_data(db, args.lead_id)
        print(json.dumps(result, indent=2, default=str))
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
