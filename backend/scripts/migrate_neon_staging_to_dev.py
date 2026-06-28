"""
Copy schema + data from Nexus-Staging Neon to Nexus-dev Neon.

Requires Docker (postgres:16 image for pg_dump / pg_restore).

Setup:
  1. Copy .env.staging-source.example -> .env.staging-source
  2. Paste Nexus-Staging pooled connection string as STAGING_DATABASE_URL
  3. Ensure backend/.env DATABASE_URL points at Nexus-dev (target)

Run:
  cd backend
  python scripts/migrate_neon_staging_to_dev.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env.staging-source")


def _to_pg_url(url: str) -> str:
    raw = (url or "").strip().strip('"').strip("'")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    if not raw.startswith("postgresql://"):
        raise ValueError(f"Unsupported database URL format: {raw[:40]}...")
    return raw


def _mask_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "?"
    db = (parsed.path or "/").lstrip("/")
    return f"{parsed.scheme}://***@{host}/{db}"


def _docker_pg_dump(source: str, dump_path: Path, *, schema_only: bool, data_only: bool) -> None:
    flags = ["-Fc", "--no-owner", "--no-acl"]
    if schema_only:
        flags.append("--schema-only")
    elif data_only:
        flags.append("--data-only")
    cmd = (
        f'pg_dump {" ".join(flags)} -f /backup/nexus_staging.dump '
        f'"{source.replace(chr(34), chr(92)+chr(34))}"'
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{dump_path.parent}:/backup",
            "postgres:16",
            "sh",
            "-c",
            cmd,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"pg_dump failed ({result.returncode})")


def _docker_pg_restore(target: str, dump_path: Path, *, schema_only: bool, data_only: bool) -> None:
    flags = ["--no-owner", "--no-acl", "--verbose"]
    if schema_only:
        flags.append("--schema-only")
    elif data_only:
        flags.append("--data-only")
    else:
        flags.extend(["--clean", "--if-exists"])
    cmd = (
        f'pg_restore {" ".join(flags)} -d '
        f'"{target.replace(chr(34), chr(92)+chr(34))}" /backup/nexus_staging.dump'
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{dump_path.parent}:/backup",
            "postgres:16",
            "sh",
            "-c",
            cmd,
        ],
        capture_output=True,
        text=True,
    )
    # pg_restore may exit 1 for benign warnings (e.g. missing extensions)
    if result.returncode not in (0, 1):
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"pg_restore failed ({result.returncode})")
    if result.stderr:
        print(result.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Nexus-Staging Neon DB to Nexus-dev")
    parser.add_argument("--source", help="Override STAGING_DATABASE_URL")
    parser.add_argument("--target", help="Override DATABASE_URL (Nexus-dev)")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args()

    source = _to_pg_url(args.source or os.getenv("STAGING_DATABASE_URL", ""))
    target = _to_pg_url(args.target or os.getenv("DATABASE_URL", ""))

    if not source or "USER:PASSWORD" in source or "PASSWORD@" in source:
        print(
            "Missing STAGING_DATABASE_URL.\n"
            "Copy .env.staging-source.example to .env.staging-source and paste the "
            "Nexus-Staging pooled connection string from Neon Console.",
            file=sys.stderr,
        )
        return 1

    print("Source:", _mask_url(source))
    print("Target:", _mask_url(target))

    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / "nexus_staging.dump"
        print("Dumping staging database...")
        _docker_pg_dump(source, dump_path, schema_only=args.schema_only, data_only=args.data_only)
        print(f"Dump size: {dump_path.stat().st_size / 1024:.1f} KB")
        print("Restoring into Nexus-dev...")
        _docker_pg_restore(target, dump_path, schema_only=args.schema_only, data_only=args.data_only)

    print("Migration complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
