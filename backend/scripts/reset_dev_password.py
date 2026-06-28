"""Reset a NEXUS user password in the local/dev database."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from app.core.security import get_password_hash


def _pg_conninfo(url: str) -> str:
    raw = (url or "").strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw.replace("postgresql://", "postgres://")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a user password in the dev database")
    parser.add_argument("email", help="User email, e.g. ishq@edutrust.in")
    parser.add_argument("password", help="New password")
    args = parser.parse_args()

    database_url = _pg_conninfo(os.getenv("DATABASE_URL", ""))
    if not database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 1

    hashed = get_password_hash(args.password)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET hashed_password = %s WHERE email = %s RETURNING id",
                (hashed, args.email.strip()),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        print(f"No user found for {args.email}", file=sys.stderr)
        return 1

    print(f"Password updated for {args.email.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
