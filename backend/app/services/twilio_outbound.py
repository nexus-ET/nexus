from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from twilio.rest import Client

from app.services.phone_utils import clean_phone_number


def _load_env() -> None:
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir] + list(current_dir.parents):
        target_env = parent / ".env"
        if target_env.exists():
            load_dotenv(dotenv_path=target_env)
            return
    load_dotenv()


def format_whatsapp_address(phone: str) -> str:
    clean = clean_phone_number(phone or "")
    if not clean:
        return ""
    return clean if clean.startswith("whatsapp:") else f"whatsapp:{clean}"


def resolve_whatsapp_addresses(to_phone: str) -> tuple[str, str]:
    _load_env()
    sender_number = os.getenv("TWILIO_WHATSAPP_NUMBER") or ""
    return format_whatsapp_address(to_phone), format_whatsapp_address(sender_number)


def get_twilio_client() -> tuple[Client, str] | None:
    _load_env()
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    sender_number = os.getenv("TWILIO_WHATSAPP_NUMBER")
    if not account_sid or not auth_token or not sender_number:
        return None
    formatted_from = format_whatsapp_address(sender_number)
    if not formatted_from:
        return None
    return Client(account_sid, auth_token), formatted_from


def dispatch_live_whatsapp_message(
    to_phone: str, message_body: str, media_url: Optional[str] = None
) -> bool:
    client_bundle = get_twilio_client()
    if not client_bundle:
        return False

    client, formatted_from = client_bundle
    formatted_to = format_whatsapp_address(to_phone)
    if not formatted_to:
        return False

    try:
        if media_url:
            client.messages.create(
                from_=formatted_from,
                body=message_body,
                to=formatted_to,
                media_url=media_url,
            )
        else:
            client.messages.create(from_=formatted_from, body=message_body, to=formatted_to)
        return True
    except Exception:
        traceback.print_exc()
        return False
