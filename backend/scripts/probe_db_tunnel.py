#!/usr/bin/env python3
"""Probe Postgres reachability for the Hostinger SSH DB tunnel.

Exit codes:
  0 — TCP reachable (optional) and SELECT 1 succeeded
  1 — connect / query failed
  2 — bad usage / missing DATABASE_URL

Used by start-dev.ps1 / start-hostinger-db-tunnel.ps1 watchdogs and run_dev.py.
Does not print passwords.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, unquote


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def _database_url() -> str:
    backend_root = Path(__file__).resolve().parents[1]
    _load_dotenv(backend_root / ".env")
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("[db-tunnel] DATABASE_URL missing", file=sys.stderr)
        raise SystemExit(2)
    # psycopg wants postgresql:// not postgresql+psycopg://
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url[len("postgresql+psycopg://") :]
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://") :]
    return url


def _host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    return host, int(port)


def _tcp_ok(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _select_one(url: str, connect_timeout: float) -> None:
    try:
        import psycopg
    except ImportError:
        # Fallback: SQLAlchemy engine already on the app path
        from sqlalchemy import create_engine, text

        sa_url = url
        if sa_url.startswith("postgresql://"):
            sa_url = "postgresql+psycopg://" + sa_url[len("postgresql://") :]
        engine = create_engine(
            sa_url,
            pool_pre_ping=False,
            connect_args={"connect_timeout": max(1, int(connect_timeout))},
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return

    # Strip SQLAlchemy-only bits; pass connect_timeout as libpq kwarg
    with psycopg.connect(url, connect_timeout=max(1, int(connect_timeout))) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local SSH DB tunnel / DATABASE_URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="TCP + connect timeout seconds (default 5)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Attempts before failing (default 1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between retries (default 1)",
    )
    parser.add_argument(
        "--tcp-only",
        action="store_true",
        help="Only check TCP accept on DATABASE_URL host:port",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success log line",
    )
    args = parser.parse_args()

    url = _database_url()
    host, port = _host_port(url)
    # Never log userinfo
    target = f"{host}:{port}"

    attempts = max(1, args.retries)
    last_err = ""
    for i in range(1, attempts + 1):
        if not _tcp_ok(host, port, args.timeout):
            last_err = f"TCP {target} not accepting"
        elif args.tcp_only:
            if not args.quiet:
                print(f"[db-tunnel] healthy tcp {target}")
            return 0
        else:
            try:
                _select_one(url, args.timeout)
                if not args.quiet:
                    print(f"[db-tunnel] healthy SELECT 1 via {target}")
                return 0
            except Exception as exc:  # noqa: BLE001 — probe must never raise
                last_err = f"{type(exc).__name__}: {exc}"
                # Avoid leaking password if it somehow appears in the message
                pw = urlparse(url).password
                if pw:
                    last_err = last_err.replace(pw, "***").replace(unquote(pw), "***")

        if i < attempts:
            time.sleep(max(0.1, args.delay))

    print(f"[db-tunnel] unhealthy ({target}): {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
