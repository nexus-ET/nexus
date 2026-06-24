from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import settings
from app.services.messaging import process_meta_webhook_payload
from app.services.leads import process_leadgen_webhook_payload

logger = logging.getLogger(__name__)

router = APIRouter()

HubModeQuery = Annotated[str | None, Query(alias="hub.mode")]
HubVerifyTokenQuery = Annotated[str | None, Query(alias="hub.verify_token")]
HubChallengeQuery = Annotated[str | None, Query(alias="hub.challenge")]


def _resolve_verify_token() -> str:
    """Prefer WEBHOOK_VERIFY_TOKEN; fall back to legacy WHATSAPP_VERIFY_TOKEN."""
    for value in (settings.WEBHOOK_VERIFY_TOKEN, settings.WHATSAPP_VERIFY_TOKEN):
        token = (value or "").strip()
        if token:
            return token
    return ""


def _log_handshake(
    *,
    raw_mode: str | None,
    raw_verify_token: str | None,
    raw_challenge: str | None,
    normalized_mode: str,
    normalized_verify_token: str,
    normalized_challenge: str,
) -> None:
    """Log raw Meta query params and normalized values for terminal debugging."""
    message = (
        "Meta webhook handshake received | "
        f"raw hub.mode={raw_mode!r} hub.verify_token={raw_verify_token!r} hub.challenge={raw_challenge!r} | "
        f"normalized hub.mode={normalized_mode!r} hub.verify_token={normalized_verify_token!r} "
        f"hub.challenge={normalized_challenge!r}"
    )
    logger.info(message)
    print(f"[Meta Webhook] {message}")


@router.get("/webhook/info")
async def meta_webhook_info():
    """Dev helper: current callback URL Meta must use (from PUBLIC_TUNNEL_BASE in .env)."""
    tunnel = (os.getenv("PUBLIC_TUNNEL_BASE") or "").strip().rstrip("/")
    callback = f"{tunnel}/api/webhook" if tunnel else None
    return {
        "callback_url": callback,
        "verify_token_configured": bool(_resolve_verify_token()),
        "whatsapp_phone_number_id": (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip() or None,
        "note": "Update Meta Developer Console whenever dev.ps1 prints a new tunnel URL.",
    }


@router.get("/webhook")
async def verify_meta_webhook(
    hub_mode: HubModeQuery = None,
    hub_verify_token: HubVerifyTokenQuery = None,
    hub_challenge: HubChallengeQuery = None,
):
    """
    Meta/WhatsApp webhook verification handshake (GET).

    Meta sends hub.mode, hub.verify_token, and hub.challenge as query parameters.
    On success the hub.challenge value must be echoed back as plain text with HTTP 200.

    Debugging responses:
    - 400 Bad Request: one or more required query parameters were missing or blank.
    - 403 Forbidden: parameters present but hub.mode is not "subscribe" or verify token mismatch.
      Compare logged hub.verify_token with WEBHOOK_VERIFY_TOKEN in .env (both are .strip()'d).
    - 404 in tunnel logs: Meta is hitting the wrong path; use https://<host>/api/webhook.
    - Meta dashboard fails but curl to localhost works: tunnel URL is stale or cloudflared is down.
    """
    mode = (hub_mode or "").strip()
    received_token = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()
    expected_token = _resolve_verify_token()

    _log_handshake(
        raw_mode=hub_mode,
        raw_verify_token=hub_verify_token,
        raw_challenge=hub_challenge,
        normalized_mode=mode,
        normalized_verify_token=received_token,
        normalized_challenge=challenge,
    )

    missing: list[str] = []
    if not mode:
        missing.append("hub.mode")
    if not received_token:
        missing.append("hub.verify_token")
    if not challenge:
        missing.append("hub.challenge")

    if missing:
        detail = f"Missing required query parameters: {', '.join(missing)}"
        logger.warning("Meta webhook handshake rejected: %s", detail)
        print(f"[Meta Webhook] REJECTED 400: {detail}")
        return Response(content=detail, status_code=400, media_type="text/plain")

    if not expected_token:
        detail = "Server misconfiguration: WEBHOOK_VERIFY_TOKEN is not set"
        logger.error("Meta webhook handshake rejected: %s", detail)
        print(f"[Meta Webhook] REJECTED 403: {detail}")
        return Response(content="Forbidden", status_code=403, media_type="text/plain")

    if mode == "subscribe" and received_token == expected_token:
        logger.info("Meta webhook verification succeeded; echoing hub.challenge=%r", challenge)
        print(f"[Meta Webhook] SUCCESS 200: echoing hub.challenge={challenge!r}")
        return PlainTextResponse(content=challenge)

    logger.warning(
        "Meta webhook verification failed: mode=%r token_match=%s expected_token_len=%d received_token_len=%d",
        mode,
        received_token == expected_token,
        len(expected_token),
        len(received_token),
    )
    print(
        "[Meta Webhook] REJECTED 403: "
        f"mode={mode!r} token_match={received_token == expected_token} "
        f"(expected_token_len={len(expected_token)}, received_token_len={len(received_token)})"
    )
    return Response(content="Forbidden", status_code=403, media_type="text/plain")


async def _parse_meta_webhook_payload(request: Request) -> dict[str, Any] | None:
    """
    Parse Meta webhook POST bodies.

    Meta WhatsApp / Leadgen webhooks use application/json. Some dashboard tools
    or proxies may send form-encoded wrappers — handle those when present.
    """
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    raw = await request.body()
    if not raw or not raw.strip():
        logger.warning("Meta webhook POST with empty body (content-type=%r)", content_type)
        print(f"[Meta Webhook] ignored empty POST body (content-type={content_type!r})")
        return None

    text = raw.decode("utf-8-sig", errors="replace").strip()

    if content_type == "application/x-www-form-urlencoded":
        form = parse_qs(text, keep_blank_values=True)
        for key in ("payload", "entry", "object"):
            values = form.get(key)
            if values and values[0].strip():
                text = values[0].strip()
                break

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(
            "Meta webhook invalid JSON: %s | content-type=%r len=%d body_prefix=%r",
            exc,
            content_type,
            len(text),
            text[:500],
        )
        print(
            "[Meta Webhook] INVALID JSON — "
            f"{exc} | content-type={content_type!r} len={len(text)} "
            f"body_prefix={text[:500]!r}"
        )
        return None

    if not isinstance(parsed, dict):
        logger.warning("Meta webhook JSON root is not an object: %r", type(parsed).__name__)
        return None

    return parsed


@router.post("/webhook")
async def receive_meta_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Meta webhook delivery endpoint (POST).

    Single endpoint for WhatsApp messages, Facebook Lead Ads, and Instagram Lead Ads.

    Leadgen notifications (field=leadgen) fetch full lead data from Meta Graph API
    asynchronously and persist via save_lead(). WhatsApp payloads use the messaging pipeline.

    Returns 200 OK immediately, then processes payload in the background so Meta
    does not disable the webhook for slow AI responses.
    """
    # TODO: Validate X-Hub-Signature-256 using the app secret before processing payloads.

    payload = await _parse_meta_webhook_payload(request)
    if payload is None:
        return Response(status_code=200)

    logger.info("Meta webhook raw JSON payload: %s", payload)
    print(f"[Meta Webhook] raw JSON payload: {payload}")

    # Leadgen: extract leadgen_id(s), fetch Graph details async, persist via save_lead().
    background_tasks.add_task(process_leadgen_webhook_payload, payload)
    # WhatsApp messaging and other Meta object types.
    background_tasks.add_task(process_meta_webhook_payload, payload)
    return Response(status_code=200)
