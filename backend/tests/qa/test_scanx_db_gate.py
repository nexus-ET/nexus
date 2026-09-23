"""ScanX must wait on the SSH connect gate after enhance/classify, not fail-fast."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

from app.db.database import (
    connect_gate_timeout_sec,
    is_db_pool_pressure_error,
    is_db_tunnel_transient_error,
    should_dispose_pool_for_error,
)
from app.services.scanx_jobs import (
    _is_db_connectivity_error,
    _persist_progress,
    _reopen_job_db,
)


def test_connect_gate_timeout_api_stays_fail_fast() -> None:
    from app.db import database as dbmod

    dbmod._scanx_long_connect_gate.active = False
    assert connect_gate_timeout_sec() == 12.0


def test_connect_gate_timeout_scanx_job_waits() -> None:
    from app.db import database as dbmod

    dbmod._scanx_long_connect_gate.active = True
    try:
        assert connect_gate_timeout_sec() == 120.0
    finally:
        dbmod._scanx_long_connect_gate.active = False


def test_gate_busy_is_pool_pressure_not_dispose() -> None:
    err = TimeoutError("tunnel connect gate busy")
    assert is_db_pool_pressure_error(err) is True
    assert should_dispose_pool_for_error(err) is False
    assert _is_db_connectivity_error(err) is True


def test_admin_shutdown_is_retryable_transient() -> None:
    err = OperationalError(
        "UPDATE",
        {},
        Exception("terminating connection due to administrator command"),
    )
    assert _is_db_connectivity_error(err) is True
    assert is_db_tunnel_transient_error(err) is True


def test_should_not_dispose_pool_when_tunnel_port_listening() -> None:
    """Port listening + Postgres warming must not wipe the SQLAlchemy pool."""
    err = OperationalError(
        "SELECT 1",
        {},
        Exception("connection timeout"),
    )
    with (
        patch("app.db.database._IS_SSH_TUNNEL_DB", True),
        patch("app.db.database.probe_ssh_tunnel_tcp", return_value="up") as probe,
    ):
        assert is_db_tunnel_transient_error(err) is True
        assert should_dispose_pool_for_error(err) is False
    probe.assert_called()


def test_should_not_dispose_pool_when_tunnel_tcp_warming() -> None:
    err = OperationalError(
        "SELECT 1",
        {},
        Exception("timeout expired"),
    )
    with (
        patch("app.db.database._IS_SSH_TUNNEL_DB", True),
        patch("app.db.database.probe_ssh_tunnel_tcp", return_value="warming"),
    ):
        assert should_dispose_pool_for_error(err) is False


def test_should_dispose_pool_when_tunnel_port_closed() -> None:
    err = OperationalError(
        "SELECT 1",
        {},
        Exception("connection refused"),
    )
    with (
        patch("app.db.database._IS_SSH_TUNNEL_DB", True),
        patch("app.db.database.probe_ssh_tunnel_tcp", return_value="closed"),
    ):
        assert should_dispose_pool_for_error(err) is True


def test_bulk_delete_retries_on_transient_tunnel_error() -> None:
    """bulk-delete must reopen the session instead of 503 on the first warm-up miss."""
    from fastapi import BackgroundTasks

    from app.routers.scanx import (
        ScanxBulkDeleteRequest,
        ScanxBulkDeleteResponse,
        bulk_delete_scanx_documents,
    )

    timeout = OperationalError(
        "DELETE",
        {},
        Exception("connection timeout"),
    )
    ok = ScanxBulkDeleteResponse(deleted=2, skipped=0, ids=[1, 2], storage_removed=0)
    bg = BackgroundTasks()

    with (
        patch("app.routers.scanx.time.sleep"),
        patch("app.db.database.SessionLocal", return_value=MagicMock()),
        patch(
            "app.routers.scanx._hard_delete_scanx_documents",
            side_effect=[timeout, ok],
        ) as hard_delete,
        patch("app.db.database.safe_close_session"),
        patch("app.db.database.dispose_db_pool") as dispose,
        patch("app.db.database.should_dispose_pool_for_error", return_value=False),
        patch("app.services.audit_service.write_audit_log"),
    ):
        result = bulk_delete_scanx_documents(
            ScanxBulkDeleteRequest(ids=[1, 2]),
            bg,
        )

    assert result.deleted == 2
    assert hard_delete.call_count == 2
    dispose.assert_not_called()


def test_reopen_job_db_retries_when_open_session_hits_gate() -> None:
    busy = TimeoutError("tunnel connect gate busy")
    db = MagicMock()
    doc = SimpleNamespace(id=7)
    db.query.return_value.filter.return_value.first.return_value = doc

    with (
        patch("app.services.scanx_jobs.time.sleep"),
        patch(
            "app.services.scanx_jobs.open_scanx_session",
            side_effect=[busy, db],
        ) as opener,
        patch("app.services.scanx_jobs.ensure_db_connection"),
    ):
        got_db, got_doc = _reopen_job_db(7)

    assert opener.call_count == 2
    assert got_db is db
    assert got_doc is doc


def test_persist_progress_retries_then_soft_fails_without_dispose() -> None:
    """AdminShutdown on metrics UPDATE must not fail the document or wipe the pool."""
    shutdown = OperationalError(
        "UPDATE scanx_documents SET metrics_json",
        {},
        Exception("terminating connection due to administrator command"),
    )
    db = MagicMock()
    db.commit.side_effect = shutdown
    doc = SimpleNamespace(id=42, metrics_json={})
    steps = [
        {
            "id": "classify",
            "label": "Classify",
            "status": "complete",
            "weight": 1,
        }
    ]

    with (
        patch("app.services.scanx_jobs.time.sleep"),
        patch("app.services.scanx_jobs.raise_if_cancelled"),
        patch(
            "app.services.scanx_jobs.open_scanx_session",
            side_effect=shutdown,
        ) as opener,
        patch("app.services.scanx_jobs.dispose_db_pool") as dispose,
        patch("app.services.scanx_jobs._emit_status"),
    ):
        out = _persist_progress(db, doc, {"fetch_ms": 10}, steps, emit=False)

    assert isinstance(out, dict)
    assert "progress_steps" in out
    assert opener.call_count >= 1
    dispose.assert_not_called()


def test_persist_progress_recovers_via_fresh_session() -> None:
    shutdown = OperationalError(
        "UPDATE",
        {},
        Exception("terminating connection due to administrator command"),
    )
    db = MagicMock()
    db.commit.side_effect = shutdown
    passport_fields = {"version": 1, "passport": {"surname": "REGURI"}}
    doc = SimpleNamespace(
        id=9,
        metrics_json={},
        extracted_fields_json=passport_fields,
        __dict__={
            "id": 9,
            "metrics_json": {},
            "extracted_fields_json": passport_fields,
        },
    )
    steps = [{"id": "enhance", "label": "Enhance", "status": "complete", "weight": 1}]

    side = MagicMock()
    rebound = SimpleNamespace(id=9, metrics_json={"ok": True})
    side.query.return_value.filter.return_value.first.return_value = rebound

    with (
        patch("app.services.scanx_jobs.time.sleep"),
        patch("app.services.scanx_jobs.raise_if_cancelled"),
        patch("app.services.scanx_jobs.open_scanx_session", return_value=side),
        patch("app.services.scanx_jobs.safe_close_session") as closer,
        patch("app.services.scanx_jobs.dispose_db_pool") as dispose,
        patch("app.services.scanx_jobs._emit_status") as emit,
    ):
        out = _persist_progress(db, doc, {}, steps, emit=True)

    assert out.get("progress_percent") is not None
    side.commit.assert_called()
    assert rebound.extracted_fields_json == passport_fields
    closer.assert_called_with(side)
    emit.assert_called()
    dispose.assert_not_called()


def test_document_looks_like_passport_from_ocr_heuristics() -> None:
    from app.services.scanx_jobs import document_looks_like_passport

    assert document_looks_like_passport(
        document_type_id="UNKNOWN",
        original_filename="scan.pdf",
        extracted_text="REPUBLIC OF INDIA\nPassport No.\nU9663905\nSurname\nANNADURAI",
    )
    assert not document_looks_like_passport(
        document_type_id="TR_TRANSCRIPT",
        original_filename="marks.pdf",
        extracted_text="Subject Theory Practical Total",
    )