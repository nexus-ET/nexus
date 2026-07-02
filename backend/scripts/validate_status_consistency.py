#!/usr/bin/env python3
"""Scan pipeline status data for integrity issues."""

from __future__ import annotations

import argparse
import sys

from app.db.database import SessionLocal
from app.services.status_consistency_service import validate_status_data_consistency


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate student pipeline status consistency.")
    parser.add_argument("--student-id", type=int, default=None, help="Limit scan to one student.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        issues = validate_status_data_consistency(db, student_id=args.student_id)
    finally:
        db.close()

    if not issues:
        print("OK: no status consistency issues found.")
        return 0

    print(f"Found {len(issues)} issue(s):")
    for issue in issues:
        prefix = f"student={issue.student_id}" if issue.student_id else "global"
        print(f"- [{issue.code}] {prefix}: {issue.message} {issue.details}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
