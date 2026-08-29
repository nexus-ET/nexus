#!/usr/bin/env python3
"""Start uvicorn after loading .env the same way app scripts do.

systemd EnvironmentFile= does not parse dotenv the same as python-dotenv
(quotes, UTF-8 BOM, CRLF). Neon console URLs also include channel_binding=require
and postgresql:// — normalize before the app imports SQLAlchemy.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env", override=True)

from app.config import normalize_database_url

raw = (os.environ.get("DATABASE_URL") or "").strip()
if raw:
    os.environ["DATABASE_URL"] = normalize_database_url(raw)

uvicorn = BACKEND_ROOT / ".venv" / "bin" / "uvicorn"
if not uvicorn.is_file():
    sys.stderr.write(f"ERROR: uvicorn not found at {uvicorn}\n")
    sys.exit(1)

host = (os.environ.get("NEXUS_BIND_HOST") or "127.0.0.1").strip() or "127.0.0.1"
port = (os.environ.get("NEXUS_PORT") or "8002").strip() or "8002"

os.execv(
    str(uvicorn),
    [
        str(uvicorn),
        "app.main:app",
        "--host",
        host,
        "--port",
        port,
    ],
)
