"""ScanX: R2 archives originals only; rescan/reprocess reads original keys."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.scanx_jobs import _schedule_post_ocr_r2_archive
from app.services.scanx_storage import (
    collect_scanx_document_storage_keys,
    collect_scanx_original_archive_keys,
    is_enhanced_preview_key,
    schedule_archive_scanx_keys,
)


def test_is_enhanced_preview_key_detects_artifacts() -> None:
    assert is_enhanced_preview_key(
        "STUDENTS/1/PROFILE/abc__PASSPORT__x__enhanced_preview.jpg"
    )
    assert is_enhanced_preview_key(
        "STUDENTS/1/PROFILE/abc__PASSPORT__x__enhanced_preview_p2.jpg"
    )
    assert not is_enhanced_preview_key(
        "STUDENTS/1/PROFILE/abc__PASSPORT__x.pdf"
    )


def test_original_archive_keys_exclude_enhanced() -> None:
    doc = SimpleNamespace(
        r2_key="STUDENTS/1/PROFILE/abc__PASSPORT__x.pdf",
        source_pages=[
            {
                "page_index": 0,
                "r2_key": "STUDENTS/1/PROFILE/abc__page0.jpg",
            },
            {
                "page_index": 1,
                "r2_key": "STUDENTS/1/PROFILE/abc__page1.jpg",
            },
        ],
        metrics_json={
            "enhanced_preview_key": "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg",
            "enhanced_preview_keys": [
                "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg",
                "STUDENTS/1/PROFILE/abc__enhanced_preview_p1.jpg",
            ],
            "enhanced_preview_pages": [
                {
                    "page_index": 0,
                    "key": "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg",
                }
            ],
        },
    )
    archive = collect_scanx_original_archive_keys(doc)
    assert doc.r2_key in archive
    assert "STUDENTS/1/PROFILE/abc__page0.jpg" in archive
    assert "STUDENTS/1/PROFILE/abc__page1.jpg" in archive
    assert all(not is_enhanced_preview_key(k) for k in archive)

    # Cancel/delete may still clean leftover local enhanced files.
    cleanup = collect_scanx_document_storage_keys(doc)
    assert "STUDENTS/1/PROFILE/abc__enhanced_preview.jpg" in cleanup


def test_schedule_archive_skips_enhanced_preview_keys() -> None:
    original = "STUDENTS/9/MARKSHEETS/doc__MARKSHEET__scan.pdf"
    enhanced = "STUDENTS/9/MARKSHEETS/doc__enhanced_preview.jpg"
    with patch(
        "app.services.scanx_storage.archive_scanx_key_to_r2",
        return_value={"ok": True, "storage_key": original},
    ) as archive_fn:
        with patch("threading.Thread") as thread_cls:
            started: list = []

            def _capture(*, target=None, **_kwargs):
                mock = MagicMock()
                mock.start = lambda: started.append(target) or (target and target())
                return mock

            thread_cls.side_effect = _capture
            schedule_archive_scanx_keys([original, enhanced, enhanced])

    assert len(started) == 1
    assert archive_fn.call_count == 1
    assert archive_fn.call_args[0][0] == original


def test_post_ocr_archive_schedules_originals_only() -> None:
    doc = SimpleNamespace(
        id=55,
        r2_key="STUDENTS/2/PROFILE/pass__PASSPORT__p.pdf",
        content_type="application/pdf",
        original_filename="passport.pdf",
        source_pages=None,
        metrics_json={
            "enhanced_preview_key": "STUDENTS/2/PROFILE/pass__enhanced_preview.jpg",
            "enhanced_preview_keys": [
                "STUDENTS/2/PROFILE/pass__enhanced_preview.jpg",
            ],
        },
    )
    metrics = dict(doc.metrics_json)

    with patch(
        "app.services.scanx_jobs.schedule_archive_scanx_keys"
    ) as schedule_fn:
        with patch(
            "app.services.scanx_jobs.delete_scanx_objects",
            return_value=1,
        ) as delete_fn:
            _schedule_post_ocr_r2_archive(doc, metrics)

    schedule_fn.assert_called_once()
    scheduled_keys = schedule_fn.call_args[0][0]
    assert scheduled_keys == [doc.r2_key]
    assert all(not is_enhanced_preview_key(k) for k in scheduled_keys)
    delete_fn.assert_called_once()
    assert "STUDENTS/2/PROFILE/pass__enhanced_preview.jpg" in delete_fn.call_args[0][0]
    assert "enhanced_preview_key" not in metrics
    assert metrics.get("r2_archive_originals_only") is True


def test_reprocess_input_is_original_r2_key() -> None:
    """Worker fetch + multi-page load use original keys, never enhanced previews."""
    from app.services.scanx_jobs import _load_source_page_images, _source_pages_meta

    doc = SimpleNamespace(
        id=88,
        r2_key="STUDENTS/3/PROFILE/grp__PASSPORT__p0.jpg",
        source_pages=[
            {
                "page_index": 0,
                "r2_key": "STUDENTS/3/PROFILE/grp__PASSPORT__p0.jpg",
            },
            {
                "page_index": 1,
                "r2_key": "STUDENTS/3/PROFILE/grp__PASSPORT__p1.jpg",
            },
        ],
        metrics_json={
            "enhanced_preview_key": "STUDENTS/3/PROFILE/grp__enhanced_preview.jpg",
        },
    )
    pages = _source_pages_meta(doc)
    assert all(not is_enhanced_preview_key(p["r2_key"]) for p in pages)

    fetched: list[str] = []

    def _fake_fetch(key: str):
        fetched.append(key)
        return b"orig-bytes", "image/jpeg"

    with patch("app.services.scanx_jobs.fetch_scanx_bytes", side_effect=_fake_fetch):
        images = _load_source_page_images(doc)

    assert len(images) == 2
    assert fetched == [
        "STUDENTS/3/PROFILE/grp__PASSPORT__p0.jpg",
        "STUDENTS/3/PROFILE/grp__PASSPORT__p1.jpg",
    ]
    assert doc.r2_key == fetched[0]
    assert all(not is_enhanced_preview_key(k) for k in fetched)
