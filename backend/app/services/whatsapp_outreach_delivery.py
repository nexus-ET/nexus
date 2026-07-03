"""Track Meta WhatsApp outbound delivery status for ordered outreach sequences."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

ACCEPTABLE_OUTBOUND_STATUSES = frozenset({"sent", "delivered", "read"})
DELIVERED_OUTBOUND_STATUSES = frozenset({"delivered", "read"})

_events: dict[str, asyncio.Event] = {}
_delivered_events: dict[str, asyncio.Event] = {}
_early_statuses: dict[str, str] = {}
_latest_statuses: dict[str, str] = {}


def extract_whatsapp_status_updates(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (wamid, status) pairs from a Meta WhatsApp webhook payload."""
    updates: list[tuple[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status_row in value.get("statuses", []):
                message_id = str(status_row.get("id") or "").strip()
                status = str(status_row.get("status") or "").strip().lower()
                if message_id and status:
                    updates.append((message_id, status))
    return updates


def notify_whatsapp_outbound_status(message_id: str, status: str) -> None:
    """Called from webhook handlers when Meta reports outbound message progress."""
    message_id = (message_id or "").strip()
    normalized = (status or "").strip().lower()
    if not message_id or normalized not in ACCEPTABLE_OUTBOUND_STATUSES:
        return

    previous = _latest_statuses.get(message_id)
    if previous != normalized:
        _latest_statuses[message_id] = normalized
        logger.info("WhatsApp outbound status %s for message_id=%s", normalized, message_id)

    event = _events.get(message_id)
    if event is not None:
        event.set()
        _events.pop(message_id, None)

    if normalized in DELIVERED_OUTBOUND_STATUSES:
        _early_statuses.pop(message_id, None)
        delivered_event = _delivered_events.get(message_id)
        if delivered_event is not None:
            delivered_event.set()
            _delivered_events.pop(message_id, None)
        return

    if event is None:
        _early_statuses[message_id] = normalized
        logger.info(
            "WhatsApp outbound status %s arrived before waiter registered for message_id=%s",
            normalized,
            message_id,
        )


async def wait_for_whatsapp_outbound_status(
    message_id: str,
    *,
    timeout_seconds: float = 3.0,
) -> bool:
    """
    Block until Meta reports sent/delivered/read for this wamid, or timeout.

    Returns True when an acceptable status was observed, False on timeout.
    """
    message_id = (message_id or "").strip()
    if not message_id:
        return False

    if _latest_statuses.get(message_id) in ACCEPTABLE_OUTBOUND_STATUSES:
        return True

    if _early_statuses.pop(message_id, None):
        return True

    event = asyncio.Event()
    _events[message_id] = event
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
        return True
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out waiting %.1fs for WhatsApp delivery status on message_id=%s",
            timeout_seconds,
            message_id,
        )
        return False
    finally:
        _events.pop(message_id, None)


async def wait_for_whatsapp_template_delivered(
    message_id: str,
    *,
    timeout_seconds: float = 15.0,
) -> bool:
    """
    Block until Meta reports delivered/read for a template wamid, or timeout.

    Session messages must wait for template delivery — not merely API acceptance
    or a sent webhook — or WhatsApp may accept the follow-up but not deliver it.
    """
    message_id = (message_id or "").strip()
    if not message_id:
        return False

    if _latest_statuses.get(message_id) in DELIVERED_OUTBOUND_STATUSES:
        return True

    early = _early_statuses.pop(message_id, None)
    if early in DELIVERED_OUTBOUND_STATUSES:
        return True

    event = asyncio.Event()
    _delivered_events[message_id] = event
    try:
        if _latest_statuses.get(message_id) in DELIVERED_OUTBOUND_STATUSES:
            return True
        await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
        return True
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out waiting %.1fs for WhatsApp template delivery on message_id=%s",
            timeout_seconds,
            message_id,
        )
        return False
    finally:
        _delivered_events.pop(message_id, None)


def process_whatsapp_status_webhook(payload: dict[str, Any]) -> int:
    """Notify delivery waiters for all status rows in a webhook payload."""
    count = 0
    for message_id, status in extract_whatsapp_status_updates(payload):
        notify_whatsapp_outbound_status(message_id, status)
        count += 1
    return count
