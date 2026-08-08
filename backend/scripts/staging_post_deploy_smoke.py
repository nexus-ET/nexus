#!/usr/bin/env python3
"""
Staging / pre-staging smoke gates from real 2026-08-08 post-deploy failures.

Run on the VPS after hostinger-staging.sh (via verify-staging-deploy.sh), or from
a laptop against staging/local:

  cd backend && source .venv/bin/activate
  python scripts/staging_post_deploy_smoke.py
  python scripts/staging_post_deploy_smoke.py --base-url https://nexus-dev.edutrust.in

Credentials (API checks): STAGING_SMOKE_EMAIL/PASSWORD or UAT_EMAIL/UAT_PASSWORD.
Never prints secrets. Exit 0 = all gates passed; non-zero = at least one failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

# Tables that have bitten staging when rows were imported with explicit ids.
SEQUENCE_TABLES = (
    "candidate_test_scores",
    "navigation_pages",
    "role_page_permissions",
    "notification_logs",
    "counselling_bookings",
)

BOOKING_TEMPLATE_ENV = (
    ("WHATSAPP_BOOKING_TEMPLATE", "WHATSAPP_BOOKING_TEMPLATE_LANGUAGE", "et_booking_confirmation"),
    (
        "WHATSAPP_ADMIN_BOOKING_TEMPLATE",
        "WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE",
        "et_booking_assigned",
    ),
)

REQUIRED_NAV_PATHS = (
    "/book-appointment",
    "/reports/exceptions",
    "/nexus-intel",
    "/flowx",
    "/ai-active",
    "/my-bookings",
)


@dataclass
class GateResult:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, label: str) -> None:
        print(f"  OK   {label}")

    def fail(self, label: str, detail: str = "") -> None:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  FAIL {msg}", file=sys.stderr)
        self.failures.append(msg)

    def warn(self, label: str, detail: str = "") -> None:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  WARN {msg}", file=sys.stderr)
        self.warnings.append(msg)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def check_env_shape(result: GateResult, *, allow_local: bool) -> None:
    print("\n==> Env shape (names only)")
    critical = (
        "DATABASE_URL",
        "FRONTEND_URL",
        "PUBLIC_TUNNEL_BASE",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_BOOKING_TEMPLATE",
        "WHATSAPP_ADMIN_BOOKING_TEMPLATE",
        "WHATSAPP_BOOKING_TEMPLATE_LANGUAGE",
        "WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE",
    )
    for key in critical:
        value = _env(key)
        if not value:
            result.fail(f"{key} missing/empty")
        else:
            result.ok(f"{key} set (len={len(value)})")

    frontend = _env("FRONTEND_URL").lower()
    if frontend.startswith("http://127.") or "localhost" in frontend:
        if allow_local:
            result.warn("FRONTEND_URL looks local (allowed for local smoke)", frontend)
        else:
            result.fail("FRONTEND_URL looks local", frontend)
    if _env("NEXUS_TUNNEL_ENABLED").lower() in {"1", "true", "yes"}:
        if allow_local:
            result.warn("NEXUS_TUNNEL_ENABLED=true (allowed for local smoke)")
        else:
            result.fail("NEXUS_TUNNEL_ENABLED must be false on staging")
    if _env("R2_BUCKET_NAME") == "nexus-edutrust":
        result.warn("R2_BUCKET_NAME is develop bucket", "prefer nexus-edutrust-staging")


def check_id_sequences(result: GateResult) -> None:
    print("\n==> Postgres id sequences")
    database_url = _env("DATABASE_URL")
    if not database_url:
        result.fail("DATABASE_URL missing — cannot check sequences")
        return

    engine = create_engine(database_url)
    with engine.connect() as conn:
        for table in SEQUENCE_TABLES:
            exists = conn.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": table},
            ).scalar()
            if not exists:
                result.warn(f"table {table} missing — skip sequence check")
                continue
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:table, 'id')"),
                {"table": table},
            ).scalar()
            if not seq:
                result.warn(f"{table}.id has no serial sequence")
                continue
            max_id = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")).scalar() or 0
            last_value, is_called = conn.execute(
                text(f"SELECT last_value, is_called FROM {seq}")
            ).fetchone()
            next_id = int(last_value) + (1 if is_called else 0)
            # When is_called is false, next nextval returns last_value as-is.
            effective_next = int(last_value) if not is_called else int(last_value) + 1
            if max_id > 0 and effective_next <= max_id:
                result.fail(
                    f"{table} sequence behind MAX(id)",
                    f"max_id={max_id} next≈{effective_next} seq={seq}",
                )
            else:
                result.ok(f"{table} sequence ok (max_id={max_id}, last={last_value})")


def check_navigation_rbac(result: GateResult) -> None:
    print("\n==> Navigation RBAC")
    database_url = _env("DATABASE_URL")
    if not database_url:
        return
    engine = create_engine(database_url)
    with engine.connect() as conn:
        if not conn.execute(text("SELECT to_regclass('navigation_pages') IS NOT NULL")).scalar():
            result.fail("navigation_pages table missing")
            return
        pages = conn.execute(text("SELECT COUNT(*) FROM navigation_pages")).scalar() or 0
        perms = conn.execute(text("SELECT COUNT(*) FROM role_page_permissions")).scalar() or 0
        if pages < 5:
            result.fail("navigation_pages under-seeded", f"count={pages}")
        else:
            result.ok(f"navigation_pages={pages}")
        if perms < 5:
            result.fail("role_page_permissions under-seeded", f"count={perms}")
        else:
            result.ok(f"role_page_permissions={perms}")
        for path in REQUIRED_NAV_PATHS:
            found = conn.execute(
                text("SELECT 1 FROM navigation_pages WHERE route = :path LIMIT 1"),
                {"path": path},
            ).scalar()
            if found:
                result.ok(f"nav has {path}")
            else:
                result.fail(f"nav missing {path}", "run ensure_navigation_rbac.py")


def check_whatsapp_booking_templates(result: GateResult) -> None:
    print("\n==> WhatsApp booking templates (Meta business WABA)")
    token = _env("WHATSAPP_ACCESS_TOKEN")
    if not token:
        result.fail("WHATSAPP_ACCESS_TOKEN missing — cannot verify templates")
        return

    from app.config import settings
    from app.services.messaging import WHATSAPP_GRAPH_API_BASE, list_meta_template_language_codes
    from app.services.whatsapp_config import (
        is_local_development,
        resolve_whatsapp_phone_number_id,
        resolve_whatsapp_waba_id,
    )

    waba = resolve_whatsapp_waba_id()
    phone = resolve_whatsapp_phone_number_id()
    line = "test" if is_local_development() else "business"
    print(f"    line={line} waba={waba or '?'} phone_id={phone or '?'}")
    if not waba:
        result.fail("WhatsApp WABA id unresolved")
        return
    if not phone:
        result.fail("WhatsApp phone_number_id unresolved")

    # Prefer business WABA on staging even if local-dev helpers would pick test.
    business_waba = (_env("WHATSAPP_BUSINESS_WABA_ID") or getattr(settings, "WHATSAPP_BUSINESS_WABA_ID", None) or "").strip()
    check_waba = business_waba or waba
    if business_waba and business_waba != waba:
        print(f"    also checking business WABA {business_waba} (staging must use this)")

    import asyncio

    async def _langs(name: str) -> list[str]:
        # list_meta_template_language_codes uses resolve_whatsapp_waba_id();
        # for staging we also probe business WABA directly.
        url = f"{WHATSAPP_GRAPH_API_BASE}/{check_waba}/message_templates"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                params={"name": name, "limit": "50"},
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            return []
        approved: list[str] = []
        pending: list[str] = []
        for row in response.json().get("data") or []:
            if str(row.get("name") or "") != name:
                continue
            language = str(row.get("language") or "").strip()
            status = str(row.get("status") or "").upper()
            if status in {"APPROVED", "ACTIVE", ""}:
                if language and language not in approved:
                    approved.append(language)
            elif language and language not in pending:
                pending.append(f"{language}:{status or 'UNKNOWN'}")
        return approved or pending

    for name_key, lang_key, default_name in BOOKING_TEMPLATE_ENV:
        template = _env(name_key) or default_name
        preferred = _env(lang_key) or "en"
        langs = asyncio.run(_langs(template))
        if not langs:
            result.fail(
                f"Meta template {template!r} missing on WABA {check_waba}",
                "register via scripts/register_whatsapp_booking_templates.py on BUSINESS WABA",
            )
            continue
        # Pending-only entries look like "en:PENDING"
        if all(":" in item for item in langs):
            result.fail(
                f"Meta template {template!r} not APPROVED",
                ", ".join(langs),
            )
            continue
        if preferred not in langs and not any(
            preferred.split("_")[0] == lang.split("_")[0] for lang in langs
        ):
            result.fail(
                f"template {template!r} language mismatch",
                f"env {lang_key}={preferred!r} Meta={langs}",
            )
        else:
            # Soft prefer exact code
            if preferred not in langs:
                result.warn(
                    f"{template} preferred {preferred!r} not exact",
                    f"Meta has {langs} — set {lang_key} to Meta's exact code",
                )
            result.ok(f"{template} APPROVED languages={langs}")

        # Also ensure list helper path works
        try:
            helper_langs = asyncio.run(list_meta_template_language_codes(template))
            if helper_langs:
                result.ok(f"resolver sees {template} → {helper_langs}")
        except Exception as exc:  # noqa: BLE001
            result.warn(f"list_meta_template_language_codes({template})", str(exc))


def _api_login(client: httpx.Client, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/login",
        data={"username": email, "password": password},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("login response missing access_token")
    return str(token)


def check_api_smoke(result: GateResult, base_url: str, email: str, password: str) -> None:
    print(f"\n==> API smoke ({base_url})")
    if not email or not password:
        result.warn("API smoke skipped — set STAGING_SMOKE_EMAIL/PASSWORD or UAT_EMAIL/UAT_PASSWORD")
        return

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0, follow_redirects=True) as client:
        try:
            token = _api_login(client, email, password)
            result.ok("login")
        except Exception as exc:  # noqa: BLE001
            result.fail("login", str(exc))
            return

        headers = {"Authorization": f"Bearer {token}"}

        r = client.get("/api/v1/leads/status-definitions", headers=headers)
        if r.status_code == 200 and (r.json() if r.content else None) is not None:
            result.ok("status-definitions")
        else:
            result.fail("status-definitions", f"status={r.status_code}")

        r = client.get("/api/v1/bookings/mine", headers=headers)
        if r.status_code != 200:
            result.fail("bookings/mine", f"status={r.status_code}")
            return
        result.ok("bookings/mine")
        mine = r.json()
        booking_id = None
        for section in ("today", "upcoming", "past"):
            for row in mine.get(section) or []:
                booking_id = row.get("id")
                if booking_id:
                    break
            if booking_id:
                break

        # Prefer explicit smoke booking if set.
        booking_id = int(_env("UAT_BOOKING_ID") or booking_id or 0) or None

        # Create a far-future staff booking so we always exercise notify + scores.
        day = (datetime.now(timezone.utc) + timedelta(days=14)).date()
        avail = client.get(
            "/api/v1/bookings/availability",
            headers=headers,
            params={"admin_id": 1, "date": day.isoformat()},
        )
        slot_start = None
        if avail.status_code == 200:
            for slot in avail.json().get("slots") or []:
                if slot.get("available"):
                    slot_start = slot.get("start")
                    break
        if slot_start:
            create = client.post(
                "/api/v1/bookings/staff",
                headers=headers,
                json={
                    "scheduled_time": slot_start,
                    "admin_id": 1,
                    "candidate_name": "Staging Smoke",
                    "candidate_email": email,
                    "candidate_phone": _env("STAGING_SMOKE_PHONE") or None,
                    "lead_id": int(_env("UAT_LEAD_ID") or "0") or None,
                    "session_purpose": "UAT smoke",
                    "notes": "Purpose: UAT smoke",
                },
            )
            if create.status_code == 200:
                body = create.json()
                booking_id = body.get("id") or booking_id
                notifications = body.get("notifications") or {}
                result.ok(f"staff booking #{booking_id} created")
                for channel in ("email", "email_admin"):
                    status = notifications.get(channel)
                    if status in {"sent", "skipped", "disabled"}:
                        result.ok(f"notify {channel}={status}")
                    elif status == "failed":
                        result.fail(f"notify {channel}=failed")
                    else:
                        result.warn(f"notify {channel}", repr(status))
                for channel in ("whatsapp", "whatsapp_admin"):
                    status = notifications.get(channel)
                    if status == "sent":
                        result.ok(f"notify {channel}=sent")
                    elif status == "failed":
                        # Fail hard — this burned ~hours on 2026-08-08.
                        result.fail(
                            f"notify {channel}=failed",
                            "check Meta templates on BUSINESS WABA + *_TEMPLATE_LANGUAGE",
                        )
                    elif status in {"skipped", "disabled"}:
                        result.warn(f"notify {channel}={status}")
                    else:
                        result.warn(f"notify {channel}", repr(status))
            else:
                result.warn("staff booking create", f"status={create.status_code} {(create.text or '')[:160]}")
        else:
            result.warn("no available slot for staff booking smoke")

        if not booking_id:
            result.warn("TOEFL save skipped — no booking id")
            return

        payload = {
            "test_name": "TOEFL",
            "test_date": date.today().isoformat(),
            "overall_score": "110",
            "sections": [
                {"section_name": "Reading", "score": "28"},
                {"section_name": "Listening", "score": "28"},
                {"section_name": "Speaking", "score": "27"},
                {"section_name": "Writing", "score": "27"},
            ],
        }
        save = client.post(
            f"/api/v1/bookings/mine/{booking_id}/test-scores",
            headers=headers,
            json=payload,
        )
        if save.status_code == 200:
            scores = (save.json() or {}).get("scores") or []
            if scores:
                result.ok(f"TOEFL save on booking #{booking_id} ({len(scores)} rows)")
            else:
                result.fail("TOEFL save returned empty scores")
        else:
            result.fail(
                f"TOEFL save HTTP {save.status_code}",
                (save.text or "")[:240],
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=_env("STAGING_SMOKE_BASE_URL")
        or _env("UAT_BASE_URL")
        or _env("FRONTEND_URL")
        or "https://nexus-dev.edutrust.in",
    )
    parser.add_argument("--skip-env", action="store_true")
    parser.add_argument("--skip-db", action="store_true")
    parser.add_argument("--skip-meta", action="store_true")
    parser.add_argument("--skip-api", action="store_true")
    parser.add_argument(
        "--strict-local",
        action="store_true",
        help="Also fail on warnings when running against local (default: warnings ok).",
    )
    parser.add_argument(
        "--allow-local-env",
        action="store_true",
        help="Do not fail on local FRONTEND_URL / NEXUS_TUNNEL_ENABLED (for develop smoke).",
    )
    return parser.parse_args()


def _detect_allow_local(args: argparse.Namespace) -> bool:
    if args.allow_local_env:
        return True
    # On the VPS, always enforce staging env shape.
    if Path("/var/www/nexus/backend/.env").exists():
        return False
    instance = (_env("NEXUS_INSTANCE") or _env("ENVIRONMENT") or "").lower()
    if instance in {"nexus-dev", "staging", "staging-local"}:
        return False
    base = (args.base_url or "").lower()
    if "127.0.0.1" in base or "localhost" in base:
        return True
    # Laptop smoke against remote staging still loads local develop .env —
    # do not fail on local FRONTEND_URL / tunnel flags in that case.
    if "nexus-dev" in base or "edutrust.in" in base:
        return True
    if instance in {"development", "dev", "local"} or instance.startswith("dev"):
        return True
    return False


def main() -> int:
    args = parse_args()
    result = GateResult()
    allow_local = _detect_allow_local(args)
    print(f"==> Staging post-deploy smoke ({datetime.now(timezone.utc).isoformat()})")
    print(f"    allow_local_env={allow_local}")

    if not args.skip_env:
        check_env_shape(result, allow_local=allow_local)
    if not args.skip_db:
        check_id_sequences(result)
        check_navigation_rbac(result)
    if not args.skip_meta:
        check_whatsapp_booking_templates(result)

    email = _env("STAGING_SMOKE_EMAIL") or _env("UAT_EMAIL")
    password = _env("STAGING_SMOKE_PASSWORD") or _env("UAT_PASSWORD")
    if not args.skip_api:
        base = args.base_url.rstrip("/")
        check_api_smoke(result, base, email, password)

    print("")
    if result.failures:
        print(f"==> {len(result.failures)} failure(s), {len(result.warnings)} warning(s).", file=sys.stderr)
        for item in result.failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    if args.strict_local and result.warnings:
        print(f"==> {len(result.warnings)} warning(s) treated as failures (--strict-local).", file=sys.stderr)
        return 1
    if result.warnings:
        print(f"==> All required gates passed ({len(result.warnings)} warning(s)).")
        return 0
    print("==> All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
