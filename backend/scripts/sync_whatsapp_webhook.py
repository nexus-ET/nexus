"""
Register this environment's WhatsApp webhook with Meta.

Each NEXUS environment (local development vs nexus-dev server) must own the
shared WABA webhook exclusively. Run automatically via dev.ps1 / deploy.sh, or:

  python scripts/sync_whatsapp_webhook.py
  python scripts/sync_whatsapp_webhook.py --status
  python scripts/sync_whatsapp_webhook.py --release
  python scripts/sync_whatsapp_webhook.py --callback-url https://nexus-dev.edutrust.in/api/webhook
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")


def verify_callback_reachable(
    callback_url: str,
    verify_token: str,
    *,
    retries: int = 8,
    retry_delay_seconds: float = 2.0,
) -> None:
    challenge = "nexus-webhook-preflight"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": challenge,
    }
    last_error: Exception | None = None
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for attempt in range(1, retries + 1):
            try:
                response = client.get(callback_url, params=params)
                if response.status_code == 200 and response.text.strip() == challenge:
                    return
                last_error = RuntimeError(
                    f"Webhook callback is not reachable: {callback_url} "
                    f"(status={response.status_code}). "
                    "Start dev.ps1 with the Cloudflare tunnel running."
                )
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt < retries:
                time.sleep(retry_delay_seconds)
    raise RuntimeError(
        f"Webhook callback is not reachable after {retries} attempts: {callback_url}"
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Meta WhatsApp webhook for this NEXUS environment")
    parser.add_argument("--dry-run", action="store_true", help="Print target URL only")
    parser.add_argument("--status", action="store_true", help="Show current routing without changes")
    parser.add_argument("--release", action="store_true", help="Hand webhook to NEXUS_WHATSAPP_HANDOFF_URL")
    parser.add_argument("--callback-url", help="Override callback URL (must end with /api/webhook)")
    args = parser.parse_args()

    from app.services.whatsapp_webhook_env import (
        get_webhook_status,
        register_webhook_callback,
        release_webhook_to_handoff_url,
        resolve_verify_token,
        resolve_webhook_callback_url,
        sync_webhook_for_current_environment,
    )

    if args.status:
        status = get_webhook_status()
        print(json.dumps(status.__dict__, indent=2))
        return 0

    if args.release:
        if args.dry_run:
            from app.config import settings

            handoff = (settings.NEXUS_WHATSAPP_HANDOFF_URL or "").strip().rstrip("/")
            print(f"Would hand off webhook to {handoff}/api/webhook")
            return 0
        try:
            release_webhook_to_handoff_url()
        except Exception as exc:
            print(f"Warning: webhook handoff failed: {exc}", file=sys.stderr)
            return 1
        status = get_webhook_status()
        print("Webhook handed off.")
        print(json.dumps(status.__dict__, indent=2))
        return 0

    if args.callback_url:
        callback = args.callback_url.strip().rstrip("/")
        if not callback.endswith("/api/webhook"):
            callback = f"{callback}/api/webhook"
        if args.dry_run:
            print(f"Would register callback -> {callback}")
            return 0
        verify_callback_reachable(callback, resolve_verify_token())
        register_webhook_callback(callback, resolve_verify_token())
    else:
        callback = resolve_webhook_callback_url()
        if args.dry_run:
            print(f"Would register callback -> {callback}")
            return 0
        if not callback:
            raise ValueError("PUBLIC_TUNNEL_BASE is not set")
        verify_callback_reachable(callback, resolve_verify_token())
        sync_webhook_for_current_environment()

    status = get_webhook_status()
    print("Webhook sync complete.")
    print(json.dumps(status.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
