"""Unit tests for ScanX per-document in-flight claim and enqueue skip."""

from __future__ import annotations

from unittest.mock import patch

from app.services import scanx_queue as queue_mod
from app.services.scanx_cancel import (
    add_job_wait_ms,
    bind_job,
    take_job_wait_ms,
    unbind_job,
)
from app.services.scanx_queue import (
    enqueue_process_document,
    is_scanx_document_inflight,
    release_scanx_document,
    try_claim_scanx_document,
)


def setup_function() -> None:
    with queue_mod._inflight_lock:
        queue_mod._inflight_docs.clear()
    unbind_job()


def teardown_function() -> None:
    with queue_mod._inflight_lock:
        queue_mod._inflight_docs.clear()
    unbind_job()


def test_try_claim_rejects_second_claim_for_same_document() -> None:
    assert try_claim_scanx_document(165) is True
    assert is_scanx_document_inflight(165) is True
    assert try_claim_scanx_document(165) is False
    assert try_claim_scanx_document(166) is True
    release_scanx_document(165)
    assert is_scanx_document_inflight(165) is False
    assert try_claim_scanx_document(165) is True


def test_enqueue_skips_when_document_already_inflight() -> None:
    assert try_claim_scanx_document(42) is True
    result = enqueue_process_document(42, force_thread=True)
    assert result["mode"] == "skipped_inflight"
    assert result["job_id"] == "inflight-42"


def test_rescue_stale_parsing_skips_when_inflight() -> None:
    assert try_claim_scanx_document(99) is True
    assert queue_mod.rescue_stale_parsing_document(99) is None


def test_job_wait_ms_survives_bind_and_is_taken_for_leave_parsing() -> None:
    add_job_wait_ms(12_000)
    bind_job(7)
    add_job_wait_ms(3_000)
    waited = take_job_wait_ms()
    assert waited == 15_000
    assert take_job_wait_ms() == 0


def test_start_thread_noops_second_start_for_same_id() -> None:
    import threading
    import time

    started: list[int] = []
    hold = threading.Event()
    entered = threading.Event()

    def fake_process(document_id: int, *, claimed: bool = False) -> dict:
        started.append(int(document_id))
        entered.set()
        hold.wait(timeout=2.0)
        return {"ok": True, "document_id": int(document_id)}

    with (
        patch.object(queue_mod, "_THREAD_PARSE_SLOTS") as slots,
        patch(
            "app.services.scanx_jobs.process_scanx_document",
            side_effect=fake_process,
        ),
        patch.object(queue_mod, "_mark_thread_dispatch"),
        patch.object(queue_mod, "_seed_enqueue_progress"),
    ):
        slots.acquire.return_value = True
        queue_mod._start_thread(165)
        assert entered.wait(timeout=2.0)
        queue_mod._start_thread(165)
        time.sleep(0.15)
        hold.set()
        deadline = time.time() + 2.0
        while time.time() < deadline and is_scanx_document_inflight(165):
            time.sleep(0.05)

    assert started == [165]
    assert is_scanx_document_inflight(165) is False
