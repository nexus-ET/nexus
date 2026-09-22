"""ScanX cancel: cooperative abort + hard-delete (no exact OCR resume)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.scanx_cancel import (
    ScanxJobCancelled,
    cancel_scanx_document,
    clear_cancel,
    is_cancel_requested,
    raise_if_cancelled,
    request_cancel,
)
from app.services.scanx_storage import collect_scanx_document_storage_keys


def test_cancel_flag_stops_fake_job() -> None:
    doc_id = 4242
    request_cancel(doc_id)
    steps = 0
    try:
        for _ in range(10):
            raise_if_cancelled(doc_id)
            steps += 1
        raise AssertionError("cancel flag should have stopped the loop")
    except ScanxJobCancelled:
        pass
    finally:
        clear_cancel(doc_id)
    assert steps == 0
    assert is_cancel_requested(doc_id) is False


def test_cancel_missing_id_is_safe() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    result = cancel_scanx_document(db, 999001)
    assert result.ok is True
    assert result.cancelled is True
    assert result.already_gone is True
    db.delete.assert_not_called()


def test_cancel_deletes_file_and_row() -> None:
    doc = SimpleNamespace(
        id=17,
        status="parsing",
        r2_key="STUDENTS/1/PROFILE/abc__PASSPORT__x.pdf",
        metrics_json={
            "job_id": "thread-17",
            "enhanced_preview_key": "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg",
        },
        source_pages=[
            {
                "page_index": 0,
                "r2_key": "STUDENTS/1/PROFILE/abc__page0.jpg",
            }
        ],
        document_group_id=None,
    )
    keys = collect_scanx_document_storage_keys(doc)
    assert doc.r2_key in keys
    assert "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg" in keys
    assert "STUDENTS/1/PROFILE/abc__page0.jpg" in keys

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.first.return_value = doc
    query.filter.return_value.all.return_value = [doc]

    with patch(
        "app.services.scanx_storage.delete_scanx_objects",
        return_value=3,
    ) as deleter:
        with patch("app.services.scanx_queue.cancel_scanx_rq_job") as rq_cancel:
            result = cancel_scanx_document(db, 17)

    assert result.ok is True
    assert result.cancelled is True
    assert result.already_gone is False
    assert result.storage_removed is True
    db.delete.assert_called()
    deleter.assert_called_once()
    deleted_keys = deleter.call_args[0][0]
    assert doc.r2_key in deleted_keys
    assert "STUDENTS/1/PROFILE/abc__page0.jpg" in deleted_keys
    rq_cancel.assert_not_called()
