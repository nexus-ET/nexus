"""Unit tests for ScanX per-document in-flight claim and enqueue skip."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

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


def test_two_uploads_same_document_cannot_both_enter_worker() -> None:
    """Two uploads of the same document_id cannot both enter the worker."""
    entered: list[int] = []
    hold = threading.Event()
    first_inside = threading.Event()

    def fake_process(document_id: int, *, claimed: bool = False) -> dict:
        entered.append(int(document_id))
        first_inside.set()
        hold.wait(timeout=3.0)
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
        r1 = enqueue_process_document(501, force_thread=True)
        assert first_inside.wait(timeout=2.0)
        r2 = enqueue_process_document(501, force_thread=True)
        time.sleep(0.1)
        hold.set()
        deadline = time.time() + 2.0
        while time.time() < deadline and is_scanx_document_inflight(501):
            time.sleep(0.05)

    assert r1["mode"] in {"thread", "thread_forced"}
    assert r2["mode"] == "skipped_inflight"
    assert entered == [501]


def test_failure_on_document_a_does_not_stop_document_b() -> None:
    """A failure on document A does not stop document B."""
    results: dict[int, str] = {}
    order_lock = threading.Lock()
    both_done = threading.Barrier(3)  # A, B, main

    def fake_process(document_id: int, *, claimed: bool = False) -> dict:
        doc_id = int(document_id)
        try:
            if doc_id == 10:
                raise RuntimeError("simulated OCR crash on A")
            with order_lock:
                results[doc_id] = "ok"
            return {"ok": True, "document_id": doc_id}
        except Exception:
            with order_lock:
                results[doc_id] = "failed"
            raise
        finally:
            try:
                both_done.wait(timeout=3.0)
            except threading.BrokenBarrierError:
                pass

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
        queue_mod._start_thread(10)
        queue_mod._start_thread(11)
        try:
            both_done.wait(timeout=3.0)
        except threading.BrokenBarrierError:
            pass
        deadline = time.time() + 2.0
        while time.time() < deadline and (
            is_scanx_document_inflight(10) or is_scanx_document_inflight(11)
        ):
            time.sleep(0.05)

    assert results.get(10) == "failed"
    assert results.get(11) == "ok"
    assert is_scanx_document_inflight(10) is False
    assert is_scanx_document_inflight(11) is False


def test_failed_mid_scan_progress_write_does_not_call_ocr_again() -> None:
    """Tunnel/OperationalError on mid-scan progress must not re-enter OCR."""
    from app.services import scanx_jobs as jobs_mod

    ocr_calls = {"n": 0}

    def fake_ocr(*_a, **_kw):
        ocr_calls["n"] += 1
        return SimpleNamespace(
            text="PASSPORT SAMPLE",
            engine="rapid",
            note="ocr_ok",
            elapsed_ms=12,
            page_count=1,
            primary_engine="rapid",
            fallback_reason=None,
            blocks=[],
            marks=[],
            table_regions=[],
        )

    doc_id = 777
    metrics: dict = {"progress_steps": []}
    steps: list = []
    state, on_progress = jobs_mod._ocr_progress_updater(doc_id, metrics, steps)

    tunnel_err = OperationalError(
        "UPDATE",
        {},
        Exception("SSL connection has been closed unexpectedly"),
    )
    bad_session = MagicMock()
    bad_session.query.return_value.filter.return_value.first.side_effect = tunnel_err

    with (
        patch(
            "app.services.scanx_jobs.open_scanx_session",
            return_value=bad_session,
        ),
        patch("app.services.scanx_jobs.safe_close_session"),
        patch(
            "app.services.scanx_jobs.extract_text_from_image",
            side_effect=fake_ocr,
        ) as ocr_mock,
    ):
        # Mid-scan progress write fails — must be logged and ignored.
        on_progress("RapidOCR running… 15s")
        on_progress("RapidOCR running… 30s")
        # Simulate the job calling OCR once after progress blips.
        result = jobs_mod._call_extract_text_from_image(b"fake-image-bytes")
        assert result.note == "ocr_ok"
        assert ocr_calls["n"] == 1
        assert ocr_mock.call_count == 1

    # Progress updater kept in-memory state; never triggered a second OCR.
    assert state["tick"] >= 1
    assert ocr_calls["n"] == 1
