"""ScanX OCR slot-wait timeout: one retry, no invented passport type on empty."""

from __future__ import annotations

from unittest.mock import patch

from app.services.scanx_ocr import extract_text_from_image
from app.services.scanx_passport import extract_passport_fields


def test_ocr_slot_wait_timeout_retries_once_then_ok() -> None:
    calls: list[str] = []

    def fake_try(engine_name, frames, *, timeout_seconds, on_progress=None):
        calls.append(engine_name)
        if len(calls) == 1:
            return None, "ocr_timeout", "ocr_slot_wait_timeout", []
        return "PASSPORT OCR TEXT", "ocr_ok", None, []

    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with (
        patch("app.services.scanx_ocr._pil_frames", return_value=[b"frame"]),
        patch("app.services.scanx_ocr._try_engine", side_effect=fake_try),
        patch(
            "app.services.scanx_ocr._finalize_ocr_blocks",
            return_value=("PASSPORT OCR TEXT", [], [], []),
        ),
        patch("app.services.scanx_ocr.configured_ocr_fallback", return_value=None),
    ):
        result = extract_text_from_image(tiny_png, timeout_seconds=30.0)

    assert result.note == "ocr_ok"
    assert result.text == "PASSPORT OCR TEXT"
    assert len(calls) == 2
    assert "ocr_slot_wait_timeout_retry" in str(result.fallback_reason or "")


def test_ocr_slot_wait_timeout_retries_once_only() -> None:
    calls = {"n": 0}

    def always_slot_timeout(engine_name, frames, *, timeout_seconds, on_progress=None):
        calls["n"] += 1
        return None, "ocr_timeout", "ocr_slot_wait_timeout", []

    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with (
        patch("app.services.scanx_ocr._pil_frames", return_value=[b"frame"]),
        patch("app.services.scanx_ocr._try_engine", side_effect=always_slot_timeout),
        patch("app.services.scanx_ocr.configured_ocr_fallback", return_value=None),
    ):
        result = extract_text_from_image(tiny_png, timeout_seconds=30.0)

    assert result.note == "ocr_timeout"
    assert result.text is None
    # Outer attempt + one retry (no fallback engine) => 2 _try_engine calls.
    assert calls["n"] == 2
    assert "ocr_slot_wait_timeout" in str(result.fallback_reason or "")


def test_empty_passport_extract_leaves_document_type_blank() -> None:
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value={},
    ):
        fields = extract_passport_fields("")
    assert fields.get("document_type") in (None, "")
    for key in ("document_number", "surname", "given_names", "mrz_string", "sex"):
        assert fields.get(key) in (None, "")
