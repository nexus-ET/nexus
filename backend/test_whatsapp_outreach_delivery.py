from __future__ import annotations

import asyncio

import pytest

from app.services.whatsapp_outreach_delivery import (
    extract_whatsapp_status_updates,
    notify_whatsapp_outbound_status,
    wait_for_whatsapp_outbound_status,
    wait_for_whatsapp_template_delivered,
)


def test_extract_whatsapp_status_updates() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {"id": "wamid.abc", "status": "sent"},
                                {"id": "wamid.def", "status": "delivered"},
                            ]
                        }
                    }
                ]
            }
        ]
    }
    assert extract_whatsapp_status_updates(payload) == [
        ("wamid.abc", "sent"),
        ("wamid.def", "delivered"),
    ]


def test_wait_for_whatsapp_outbound_status_completes_on_notify() -> None:
    async def _run() -> None:
        async def _notify_later() -> None:
            await asyncio.sleep(0.05)
            notify_whatsapp_outbound_status("wamid.test", "sent")

        task = asyncio.create_task(_notify_later())
        try:
            assert await wait_for_whatsapp_outbound_status("wamid.test", timeout_seconds=2.0) is True
        finally:
            await task

    asyncio.run(_run())


def test_wait_for_whatsapp_outbound_status_handles_early_notify() -> None:
    async def _run() -> None:
        notify_whatsapp_outbound_status("wamid.early", "delivered")
        assert await wait_for_whatsapp_outbound_status("wamid.early", timeout_seconds=1.0) is True

    asyncio.run(_run())


def test_wait_for_whatsapp_template_delivered_ignores_sent_only() -> None:
    async def _run() -> None:
        async def _notify_later() -> None:
            await asyncio.sleep(0.05)
            notify_whatsapp_outbound_status("wamid.template", "delivered")

        task = asyncio.create_task(_notify_later())
        try:
            assert (
                await wait_for_whatsapp_template_delivered("wamid.template", timeout_seconds=2.0)
                is True
            )
        finally:
            await task

    asyncio.run(_run())


def test_wait_for_whatsapp_template_delivered_times_out_on_sent_only() -> None:
    async def _run() -> None:
        notify_whatsapp_outbound_status("wamid.sent_only", "sent")
        assert (
            await wait_for_whatsapp_template_delivered("wamid.sent_only", timeout_seconds=0.05)
            is False
        )

    asyncio.run(_run())
