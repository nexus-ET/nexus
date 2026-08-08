"""WhatsApp booking template language resolution."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.messaging import (
    _language_codes_equal,
    _language_codes_match,
    resolve_meta_template_send_language,
)


def test_language_codes_equal_is_exact():
    assert _language_codes_equal("en", "en")
    assert _language_codes_equal("en_US", "en-us")
    assert not _language_codes_equal("en", "en_US")


def test_language_codes_match_allows_base():
    assert _language_codes_match("en", "en_US")
    assert _language_codes_match("en_US", "en")


def test_resolve_meta_template_send_language_prefers_exact_meta_code():
    async def _run() -> None:
        with patch(
            "app.services.messaging.list_meta_template_language_codes",
            new=AsyncMock(return_value=["en"]),
        ):
            assert await resolve_meta_template_send_language("et_booking_assigned", "en_US") == "en"
            assert await resolve_meta_template_send_language("et_booking_assigned", "en") == "en"

    asyncio.run(_run())


def test_resolve_meta_template_send_language_keeps_exact_when_available():
    async def _run() -> None:
        with patch(
            "app.services.messaging.list_meta_template_language_codes",
            new=AsyncMock(return_value=["en_US", "en"]),
        ):
            assert await resolve_meta_template_send_language("et_booking_assigned", "en_US") == "en_US"

    asyncio.run(_run())
