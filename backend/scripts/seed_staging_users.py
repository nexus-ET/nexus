#!/usr/bin/env python3
"""
Ensure staging has login-ready users after a fresh Neon DB (e.g. Nexus-Dev-1).

Usage (VPS):
  cd /var/www/nexus/backend && source .venv/bin/activate
  python scripts/seed_staging_users.py
  python scripts/seed_staging_users.py --email you@edutrust.in --password 'YourSecurePass'
  python scripts/seed_staging_users.py --copy-from "$STAGING_USERS_SOURCE_URL"

Env (optional):
  STAGING_ADMIN_EMAIL      default admin@edutrust.in
  STAGING_ADMIN_PASSWORD   required unless --password / --copy-from
  STAGING_USERS_SOURCE_URL optional Neon URL to copy users + admin_roles from
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from app.config import normalize_database_url, settings
from app.core.security import get_password_hash
from app.models.admin_role import AdminRole
from app.models.user import User
from app.services.admin_roles import DEFAULT_ADMIN_ROLES
from app.services.business_profile_service import ensure_default_business


def _summarize_url(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
    host = parsed.hostname or "?"
    db = (parsed.path or "/").lstrip("/") or "?"
    return f"{host}/{db}"


def _ensure_admin_roles(db) -> AdminRole:
    for item in DEFAULT_ADMIN_ROLES:
        existing = db.query(AdminRole).filter(AdminRole.name == item["name"]).first()
        if existing:
            continue
        db.add(
            AdminRole(
                name=str(item["name"]),
                description=str(item.get("description") or ""),
                is_superuser=bool(item.get("is_superuser", False)),
                is_active=True,
                sort_order=int(item.get("sort_order") or 0),
            )
        )
    db.commit()
    super_role = (
        db.query(AdminRole)
        .filter(AdminRole.is_superuser.is_(True), AdminRole.is_active.is_(True))
        .order_by(AdminRole.sort_order.asc())
        .first()
    )
    if not super_role:
        raise RuntimeError("Failed to create Super Admin role")
    return super_role


def _upsert_admin_user(
    db,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    super_role: AdminRole,
) -> User:
    email_norm = email.strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    hashed = get_password_hash(password)
    if user:
        user.hashed_password = hashed
        user.is_active = True
        user.is_superuser = True
        user.admin_role_id = super_role.id
        user.first_name = user.first_name or first_name
        user.last_name = user.last_name or last_name
        user.business_id = user.business_id or 1
        action = "updated"
    else:
        user = User(
            email=email_norm,
            hashed_password=hashed,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            is_superuser=True,
            admin_role_id=super_role.id,
            business_id=1,
        )
        db.add(user)
        action = "created"
    db.commit()
    db.refresh(user)
    print(f"Staging admin {action}: {user.email} (id={user.id}, superuser=true)")
    return user


def _copy_users_from(source_url: str, target_url: str) -> int:
    """Copy admin_roles + users (including hashed passwords) from source → target."""
    source = create_engine(normalize_database_url(source_url), pool_pre_ping=True)
    target = create_engine(normalize_database_url(target_url), pool_pre_ping=True)
    print(f"Copying users from {_summarize_url(source_url)} → {_summarize_url(target_url)}")

    with source.connect() as src, target.begin() as dst:
        roles = src.execute(
            text(
                "SELECT id, name, description, is_superuser, is_active, sort_order "
                "FROM admin_roles ORDER BY id"
            )
        ).mappings().all()
        for row in roles:
            dst.execute(
                text(
                    """
                    INSERT INTO admin_roles (id, name, description, is_superuser, is_active, sort_order)
                    VALUES (:id, :name, :description, :is_superuser, :is_active, :sort_order)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        is_superuser = EXCLUDED.is_superuser,
                        is_active = EXCLUDED.is_active,
                        sort_order = EXCLUDED.sort_order
                    """
                ),
                dict(row),
            )
        if roles:
            dst.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('admin_roles', 'id'), "
                    "(SELECT COALESCE(MAX(id), 1) FROM admin_roles))"
                )
            )

        # Ensure default business exists for FK
        dst.execute(
            text(
                """
                INSERT INTO businesses (id, name)
                VALUES (1, 'Default Business')
                ON CONFLICT (id) DO NOTHING
                """
            )
        )

        users = src.execute(
            text(
                """
                SELECT id, email, hashed_password, first_name, last_name, phone_number,
                       is_active, is_superuser, admin_role_id, business_id,
                       creation_reason, creation_date, deactivation_reason, deactivation_date,
                       activation_reason, activation_date
                FROM users
                ORDER BY id
                """
            )
        ).mappings().all()

        copied = 0
        for row in users:
            payload = dict(row)
            # Avoid FK failures if optional reason IDs don't exist on fresh DB
            for key in (
                "creation_reason",
                "deactivation_reason",
                "activation_reason",
            ):
                payload[key] = None
            payload["business_id"] = payload.get("business_id") or 1
            dst.execute(
                text(
                    """
                    INSERT INTO users (
                        id, email, hashed_password, first_name, last_name, phone_number,
                        is_active, is_superuser, admin_role_id, business_id,
                        creation_reason, creation_date, deactivation_reason, deactivation_date,
                        activation_reason, activation_date
                    ) VALUES (
                        :id, :email, :hashed_password, :first_name, :last_name, :phone_number,
                        :is_active, :is_superuser, :admin_role_id, :business_id,
                        :creation_reason, :creation_date, :deactivation_reason, :deactivation_date,
                        :activation_reason, :activation_date
                    )
                    ON CONFLICT (email) DO UPDATE SET
                        hashed_password = EXCLUDED.hashed_password,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        phone_number = EXCLUDED.phone_number,
                        is_active = EXCLUDED.is_active,
                        is_superuser = EXCLUDED.is_superuser,
                        admin_role_id = EXCLUDED.admin_role_id,
                        business_id = EXCLUDED.business_id
                    """
                ),
                payload,
            )
            copied += 1

        if users:
            dst.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('users', 'id'), "
                    "(SELECT COALESCE(MAX(id), 1) FROM users))"
                )
            )

    print(f"Copied {copied} user(s) and {len(roles)} admin role(s).")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed staging login users")
    parser.add_argument("--email", default=os.getenv("STAGING_ADMIN_EMAIL", "admin@edutrust.in"))
    parser.add_argument("--password", default=os.getenv("STAGING_ADMIN_PASSWORD", ""))
    parser.add_argument("--first-name", default=os.getenv("STAGING_ADMIN_FIRST_NAME", "Staging"))
    parser.add_argument("--last-name", default=os.getenv("STAGING_ADMIN_LAST_NAME", "Admin"))
    parser.add_argument(
        "--copy-from",
        default=os.getenv("STAGING_USERS_SOURCE_URL", ""),
        help="Copy users+roles from another DATABASE_URL (keeps same passwords)",
    )
    parser.add_argument(
        "--force-admin",
        action="store_true",
        help="Also upsert STAGING_ADMIN_* even when --copy-from is used",
    )
    args = parser.parse_args()

    target_url = normalize_database_url(settings.DATABASE_URL)
    if not target_url or target_url.startswith("sqlite"):
        print("DATABASE_URL must be Postgres (staging Neon).", file=sys.stderr)
        return 1

    if args.copy_from:
        _copy_users_from(args.copy_from, target_url)
        if not args.force_admin and not args.password:
            print("Done. Log in with a copied user email/password.")
            return 0

    password = (args.password or "").strip()
    engine = create_engine(target_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        existing_users = db.query(User).count()
        if not password:
            if existing_users > 0 and not args.force_admin:
                print(f"{existing_users} user(s) already present — nothing to do.")
                return 0
            password = "StagingAdmin!ChangeMe"
            print(
                "STAGING_ADMIN_PASSWORD not set — using default StagingAdmin!ChangeMe "
                "(change after first login)."
            )

        ensure_default_business(db)
        super_role = _ensure_admin_roles(db)
        _upsert_admin_user(
            db,
            email=args.email,
            password=password,
            first_name=args.first_name,
            last_name=args.last_name,
            super_role=super_role,
        )
    finally:
        db.close()

    print(f"Login at staging with email={args.email.strip().lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
