"""POST a simulated Meta WhatsApp inbound payload to a webhook URL."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.whatsapp_config import (  # noqa: E402
    resolve_whatsapp_phone_number_id,
    resolve_whatsapp_waba_id,
)


def build_payload(*, from_phone: str = "918754545407", text: str = "Simulated inbound webhook test") -> dict:
    phone_id = resolve_whatsapp_phone_number_id()
    waba_id = resolve_whatsapp_waba_id()
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": waba_id,
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": from_phone,
                                "phone_number_id": phone_id,
                            },
                            "contacts": [{"profile": {"name": "Ish"}, "wa_id": from_phone}],
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": "wamid.SIMULATED_INBOUND_TEST",
                                    "timestamp": "1719400000",
                                    "text": {"body": text},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002/api/v1/webhooks/whatsapp"
    payload = build_payload()
    r = httpx.post(url, json=payload, timeout=20)
    print(url)
    print("phone_number_id:", payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"])
    print(r.status_code, r.text)


if __name__ == "__main__":
    main()
