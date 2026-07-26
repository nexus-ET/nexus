#!/usr/bin/env python3
"""Seed navigation_pages + missing role_page_permissions (fixes empty top menu)."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from sqlalchemy import text

from app.db.database import SessionLocal
from app.db.register_models import register_all_models
from app.services.navigation_rbac import ensure_navigation_rbac

register_all_models()


def main() -> int:
    db = SessionLocal()
    try:
        ensure_navigation_rbac(db)
        pages = db.execute(text("SELECT COUNT(*) FROM navigation_pages")).scalar()
        perms = db.execute(text("SELECT COUNT(*) FROM role_page_permissions")).scalar()
        print(f"navigation_pages={pages}, role_page_permissions={perms}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
