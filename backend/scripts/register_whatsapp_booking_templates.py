#!/usr/bin/env python3
"""
Register WhatsApp UTILITY templates for booking confirmations (Meta).

Business-initiated booking alerts cannot use free-form session text outside the
24-hour customer care window. These templates open delivery for staff bookings.

Creates (if missing):
  - et_booking_confirmation   (candidate)
  - et_booking_assigned       (counsellor)

Usage (from backend root, with .env loaded):

    python scripts/register_whatsapp_booking_templates.py
    python scripts/register_whatsapp_booking_templates.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services.messaging import WHATSAPP_GRAPH_API_BASE  # noqa: E402
from app.services.whatsapp_config import resolve_whatsapp_waba_id  # noqa: E402

CANDIDATE_TEMPLATE = {
    "name": "et_booking_confirmation",
    "language": "en",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            "text": (
                "Hi {{1}}, your counselling session with {{2}} is confirmed for {{3}}. "
                "Purpose: {{4}}. Use the Reschedule or Cancel options in this chat for your latest booking."
            ),
            "example": {
                "body_text": [
                    ["Alex", "Ishq Ahmed", "Sat, Aug 08 at 03:00 PM", "Course guidance"]
                ]
            },
        }
    ],
}

ADMIN_TEMPLATE = {
    "name": "et_booking_assigned",
    "language": "en",
    "category": "UTILITY",
    "components": [
        {
            "type": "BODY",
            # Meta rejects templates that start or end with a variable.
            "text": (
                "Hi {{1}}, a counselling session has been assigned to you. "
                "Student: {{2}}. When: {{3}}. Booking ID {{4}}. Please open it in Nexus."
            ),
            "example": {
                "body_text": [["Ishq Ahmed", "Alex", "Sat, Aug 08 at 03:00 PM", "97"]]
            },
        }
    ],
}


def _list_templates(client: httpx.Client, waba_id: str, access_token: str, name: str) -> list[dict]:
    url = f"{WHATSAPP_GRAPH_API_BASE}/{waba_id}/message_templates"
    response = client.get(
        url,
        params={"name": name, "limit": "50"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return list(response.json().get("data") or [])


def _ensure_template(
    client: httpx.Client,
    *,
    waba_id: str,
    access_token: str,
    payload: dict,
    dry_run: bool,
) -> int:
    name = payload["name"]
    language = payload["language"]
    print(f"\nTemplate: {name} ({language})")
    print(f"Body: {payload['components'][0]['text']}")

    if dry_run:
        print("Dry run — not calling Meta.")
        return 0

    existing = _list_templates(client, waba_id, access_token, name)
    for row in existing:
        if str(row.get("name") or "") == name and str(row.get("language") or "") == language:
            status = row.get("status") or "unknown"
            print(f"Already exists (status={status}, id={row.get('id')}).")
            if status != "APPROVED":
                print("Wait for Meta approval before booking WhatsApp will deliver.")
            return 0

    url = f"{WHATSAPP_GRAPH_API_BASE}/{waba_id}/message_templates"
    response = client.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code >= 400:
        print(f"Meta API error ({response.status_code}): {response.text}", file=sys.stderr)
        return 1

    data = response.json()
    print(f"Created id={data.get('id')} status={data.get('status', 'PENDING')}.")
    print("Approve in Meta Business Manager if not auto-approved, then restart nexus-backend.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Register WhatsApp booking utility templates.")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads only.")
    args = parser.parse_args()

    waba_id = resolve_whatsapp_waba_id()
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not waba_id or not access_token:
        print("ERROR: WHATSAPP_ACCESS_TOKEN and WABA id are required in .env", file=sys.stderr)
        return 1

    # Prefer configured names when present.
    candidate = dict(CANDIDATE_TEMPLATE)
    admin = dict(ADMIN_TEMPLATE)
    configured_candidate = (settings.WHATSAPP_BOOKING_TEMPLATE or "").strip()
    configured_admin = (settings.WHATSAPP_ADMIN_BOOKING_TEMPLATE or "").strip()
    if configured_candidate:
        candidate["name"] = configured_candidate
    if configured_admin:
        admin["name"] = configured_admin
    cand_lang = (settings.WHATSAPP_BOOKING_TEMPLATE_LANGUAGE or "en").strip() or "en"
    admin_lang = (settings.WHATSAPP_ADMIN_BOOKING_TEMPLATE_LANGUAGE or "en").strip() or "en"
    candidate["language"] = cand_lang
    admin["language"] = admin_lang

    rc = 0
    with httpx.Client(timeout=30.0) as client:
        rc |= _ensure_template(
            client, waba_id=waba_id, access_token=access_token, payload=candidate, dry_run=args.dry_run
        )
        rc |= _ensure_template(
            client, waba_id=waba_id, access_token=access_token, payload=admin, dry_run=args.dry_run
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
