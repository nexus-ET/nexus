"""Compare ScanX OCR engines on a sample image (or synthetic PNG).

Usage (from backend/ with .venv active)::

    python scripts/verify_scanx_ocr_engines.py
    python scripts/verify_scanx_ocr_engines.py path/to/image.png

Prints engine tag, note, fallback_reason, and a short text preview for:
  - default config (SCANX_OCR_ENGINE, usually rapid → paddle fallback)
  - force_engine=paddle
  - force_engine=rapid
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# Allow `python scripts/...` from backend/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sample_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 140), "white")
    d = ImageDraw.Draw(img)
    d.text((24, 50), "HELLO SCANX OCR 12345", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _run(label: str, raw: bytes, *, force_engine: str | None = None) -> None:
    from app.services.scanx_ocr import (
        configured_ocr_engine,
        configured_ocr_fallback,
        extract_text_from_image,
    )

    print(f"\n=== {label} ===")
    if force_engine is None:
        print(
            f"config primary={configured_ocr_engine()} "
            f"fallback={configured_ocr_fallback()}"
        )
    result = extract_text_from_image(
        raw,
        timeout_seconds=60.0,
        force_engine=force_engine,
    )
    preview = (result.text or "").replace("\n", " | ")[:160]
    print(f"engine_used={result.engine}")
    print(f"primary_engine={result.primary_engine}")
    print(f"note={result.note}")
    print(f"fallback_reason={result.fallback_reason!r}")
    print(f"elapsed_ms={result.elapsed_ms}")
    print(f"text_preview={preview!r}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if path and path.is_file():
        raw = path.read_bytes()
        print(f"image={path} bytes={len(raw)}")
    else:
        raw = _sample_png()
        print(f"image=synthetic_png bytes={len(raw)}")

    # Import probe summary
    print("\n=== import probe ===")
    for mod in ("paddle", "paddleocr", "rapidocr"):
        try:
            __import__(mod)
            print(f"{mod}: OK")
        except Exception as exc:
            print(f"{mod}: FAIL {type(exc).__name__}: {exc}")

    _run("default (SCANX_OCR_ENGINE)", raw)
    _run("force paddle", raw, force_engine="paddle")
    _run("force rapid", raw, force_engine="rapid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
