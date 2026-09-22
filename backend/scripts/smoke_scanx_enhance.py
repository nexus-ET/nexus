"""Smoke-test ScanX OpenCV enhance + document classify (no DB / OCR).

Usage (from backend/ with venv active):
  python scripts/smoke_scanx_enhance.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/...` from backend/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_skewed_noisy_png() -> bytes:
    import cv2
    import numpy as np

    # Synthetic "page": white bg, dark text bars, then rotate + noise.
    h, w = 400, 300
    img = np.full((h, w), 240, dtype=np.uint8)
    cv2.putText(
        img,
        "ScanX TEST",
        (40, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        20,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        "Grade: A+",
        (40, 180),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        30,
        2,
        cv2.LINE_AA,
    )
    # Soft shadow gradient
    for y in range(h):
        img[y, :] = np.clip(img[y, :].astype(np.int16) - int(y * 0.15), 0, 255).astype(
            np.uint8
        )
    # Noise
    noise = np.random.randint(0, 40, (h, w), dtype=np.uint8)
    img = cv2.subtract(img, noise)
    # Skew ~8 degrees
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, 8.0, 1.0)
    skewed = cv2.warpAffine(img, M, (w, h), borderValue=200)
    bgr = cv2.cvtColor(skewed, cv2.COLOR_GRAY2BGR)
    ok, buf = cv2.imencode(".png", bgr)
    assert ok
    return bytes(buf.tobytes())


def main() -> int:
    from app.services.scanx_document_classify import classify_scanx_document
    from app.services.scanx_image_enhance import enhance_image_bytes

    raw = _make_skewed_noisy_png()
    clf = classify_scanx_document(
        raw, content_type="image/png", filename="scan_test.png"
    )
    print("classify:", clf.doc_kind, clf.reason, f"skip_enhance={clf.skip_enhance}")
    assert clf.doc_kind == "scanned", clf

    result = enhance_image_bytes(raw)
    print(
        "enhance:",
        f"applied={result.applied}",
        f"scale={result.scale}",
        f"dpi={result.dpi_before}->{result.dpi_after}",
        f"dpi_source={result.dpi_source}",
        f"angle={result.deskew_angle:.2f}",
        f"size={result.width}x{result.height}",
        f"ms={result.elapsed_ms}",
        f"steps={result.steps}",
        f"error={result.error}",
    )
    assert result.applied, result
    assert result.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.width > 0 and result.height > 0
    assert result.dpi_before and result.dpi_before > 0
    assert result.dpi_after and result.dpi_after >= result.dpi_before
    m = result.to_metrics()
    assert m.get("dpi_before") == int(round(result.dpi_before))
    assert m.get("dpi_after") == int(round(result.dpi_after))
    print("metrics dpi:", m.get("dpi_before"), "->", m.get("dpi_after"), m.get("dpi_scale_factor"))

    # Born-digital-ish: tiny clean high-contrast "screenshot"
    import cv2
    import numpy as np

    clean = np.full((800, 600), 255, dtype=np.uint8)
    cv2.putText(clean, "DIGITAL", (80, 400), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 3)
    ok, buf = cv2.imencode(".png", clean)
    assert ok
    clf2 = classify_scanx_document(
        bytes(buf.tobytes()), content_type="image/png", filename="shot.png"
    )
    print(
        "clean image classify:",
        clf2.doc_kind,
        clf2.reason,
        f"skip_enhance={clf2.skip_enhance}",
    )

    # Empty PDF-like bytes should not crash classify
    clf3 = classify_scanx_document(
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
        content_type="application/pdf",
        filename="empty.pdf",
    )
    print("empty pdf classify:", clf3.doc_kind, clf3.reason)
    assert clf3.doc_kind in {"scanned", "born_digital"}

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
