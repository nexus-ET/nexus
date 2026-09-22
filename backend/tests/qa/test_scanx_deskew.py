"""ScanX deskew_image — synthetic tilt, no RapidOCR models required."""

from __future__ import annotations

import io

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")


def _tilted_bar_image(*, angle_deg: float = 5.0, size: int = 400) -> np.ndarray:
    """White page with a dark horizontal bar, rotated by ``angle_deg``."""
    canvas = np.full((size, size), 255, dtype=np.uint8)
    mid = size // 2
    canvas[mid - 8 : mid + 8, 40 : size - 40] = 0
    matrix = cv2.getRotationMatrix2D((size / 2.0, size / 2.0), angle_deg, 1.0)
    return cv2.warpAffine(
        canvas,
        matrix,
        (size, size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def test_deskew_image_corrects_minor_tilt():
    from app.services.scanx_image_enhance import deskew_image, estimate_skew_angle

    tilted = _tilted_bar_image(angle_deg=6.0)
    estimated = estimate_skew_angle(tilted)
    assert abs(estimated) >= 0.35
    assert abs(estimated) <= 15.0

    deskewed, applied = deskew_image(tilted)
    assert deskewed is not None
    # Canvas expands so rotation does not clip edges.
    assert deskewed.shape[0] >= tilted.shape[0]
    assert deskewed.shape[1] >= tilted.shape[1]
    assert abs(applied) >= 0.35
    # Applied angle should track the estimated tilt (within a few degrees).
    assert abs(abs(applied) - abs(estimated)) < 3.0
    # Warp must change pixels (not a no-op passthrough).
    assert deskewed.shape != tilted.shape or not np.array_equal(deskewed, tilted)


def test_deskew_image_skips_near_zero():
    from app.services.scanx_image_enhance import deskew_image

    straight = np.full((300, 300), 255, dtype=np.uint8)
    straight[140:160, 30:270] = 0
    out, angle = deskew_image(straight)
    assert angle == 0.0
    assert np.array_equal(out, straight)


def test_deskew_skips_when_estimate_near_zero(monkeypatch):
    """When Hough/rect cross-check returns 0°, deskew must not warp (no clipping)."""
    from app.services import scanx_image_enhance as enh

    straight = np.full((300, 300), 255, dtype=np.uint8)
    straight[140:160, 30:270] = 0
    monkeypatch.setattr(enh, "estimate_skew_angle", lambda _img: 0.0)
    out, angle = enh.deskew_image(straight)
    assert angle == 0.0
    assert np.array_equal(out, straight)


def test_deskew_image_accepts_bgr():
    from app.services.scanx_image_enhance import deskew_image

    gray = _tilted_bar_image(angle_deg=4.0)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    out, angle = deskew_image(bgr)
    assert len(out.shape) == 2
    assert abs(angle) >= 0.35 or angle == 0.0  # Hough may miss tiny synthetic bars


def test_render_pdf_pages_in_memory_no_disk_artifact(tmp_path, monkeypatch):
    """Multi-page PDF OCR path must not write enhanced PDF files to disk."""
    from app.services.scanx_validation import render_pdf_pages_as_png
    from pypdf import PdfWriter

    monkeypatch.chdir(tmp_path)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    before = {p.name for p in tmp_path.iterdir()}
    pages = render_pdf_pages_as_png(pdf_bytes, scale=1.0)
    after = {p.name for p in tmp_path.iterdir()}

    assert after == before, f"Unexpected disk artifacts: {after - before}"
    # pypdfium2 may return empty on blank pages in some builds; either way no files.
    assert isinstance(pages, list)
    for frame in pages:
        assert isinstance(frame, (bytes, bytearray))
        assert frame[:8] == b"\x89PNG\r\n\x1a\n"
