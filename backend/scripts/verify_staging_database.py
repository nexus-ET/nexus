#!/usr/bin/env python3
"""
Verify DATABASE_URL connectivity, table count, and Alembic head; optionally migrate.

Works for staging (Hostinger nexus_edutrust), development (Hostinger nexus_dev),
or legacy Neon — use --env to get environment-specific warnings.

Does not read or write any .env except the active process environment /
backend/.env already loaded by Settings.

Usage (staging VPS):
  cd /var/www/nexus/backend
  source .venv/bin/activate
  python scripts/verify_staging_database.py --env staging
  python scripts/verify_staging_database.py --env staging --migrate

Usage (local develop — after switching to Hostinger nexus_dev):
  cd E:\\NEXUS\\backend
  python scripts/verify_staging_database.py --env dev
  python scripts/verify_staging_database.py --env dev --migrate

Usage (PC against a URL without editing .env):
  set DATABASE_URL=postgresql+psycopg://nexus_dev_admin:...@YOUR_DB_HOST:5432/nexus_dev
  python scripts/verify_staging_database.py --env dev
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _load_url() -> str:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.config import settings

    url = (settings.DATABASE_URL or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is empty")
    return url


def _parse_db_url(url: str):
    return urlparse(url.replace("postgresql+psycopg", "postgresql", 1))


def _format_host_port(parsed) -> str:
    host = parsed.hostname or "?"
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def _validate_db_url(url: str) -> None:
    parsed = _parse_db_url(url)
    host = parsed.hostname or ""

    if not host:
        raise SystemExit(
            "ERROR: DATABASE_URL has no host.\n"
            "  Expected: postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"
        )

    if "@" in host:
        raise SystemExit(
            "ERROR: DATABASE_URL host looks malformed (contains '@').\n"
            "  Likely cause: password contains '@' that is not URL-encoded.\n"
            "  Fix: encode each '@' in the password as %40, e.g.\n"
            "    Nexus@ET@2026@Dev  ->  Nexus%40ET%402026%40Dev\n"
            f"  Parsed host: {host!r}\n"
            "  Expected: postgresql+psycopg://nexus_dev_et_admin:Nexus%40...@187.127.186.63:5432/nexus_edutrust_dev"
        )


def _summarize(url: str) -> str:
    parsed = _parse_db_url(url)
    host_port = _format_host_port(parsed)
    db = (parsed.path or "/").lstrip("/") or "?"
    return f"{parsed.scheme}://***@{host_port}/{db}"


def _print_connect_timeout_help(host_port: str) -> None:
    print(
        f"\nERROR: Connection to {host_port} timed out after 10 seconds.\n"
        "  Hostinger Postgres is usually NOT reachable from your PC on port 5432.\n"
        "\n"
        "  Option A — Run on the VPS (recommended):\n"
        "    sudo bash /var/www/nexus/backend/deploy/migrate_on_vps.sh --env dev\n"
        "    (On the VPS, DATABASE_URL should use 127.0.0.1:5432.)\n"
        "\n"
        "  Option B — SSH tunnel from your PC:\n"
        "    ssh -N -L 5433:127.0.0.1:5432 root@187.127.186.63\n"
        "    Then point DATABASE_URL at 127.0.0.1:5433 in backend/.env\n"
        "\n"
        "  See backend/deploy/setup_dev_db.md section 7 for details."
    )


def _handle_connect_error(exc: BaseException, host_port: str) -> None:
    msg = f"{exc}".lower()
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        msg = f"{msg} {cause}".lower()

    if any(token in msg for token in ("timeout", "timed out", "time out")):
        _print_connect_timeout_help(host_port)
        raise SystemExit(1) from exc

    print(f"\nERROR: Could not connect to {host_port}: {exc}")
    raise SystemExit(1) from exc


def _detect_env(url: str) -> str:
    lower = url.lower()
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    db = (parsed.path or "/").lstrip("/").lower()
    host = (parsed.hostname or "").lower()
    if db == "nexus_edutrust" or "nexus_et_admin" in lower:
        return "staging"
    if db == "nexus_dev" or "nexus_dev_admin" in lower:
        return "dev"
    if "still-paper" in host or "still-paper" in lower:
        return "legacy_neon_dev"
    if "neon.tech" in host or db == "neondb":
        return "legacy_neon"
    return "unknown"


def _print_env_warnings(url: str, env: str) -> None:
    if "sqlite" in url.lower():
        if env == "staging":
            print("WARNING: SQLITE URL — staging should use Hostinger Postgres (nexus_edutrust).")
        elif env == "dev":
            print("WARNING: SQLITE URL — develop should use Hostinger Postgres (nexus_dev).")
        else:
            print("WARNING: SQLITE URL — expected Postgres for staging/dev.")
        return

    if env == "legacy_neon_dev":
        print(
            "WARNING: legacy Neon still-paper develop URL — "
            "switch DATABASE_URL to Hostinger nexus_dev (see deploy/setup_dev_db.md)."
        )
    elif env == "legacy_neon":
        print("WARNING: Neon URL detected — confirm this is intentional (legacy or copy source).")
    elif env == "staging" and "neon.tech" in (urlparse(url.replace("postgresql+psycopg", "postgresql", 1)).hostname or ""):
        print("WARNING: staging should use Hostinger nexus_edutrust, not Neon.")
    elif env == "dev" and "neon.tech" in (urlparse(url.replace("postgresql+psycopg", "postgresql", 1)).hostname or ""):
        print("WARNING: develop should use Hostinger nexus_dev, not Neon.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Postgres DATABASE_URL and Alembic head")
    parser.add_argument(
        "--env",
        choices=("dev", "staging", "auto"),
        default="auto",
        help="Expected environment for warnings (default: auto-detect from URL)",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run bootstrap_alembic.py (upgrade head) after connectivity check",
    )
    args = parser.parse_args()

    url = _load_url()
    _validate_db_url(url)
    parsed = _parse_db_url(url)
    host_port = _format_host_port(parsed)

    print(f"DATABASE_URL: {_summarize(url)}")
    print(f"Target host:port: {host_port}")

    env = _detect_env(url) if args.env == "auto" else args.env
    if env != "auto":
        print(f"Environment: {env}")
    _print_env_warnings(url, env)

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    try:
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
    except OperationalError as exc:
        _handle_connect_error(exc, host_port)

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
