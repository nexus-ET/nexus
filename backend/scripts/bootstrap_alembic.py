#!/usr/bin/env python3
"""
Bootstrap Alembic on databases that were created before migration tracking.

NEXUS staging/production was originally provisioned with SQLAlchemy create_all()
and sync_schema_columns(), so alembic_version may be empty while tables already
exist. Running `alembic upgrade head` from scratch then fails with duplicate
column/table errors.

This script:
  1. If alembic_version is empty and core tables exist -> stamp baseline revision
  2. Run `alembic upgrade head` for any migrations after the baseline (e1..j6)

Used automatically from deploy.sh; can also be run manually on the VPS.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "d9a4b2c81f0e"  # last revision before countries/audit migrations
HEAD_REVISION = "j6f9g4h58i0d"


def _load_database_url() -> str:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    return settings.DATABASE_URL


def _current_alembic_revision() -> str | None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("INFO"):
            continue
        token = line.split()[0]
        if len(token) >= 8 and token.isalnum():
            return token
    return None


def _database_has_legacy_schema(engine) -> bool:
    inspector = inspect(engine)
    required = {"users", "leads", "clients"}
    present = {t for t in inspector.get_table_names()}
    return required.issubset(present)


def _run_alembic(*args: str) -> None:
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, cwd=BACKEND_ROOT, check=True)


def main() -> int:
    database_url = _load_database_url()
    engine = create_engine(database_url)

    current = _current_alembic_revision()
    if current:
        print(f"Alembic already at revision: {current}")
        if current == HEAD_REVISION:
            print("Already at head — nothing to do.")
            return 0
        print("Running pending upgrades...")
        _run_alembic("upgrade", "head")
        return 0

    print("No alembic_version recorded.")
    if not _database_has_legacy_schema(engine):
        print("Fresh database detected — running full alembic upgrade head.")
        _run_alembic("upgrade", "head")
        return 0

    print(
        "Existing legacy schema detected (create_all / sync_schema). "
        f"Stamping baseline {BASELINE_REVISION}, then upgrading to head."
    )
    _run_alembic("stamp", BASELINE_REVISION)
    _run_alembic("upgrade", "head")

    final = _current_alembic_revision()
    print(f"Done. Alembic revision is now: {final or 'unknown'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: alembic command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
