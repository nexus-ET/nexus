"""Classify ScanX uploads as born-digital vs scanned / raster.

Runs before OpenCV enhancement and OCR so text-rich native PDFs/DOCX skip
heavy image transforms, while scans take the enhance → RapidOCR path.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.constants.scanx import DOCX_MIME_TYPE

logger = logging.getLogger(__name__)

DocKind = Literal["born_digital", "scanned"]

# Native text thresholds (chars after strip). Sparse text on a multi-page PDF
# usually means image-only pages with a header/footer leftover.
_BORN_DIGITAL_MIN_CHARS = 80
_BORN_DIGITAL_CHARS_PER_PAGE = 40
_SPARSE_NATIVE_CHARS = 40


@dataclass
class DocumentClassification:
    doc_kind: DocKind
    reason: str
    confidence: float
    native_char_count: int = 0
    page_count: int | None = None
    image_page_ratio: float | None = None
    edge_density: float | None = None
    # Scanned path but OpenCV enhance can be skipped (clean digital screenshot).
    skip_enhance: bool = False
    classify_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_metrics(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "doc_kind": self.doc_kind,
            "doc_kind_reason": self.reason,
            "doc_kind_confidence": round(float(self.confidence), 3),
            "classify_ms": int(self.classify_ms),
            "native_char_count": int(self.native_char_count),
        }
        if self.page_count is not None:
            out["classify_page_count"] = int(self.page_count)
        if self.image_page_ratio is not None:
            out["image_page_ratio"] = round(float(self.image_page_ratio), 3)
        if self.edge_density is not None:
            out["edge_density"] = round(float(self.edge_density), 4)
        if self.skip_enhance:
            out["enhance_skip_reason"] = "already_clean"
        if self.details:
            out["classify_details"] = self.details
        return out


def _norm_ctype(content_type: str | None, filename: str | None) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    if ctype.startswith("application/pdf") or name.endswith(".pdf"):
        return "application/pdf"
    if ctype == DOCX_MIME_TYPE or name.endswith(".docx"):
        return DOCX_MIME_TYPE
    if ctype.startswith("image/") or name.endswith(
        (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")
    ):
        return ctype if ctype.startswith("image/") else "image/unknown"
    return ctype or "application/octet-stream"


def _alnum_ratio(text: str) -> float:
    if not text:
        return 0.0
    alnum = sum(1 for c in text if c.isalnum())
    return alnum / max(1, len(text))


def _pdf_native_stats(content: bytes) -> tuple[int | None, int, float]:
    """Return (page_count, char_count, image_page_ratio) via lightweight probes."""
    from app.services.scanx_validation import looks_like_pdf

    if not content or not looks_like_pdf(content):
        return None, 0, 1.0

    pages: int | None = None
    chars = 0
    image_pages = 0

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=False)
        if getattr(reader, "is_encrypted", False):
            decrypt = getattr(reader, "decrypt", None)
            if callable(decrypt):
                try:
                    decrypt("")
                except Exception:
                    pass
        pages = len(reader.pages)
        texts: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            texts.append(t)
            # Heuristic: page with almost no text but resources → likely image page.
            try:
                resources = page.get("/Resources") or {}
                xobj = resources.get("/XObject") if hasattr(resources, "get") else None
                has_image = False
                if xobj is not None:
                    try:
                        for _name, ref in xobj.items():
                            try:
                                obj = ref.get_object() if hasattr(ref, "get_object") else ref
                                subtype = obj.get("/Subtype") if hasattr(obj, "get") else None
                                if str(subtype) in {"/Image", "Image"}:
                                    has_image = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass
                if has_image and len(t.strip()) < _SPARSE_NATIVE_CHARS:
                    image_pages += 1
            except Exception:
                pass
        joined = "\n".join(texts)
        chars = len(joined.strip())
    except Exception:
        logger.debug("ScanX classify PDF pypdf probe failed", exc_info=True)
        try:
            from app.services.scanx_validation import inspect_pdf

            pages, text = inspect_pdf(content)
            chars = len((text or "").strip())
        except Exception:
            return pages, 0, 1.0

    page_n = max(1, int(pages or 1))
    ratio = float(image_pages) / float(page_n)
    return pages, chars, ratio


def _docx_native_chars(content: bytes) -> int:
    try:
        from app.services.scanx_validation import extract_docx_text, looks_like_docx

        if not looks_like_docx(content):
            return 0
        text, _subjects = extract_docx_text(content)
        return len((text or "").strip())
    except Exception:
        logger.debug("ScanX classify DOCX probe failed", exc_info=True)
        return 0


def _docx_embedded_image_count(content: bytes) -> int:
    try:
        from app.services.scanx_validation import extract_docx_embedded_images

        return len(extract_docx_embedded_images(content))
    except Exception:
        return 0


def _opencv_edge_density(image_bytes: bytes) -> float | None:
    """Laplacian variance / edge density for borderline decisions."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        # Downscale for speed.
        h, w = bgr.shape[:2]
        scale = min(1.0, 800.0 / max(h, w))
        if scale < 0.99:
            bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        edges = cv2.Canny(gray, 80, 160)
        density = float(np.count_nonzero(edges)) / float(edges.size)
        # Blend into a single score used by callers (laplacian-ish).
        return lap * (0.5 + density)
    except Exception:
        logger.debug("ScanX classify OpenCV probe failed", exc_info=True)
        return None


def _image_looks_clean_digital(image_bytes: bytes) -> tuple[bool, dict[str, Any]]:
    """Optional: high-contrast screenshot / clean raster → skip enhance."""
    details: dict[str, Any] = {}
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False, details
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return False, details
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        details["w"] = int(w)
        details["h"] = int(h)
        # Contrast: std of pixels.
        std = float(np.std(gray))
        details["gray_std"] = round(std, 2)
        lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        details["laplacian_var"] = round(lap, 2)
        # Skew proxy: if minAreaRect angle is near 0 and contrast is high, likely
        # a clean digital capture (not a phone photo of paper).
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        angle = 0.0
        if len(coords) > 200:
            rect = cv2.minAreaRect(coords.astype(np.float32))
            angle = float(rect[-1])
            if angle < -45:
                angle = 90.0 + angle
        details["skew_angle"] = round(angle, 2)
        clean = std >= 55.0 and lap >= 120.0 and abs(angle) < 1.5 and min(h, w) >= 600
        return clean, details
    except Exception:
        return False, details


def classify_scanx_document(
    content: bytes,
    *,
    content_type: str | None = None,
    filename: str | None = None,
    sample_image: bytes | None = None,
) -> DocumentClassification:
    """Classify bytes as born_digital or scanned.

    ``sample_image`` optional PNG/JPEG used for OpenCV edge checks on PDFs.
    """
    t0 = time.perf_counter()
    kind_ctype = _norm_ctype(content_type, filename)

    # --- Images: always scanned + enhance (parity with PDF/DOCX image OCR) ---
    # Skipping enhance for "clean digital" JPGs made RapidOCR diverge from the
    # same mark-sheet saved as PDF/DOCX (those always ran OpenCV mild enhance).
    if kind_ctype.startswith("image/"):
        clean, details = _image_looks_clean_digital(content)
        edge = _opencv_edge_density(content)
        ms = int((time.perf_counter() - t0) * 1000)
        details = dict(details or {})
        details["clean_digital_probe"] = bool(clean)
        return DocumentClassification(
            doc_kind="scanned",
            reason="image_upload" if not clean else "image_clean_digital",
            confidence=0.95 if not clean else 0.75,
            native_char_count=0,
            page_count=1,
            edge_density=edge,
            skip_enhance=False,
            classify_ms=ms,
            details=details,
        )

    # --- DOCX ---
    if kind_ctype == DOCX_MIME_TYPE:
        chars = _docx_native_chars(content)
        img_count = _docx_embedded_image_count(content)
        ms = int((time.perf_counter() - t0) * 1000)
        if chars >= _BORN_DIGITAL_MIN_CHARS:
            return DocumentClassification(
                doc_kind="born_digital",
                reason="docx_extractable_text",
                confidence=0.95,
                native_char_count=chars,
                classify_ms=ms,
                details={"embedded_images": img_count},
            )
        if img_count > 0 and chars < _SPARSE_NATIVE_CHARS:
            return DocumentClassification(
                doc_kind="scanned",
                reason="docx_image_only",
                confidence=0.9,
                native_char_count=chars,
                image_page_ratio=1.0,
                classify_ms=ms,
                details={"embedded_images": img_count},
            )
        # Empty body, no images — still treat as born-digital empty (no enhance).
        return DocumentClassification(
            doc_kind="born_digital",
            reason="docx_empty_or_sparse",
            confidence=0.6,
            native_char_count=chars,
            classify_ms=ms,
            details={"embedded_images": img_count},
        )

    # --- PDF (default for octet-stream that looks like PDF handled by caller) ---
    from app.services.scanx_validation import looks_like_pdf

    if kind_ctype.startswith("application/pdf") or looks_like_pdf(content):
        pages, chars, img_ratio = _pdf_native_stats(content)
        page_n = max(1, int(pages or 1))
        chars_per_page = chars / float(page_n)
        alnum = 0.5 if chars > 0 else 0.0
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content), strict=False)
            snippet_parts: list[str] = []
            for page in reader.pages[: min(3, len(reader.pages))]:
                try:
                    snippet_parts.append(page.extract_text() or "")
                except Exception:
                    pass
            snippet = "\n".join(snippet_parts)
            if snippet.strip():
                alnum = _alnum_ratio(snippet)
        except Exception:
            pass

        edge = None
        if sample_image:
            edge = _opencv_edge_density(sample_image)

        ms = int((time.perf_counter() - t0) * 1000)
        details = {
            "chars_per_page": round(chars_per_page, 1),
            "alnum_ratio": round(alnum, 3),
            "image_page_ratio": round(img_ratio, 3),
        }

        # Strong born-digital: substantial selectable text, low image-only ratio.
        if (
            chars >= _BORN_DIGITAL_MIN_CHARS
            and chars_per_page >= _BORN_DIGITAL_CHARS_PER_PAGE
            and img_ratio < 0.6
            and alnum >= 0.35
        ):
            return DocumentClassification(
                doc_kind="born_digital",
                reason="pdf_selectable_text",
                confidence=0.92,
                native_char_count=chars,
                page_count=pages,
                image_page_ratio=img_ratio,
                edge_density=edge,
                classify_ms=ms,
                details=details,
            )

        # Strong scanned: empty / sparse text or mostly image pages.
        if chars < _SPARSE_NATIVE_CHARS or img_ratio >= 0.7:
            return DocumentClassification(
                doc_kind="scanned",
                reason="pdf_image_or_empty_text",
                confidence=0.9 if chars < _SPARSE_NATIVE_CHARS else 0.85,
                native_char_count=chars,
                page_count=pages,
                image_page_ratio=img_ratio,
                edge_density=edge,
                classify_ms=ms,
                details=details,
            )

        # Borderline: use edge density if available; else lean scanned when sparse.
        if edge is not None and edge < 40.0 and chars < 200:
            return DocumentClassification(
                doc_kind="scanned",
                reason="pdf_borderline_low_edge",
                confidence=0.65,
                native_char_count=chars,
                page_count=pages,
                image_page_ratio=img_ratio,
                edge_density=edge,
                classify_ms=ms,
                details=details,
            )
        if chars >= _BORN_DIGITAL_MIN_CHARS and img_ratio < 0.5:
            return DocumentClassification(
                doc_kind="born_digital",
                reason="pdf_borderline_text_ok",
                confidence=0.7,
                native_char_count=chars,
                page_count=pages,
                image_page_ratio=img_ratio,
                edge_density=edge,
                classify_ms=ms,
                details=details,
            )
        return DocumentClassification(
            doc_kind="scanned",
            reason="pdf_borderline_assume_scan",
            confidence=0.6,
            native_char_count=chars,
            page_count=pages,
            image_page_ratio=img_ratio,
            edge_density=edge,
            classify_ms=ms,
            details=details,
        )

    # Unknown type — treat as scanned so enhance/OCR can still try.
    ms = int((time.perf_counter() - t0) * 1000)
    return DocumentClassification(
        doc_kind="scanned",
        reason="unknown_type",
        confidence=0.4,
        classify_ms=ms,
    )
