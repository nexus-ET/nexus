#!/usr/bin/env python3
"""
Register the WhatsApp outreach follow-up Utility template with Meta.

Creates et_intake_continue (or WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE) if missing.
Template must be approved in Meta before Nexus can send it.

Usage (from backend root, with .env loaded):

    python scripts/register_whatsapp_followup_template.py
    python scripts/register_whatsapp_followup_template.py --dry-run
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
from app.services.intake_templates import OUTREACH_CONTINUE_PROMPT  # noqa: E402
from app.services.messaging import WHATSAPP_GRAPH_API_BASE  # noqa: E402
from app.services.whatsapp_config import resolve_whatsapp_waba_id  # noqa: E402

DEFAULT_TEMPLATE_NAME = "et_intake_continue"
DEFAULT_LANGUAGE = "en"


def _template_name() -> str:
    return (settings.WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE or DEFAULT_TEMPLATE_NAME).strip()


def _language_code() -> str:
    return (
        (settings.WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE_LANGUAGE or "").strip()
        or DEFAULT_LANGUAGE
    )


def _list_templates(client: httpx.Client, waba_id: str, access_token: str) -> list[dict]:
    url = f"{WHATSAPP_GRAPH_API_BASE}/{waba_id}/message_templates"
    response = client.get(
        url,
        params={"name": _template_name(), "limit": "50"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return list(response.json().get("data") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Register WhatsApp outreach follow-up template in Meta.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload only; do not call Meta.")
    args = parser.parse_args()

    waba_id = resolve_whatsapp_waba_id()
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not waba_id or not access_token:
        print("ERROR: WHATSAPP_ACCESS_TOKEN and WABA id are required in .env", file=sys.stderr)
        return 1

    name = _template_name()
    language = _language_code()
    body_text = OUTREACH_CONTINUE_PROMPT

    payload = {
        "name": name,
        "language": language,
        "category": "UTILITY",
        "components": [{"type": "BODY", "text": body_text}],
    }

    print(f"Template name: {name}")
    print(f"Language: {language}")
    print(f"Body: {body_text}")

    if args.dry_run:
        print("Dry run — not calling Meta.")
        return 0

    with httpx.Client(timeout=30.0) as client:
        existing = _list_templates(client, waba_id, access_token)
        for row in existing:
            if str(row.get("name") or "") == name and str(row.get("language") or "") == language:
                status = row.get("status") or "unknown"
                print(f"Template already exists (status={status}, id={row.get('id')}).")
                if status != "APPROVED":
                    print("Wait for Meta approval, then retry outreach on staging.")
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
        print(f"Created template id={data.get('id')} status={data.get('status', 'PENDING')}.")
        print("Approve in Meta Business Manager if not auto-approved, then restart nexus-backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
