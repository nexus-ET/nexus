#!/usr/bin/env python3
"""List WhatsApp Business phone numbers registered in Meta for the configured WABAs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.whatsapp_config import (  # noqa: E402
    is_local_development,
    resolve_whatsapp_display_phone,
    resolve_whatsapp_phone_number_id,
    resolve_whatsapp_waba_id,
)

GRAPH = "https://graph.facebook.com/v20.0"


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _list_waba_numbers(token: str, waba_id: str, label: str) -> None:
    response = httpx.get(
        f"{GRAPH}/{waba_id}/phone_numbers",
        params={"fields": "id,display_phone_number,verified_name,quality_rating,status"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    if response.status_code >= 400:
        print(f"{label} WABA {waba_id}: Meta API error {response.status_code}: {response.text}")
        return

    numbers = response.json().get("data") or []
    print(f"{label} WABA ({waba_id}):")
    if not numbers:
        print("  (no phone numbers listed)")
        return
    for row in numbers:
        display = row.get("display_phone_number") or "—"
        pid = row.get("id") or "—"
        print(f"  {display}")
        print(f"    phone_number_id: {pid}")
        if row.get("verified_name"):
            print(f"    verified_name:   {row['verified_name']}")
        if row.get("status"):
            print(f"    status:          {row['status']}")
        print()


def main() -> int:
    token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not token:
        print("WHATSAPP_ACCESS_TOKEN is not set in .env", file=sys.stderr)
        return 1

    test_waba = (settings.WHATSAPP_TEST_WABA_ID or "").strip()
    business_waba = (settings.WHATSAPP_BUSINESS_WABA_ID or "").strip()
    if not test_waba and not business_waba:
        print("Set WHATSAPP_TEST_WABA_ID and/or WHATSAPP_BUSINESS_WABA_ID in .env", file=sys.stderr)
        return 1

    print("-" * 72)
    if test_waba:
        _list_waba_numbers(token, test_waba, "Test")
    if business_waba and business_waba != test_waba:
        _list_waba_numbers(token, business_waba, "Business")

    active_phone_id = resolve_whatsapp_phone_number_id()
    active_waba = resolve_whatsapp_waba_id()
    active_display = resolve_whatsapp_display_phone()
    env_label = "development (test line)" if is_local_development() else "staging/business line"

    print("-" * 72)
    print(f"Active environment: {env_label}")
    print(f"Active display phone:       {active_display or '(not set)'}")
    print(f"Active phone_number_id:     {active_phone_id or '(not set)'}")
    print(f"Active WABA id:             {active_waba or '(not set)'}")

    expected_targets = [
        ("WHATSAPP_TEST_PHONE_NUMBER", settings.WHATSAPP_TEST_PHONE_NUMBER, settings.WHATSAPP_TEST_PHONE_NUMBER_ID),
        (
            "WHATSAPP_BUSINESS_PHONE_NUMBER",
            settings.WHATSAPP_BUSINESS_PHONE_NUMBER,
            settings.WHATSAPP_BUSINESS_PHONE_NUMBER_ID,
        ),
    ]
    print("\nConfigured targets:")
    for name, phone, phone_id in expected_targets:
        print(f"  {name}={phone or '(not set)'}  id={phone_id or '(not set)'}")

    print("\nRaw active resolution JSON:")
    print(
        json.dumps(
            {
                "is_local_development": is_local_development(),
                "active_display_phone": active_display,
                "active_phone_number_id": active_phone_id,
                "active_waba_id": active_waba,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
