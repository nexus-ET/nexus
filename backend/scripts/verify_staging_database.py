#!/usr/bin/env python3
"""
Verify staging DATABASE_URL (Nexus-Dev-1) and optionally run migrations.

Does not read or write any .env except the active process environment /
backend/.env already loaded by Settings — run this ON THE VPS after you
manually edited /var/www/nexus/backend/.env.

Usage (VPS):
  cd /var/www/nexus/backend
  source .venv/bin/activate
  python scripts/verify_staging_database.py
  python scripts/verify_staging_database.py --migrate

Usage (PC against staging URL without touching local .env):
  set DATABASE_URL=postgresql+psycopg://...Nexus-Dev-1...
  python scripts/verify_staging_database.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_url() -> str:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    url = (settings.DATABASE_URL or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is empty")
    return url


def _summarize(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    host = parsed.hostname or "?"
    db = (parsed.path or "/").lstrip("/") or "?"
    return f"{parsed.scheme}://***@{host}/{db}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify staging Neon DATABASE_URL")
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run bootstrap_alembic.py (upgrade head) after connectivity check",
    )
    args = parser.parse_args()

    url = _load_url()
    print(f"DATABASE_URL: {_summarize(url)}")

    if "sqlite" in url.lower():
        print("WARNING: SQLITE URL — staging should use Neon Postgres (Nexus-Dev-1).")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        print(f"Connected OK: {str(version)[:80]}...")
        tables = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).scalar()
        print(f"Public tables: {tables}")

    heads = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    print("Alembic heads:")
    print((heads.stdout or heads.stderr or "").strip() or "(none)")

    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    print("Alembic current:")
    print((current.stdout or current.stderr or "").strip() or "(empty — fresh DB)")

    if args.migrate:
        print("\nRunning bootstrap_alembic.py ...")
        result = subprocess.run(
            [sys.executable, "scripts/bootstrap_alembic.py"],
            cwd=BACKEND_ROOT,
            check=False,
        )
        return result.returncode

    print("\nConnectivity check passed. Re-run with --migrate to apply schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
