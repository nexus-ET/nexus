#!/usr/bin/env python
"""Run the Nexus security audit fortress validation suite."""

from __future__ import annotations

import sys

from app.db.database import Base, SessionLocal, engine, sync_schema_columns
from app.models.security_audit_run import SecurityAuditRun  # noqa: F401
from app.services.audit_runner import get_security_audit_run, run_security_audit_suite


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    sync_schema_columns()


def main() -> int:
    _ensure_schema()
    db = SessionLocal()
    try:
        run_record, alert_sent = run_security_audit_suite(db, triggered_by="manual")
        serialized = get_security_audit_run(db, run_record.id)
        if serialized is None:
            print("Security audit completed but the run record could not be loaded.")
            return 1

        print(f"Security Audit Run #{serialized.id}")
        print(f"Status: {serialized.status.upper()}")
        print(f"Passed: {serialized.passed_checks}/{serialized.total_checks}")
        if alert_sent:
            print("Urgent alert dispatched to super admins.")

        print("\nChecks:")
        for check in serialized.checks:
            flag = "PASS" if check.passed else "FAIL"
            print(f"  [{flag}] {check.category}/{check.name}: {check.message}")

        return 0 if serialized.status == "pass" else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
