"""OpenCV pre-OCR enhancement for scanned / raster ScanX pages.

Pipeline (OCR-mild, sequential):
  1. BGR → grayscale
  2. Cubic upscale toward ≥300 DPI equivalent
  3. deskew_image() — MinAreaRect / Hough, minor tilt only
  4. CLAHE + background-division shadow reduction
  5. Denoise (NLM, median fallback on huge frames)
  6. Light unsharp (on continuous gray — no hard binarize)
  7. White border padding

Hard adaptive/Otsu binarization + morphology were removed from the OCR path:
on already-clean mark-sheet scans they collapse antialiased strokes to 2-tone
topology Rapid already handles, and can slightly worsen Latin tokens while
Rapid's Det.limit_side_len already renormalizes page size.

Returns PNG bytes suitable for RapidOCR / PaddleOCR.
Records ``dpi_before`` / ``dpi_after`` (effective DPI from EXIF/pHYs or
page-size estimate × scale) and ``dpi_metadata`` (value written into PNG pHYs /
JPEG density so Windows Properties matches ~300).
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Cap after upscale so NLM / OCR stay within RAM budgets.
_MAX_SIDE_PX = 4200
_TARGET_DPI = 300
_ASSUMED_SOURCE_DPI = 150  # phone/scanner guess when metadata missing
_MIN_UPSCALE = 2.0
_PAD_PX = 16

# Standard page sizes (inches) for DPI-from-pixels when metadata is absent.
_PAGE_SIZES_IN: tuple[tuple[str, float, float], ...] = (
    ("letter", 8.5, 11.0),
    ("a4", 8.27, 11.69),
)

# Sources that are pixel÷page guesses (not EXIF/pHYs).
_ESTIMATED_DPI_SOURCES = frozenset(
    {"page_letter", "page_a4", "assumed", "unknown"}
)


@dataclass
class DpiEstimate:
    dpi: float | None
    source: str  # exif | png_phys | jpeg_exif | page_letter | page_a4 | assumed | unknown
    width: int = 0
    height: int = 0

    def round_dpi(self) -> int | None:
        if self.dpi is None or self.dpi <= 0:
            return None
        return int(round(float(self.dpi)))


@dataclass
class EnhanceResult:
    png_bytes: bytes
    applied: bool
    scale: float = 1.0
    deskew_angle: float = 0.0
    width: int = 0
    height: int = 0
    elapsed_ms: int = 0
    steps: list[str] = field(default_factory=list)
    note: str | None = None
    error: str | None = None
    dpi_before: float | None = None
    dpi_after: float | None = None  # effective DPI after upscale
    dpi_metadata: float | None = None  # value embedded in PNG pHYs / JPEG density
    dpi_source: str | None = None

    def to_metrics(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "enhance_applied": bool(self.applied),
            "enhance_scale": round(float(self.scale), 3),
            "enhance_deskew_angle": round(float(self.deskew_angle), 3),
            "enhance_width": int(self.width),
            "enhance_height": int(self.height),
            "enhance_ms": int(self.elapsed_ms),
            "enhance_steps": list(self.steps),
            "enhance_note": self.note,
            "enhance_error": self.error,
            "enhance_target_dpi": _TARGET_DPI,
        }
        out.update(
            _dpi_pair_metrics(
                self.dpi_before,
                self.dpi_after,
                self.dpi_source,
                self.scale,
                dpi_metadata=self.dpi_metadata,
            )
        )
        return out


def _dpi_pair_metrics(
    dpi_before: float | None,
    dpi_after: float | None,
    dpi_source: str | None,
    scale: float | None = None,
    *,
    dpi_metadata: float | None = None,
) -> dict[str, Any]:
    before_i = int(round(dpi_before)) if dpi_before and dpi_before > 0 else None
    after_i = int(round(dpi_after)) if dpi_after and dpi_after > 0 else None
    meta_i = (
        int(round(dpi_metadata)) if dpi_metadata and dpi_metadata > 0 else None
    )
    out: dict[str, Any] = {
        "dpi_before": before_i,
        "dpi_after": after_i,
        "dpi_effective": after_i,
        "dpi_in": before_i,
        "dpi_out": after_i,
        "dpi_metadata": meta_i,
    }
    if before_i and after_i and before_i > 0:
        out["dpi_scale_factor"] = round(float(after_i) / float(before_i), 3)
    elif scale is not None and scale > 0:
        out["dpi_scale_factor"] = round(float(scale), 3)
    if dpi_source:
        out["dpi_source"] = dpi_source
        out["dpi_before_estimated"] = dpi_source in _ESTIMATED_DPI_SOURCES
    return out


def estimate_image_dpi(image_bytes: bytes) -> DpiEstimate:
    """Estimate DPI from EXIF / PNG pHYs, else pixel dims vs Letter/A4."""
    if not image_bytes:
        return DpiEstimate(dpi=None, source="unknown")
    try:
        from PIL import Image
    except ImportError:
        return _estimate_dpi_from_cv_size(image_bytes)

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = int(img.size[0]), int(img.size[1])
            # Pillow surfaces PNG pHYs and some JPEG density as info['dpi'].
            info_dpi = img.info.get("dpi")
            if isinstance(info_dpi, (tuple, list)) and len(info_dpi) >= 1:
                val = float(info_dpi[0] or 0)
                if val >= 36:
                    src = "png_phys" if (img.format or "").upper() == "PNG" else "exif"
                    return DpiEstimate(dpi=val, source=src, width=w, height=h)
            if isinstance(info_dpi, (int, float)) and float(info_dpi) >= 36:
                return DpiEstimate(
                    dpi=float(info_dpi),
                    source="exif",
                    width=w,
                    height=h,
                )
            # Explicit JPEG EXIF Resolution
            try:
                exif = img.getexif()
                if exif:
                    # 282=XResolution, 283=YResolution, 296=ResolutionUnit (2=inch, 3=cm)
                    x_res = exif.get(282)
                    unit = exif.get(296, 2)
                    if x_res is not None:
                        num = float(getattr(x_res, "numerator", x_res) or 0)
                        den = float(getattr(x_res, "denominator", 1) or 1)
                        val = num / den if den else float(x_res)
                        if unit == 3:  # cm → inch
                            val = val * 2.54
                        if val >= 36:
                            return DpiEstimate(
                                dpi=val, source="jpeg_exif", width=w, height=h
                            )
            except Exception:
                pass
            return _estimate_dpi_from_page_size(w, h)
    except Exception:
        logger.debug("ScanX DPI Pillow probe failed", exc_info=True)
        return _estimate_dpi_from_cv_size(image_bytes)


def _estimate_dpi_from_cv_size(image_bytes: bytes) -> DpiEstimate:
    bgr = _decode_bgr(image_bytes)
    if bgr is None:
        return DpiEstimate(dpi=None, source="unknown")
    h, w = bgr.shape[:2]
    return _estimate_dpi_from_page_size(int(w), int(h))


def _estimate_dpi_from_page_size(width: int, height: int) -> DpiEstimate:
    """Pick Letter/A4 orientation whose implied DPI is most plausible."""
    if width <= 0 or height <= 0:
        return DpiEstimate(dpi=None, source="unknown", width=width, height=height)
    short, long = (width, height) if width <= height else (height, width)
    best: tuple[float, str, float] | None = None  # score, source, dpi
    for name, page_short, page_long in _PAGE_SIZES_IN:
        dpi_s = short / page_short
        dpi_l = long / page_long
        dpi = (dpi_s + dpi_l) / 2.0
        # Prefer estimates near common scan DPIs (72–600).
        if dpi < 36 or dpi > 900:
            continue
        # Lower score = better (how close short/long DPI agree + distance from anchors).
        agree = abs(dpi_s - dpi_l)
        anchor = min(abs(dpi - 72), abs(dpi - 96), abs(dpi - 150), abs(dpi - 300))
        score = agree + 0.15 * anchor
        src = f"page_{name}"
        if best is None or score < best[0]:
            best = (score, src, dpi)
    if best is None:
        # Fallback: assume Letter portrait.
        dpi = long / 11.0
        return DpiEstimate(
            dpi=dpi if dpi >= 36 else float(_ASSUMED_SOURCE_DPI),
            source="assumed",
            width=width,
            height=height,
        )
    return DpiEstimate(dpi=best[2], source=best[1], width=width, height=height)


def dpi_metrics_without_enhance(images: list[bytes]) -> dict[str, Any]:
    """Record dpi_before for frames when OpenCV enhance is skipped."""
    if not images:
        return {
            "enhance_applied": False,
            "dpi_before": None,
            "dpi_after": None,
            "dpi_effective": None,
            "dpi_metadata": None,
            "dpi_in": None,
            "dpi_out": None,
        }
    befores: list[float] = []
    sources: list[str] = []
    per_page: list[dict[str, Any]] = []
    for idx, raw in enumerate(images):
        est = estimate_image_dpi(raw)
        if est.dpi and est.dpi > 0:
            befores.append(float(est.dpi))
        sources.append(est.source)
        per_page.append(
            {
                "page": idx,
                "dpi_before": est.round_dpi(),
                "dpi_after": None,
                "dpi_source": est.source,
                "width": est.width,
                "height": est.height,
            }
        )
    avg_before = sum(befores) / len(befores) if befores else None
    src = sources[0] if len(set(sources)) == 1 else "mixed"
    out = _dpi_pair_metrics(avg_before, None, src, scale=1.0)
    out["enhance_applied"] = False
    out["dpi_pages"] = per_page
    if befores:
        out["dpi_before_min"] = int(round(min(befores)))
        out["dpi_before_max"] = int(round(max(befores)))
        out["dpi_before_avg"] = int(round(sum(befores) / len(befores)))
    return out


def _cv2():
    import cv2

    return cv2


def _np():
    import numpy as np

    return np


def _decode_bgr(image_bytes: bytes):
    cv2 = _cv2()
    np = _np()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is not None:
        return bgr
    # TIFF / odd containers via Pillow.
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb = np.array(img)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _round_dpi_meta(dpi: float | None) -> int | None:
    if dpi is None or dpi <= 0:
        return None
    return max(1, int(round(float(dpi))))


def _embed_png_dpi(png_bytes: bytes, dpi: float) -> bytes:
    """Rewrite PNG with pHYs so Windows Properties shows Horizontal/Vertical Resolution."""
    dpi_i = _round_dpi_meta(dpi)
    if not dpi_i:
        return png_bytes
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png_bytes)) as img:
            out = io.BytesIO()
            # Pillow writes PNG pHYs (pixels/meter) from dpi=…
            img.save(out, format="PNG", dpi=(dpi_i, dpi_i))
            return out.getvalue()
    except Exception:
        logger.warning("ScanX PNG DPI embed failed; returning OpenCV PNG", exc_info=True)
        return png_bytes


def _encode_png(gray_or_bgr, *, dpi: float | None = None) -> bytes:
    """Encode grayscale/BGR as PNG; optionally embed DPI via PNG pHYs."""
    cv2 = _cv2()
    ok, buf = cv2.imencode(".png", gray_or_bgr)
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    raw = bytes(buf.tobytes())
    if dpi and dpi > 0:
        return _embed_png_dpi(raw, dpi)
    return raw


def encode_preview_jpeg(
    image_bytes: bytes,
    *,
    max_side: int = 1800,
    quality: int = 82,
    dpi: float | None = None,
) -> bytes:
    """Downscale enhanced/original frame to a counsellor preview JPEG.

    When ``dpi`` is set, embeds JFIF/EXIF density so Windows Properties shows
    that Horizontal/Vertical Resolution (typically enhance target 300).
    """
    cv2 = _cv2()
    np = _np()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # Grayscale PNG from enhance pipeline.
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError("preview_decode_failed")
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side > max_side > 0:
        scale = float(max_side) / float(long_side)
        img = cv2.resize(
            img,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    dpi_i = _round_dpi_meta(dpi)
    if dpi_i:
        try:
            from PIL import Image

            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            out = io.BytesIO()
            pil.save(
                out,
                format="JPEG",
                quality=int(max(40, min(95, quality))),
                dpi=(dpi_i, dpi_i),
                optimize=True,
            )
            return out.getvalue()
        except Exception:
            logger.warning(
                "ScanX preview JPEG DPI embed failed; falling back to OpenCV",
                exc_info=True,
            )
    ok, buf = cv2.imencode(
        ".jpg",
        img,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(max(40, min(95, quality)))],
    )
    if not ok:
        raise RuntimeError("preview_encode_failed")
    return bytes(buf.tobytes())


def _compute_upscale(width: int, height: int, *, dpi_before: float | None = None) -> float:
    """Locked raster scale from pixel size only.

    DPI metadata is ignored. The same pixel dimensions always produce the same
    scale, so a phone JPEG and a re-save with a different DPI tag do not take
    different enhance paths.
    """
    del dpi_before
    long_side = max(int(width), int(height))
    short_side = min(int(width), int(height))
    if short_side <= 0 or long_side <= 0:
        return 1.0
    if short_side >= 1600:
        return 1.0
    scale = 1600.0 / float(short_side)
    if long_side * scale > _MAX_SIDE_PX:
        scale = max(1.0, float(_MAX_SIDE_PX) / float(long_side))
    return float(scale)


def estimate_skew_angle(image) -> float:
    """Estimate minor page tilt (degrees) via MinAreaRect + Hough cross-check.

    Returns 0.0 for near-zero noise or huge angles so straight pages are not warped.
    Passport booklet borders often trigger a false MinAreaRect ~5–6° while Hough
    stays near 0° — prefer Hough in that case so long address lines are not clipped.
    Accepts grayscale or BGR ``ndarray``.
    """
    cv2 = _cv2()
    np = _np()
    if image is None or getattr(image, "size", 0) == 0:
        return 0.0
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    h, w = gray.shape[:2]
    rect_angle = 0.0
    try:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        if len(coords) > 500:
            rect = cv2.minAreaRect(coords.astype(np.float32))
            rect_angle = float(rect[-1])
            if rect_angle < -45:
                rect_angle = 90.0 + rect_angle
            # Minor skews only — skip large rotations (wrong minAreaRect axis).
            if abs(rect_angle) > 15:
                rect_angle = 0.0
    except Exception:
        rect_angle = 0.0

    hough_angle: float | None = None
    try:
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=max(80, w // 4))
        if lines is not None and len(lines) > 0:
            angles: list[float] = []
            for rho_theta in lines[:40]:
                _rho, theta = rho_theta[0]
                deg = (theta * 180.0 / np.pi) - 90.0
                if -15 <= deg <= 15:
                    angles.append(float(deg))
            if angles:
                hough_angle = float(np.median(angles))
    except Exception:
        hough_angle = None

    if hough_angle is not None:
        # Nearly-straight page: false MinAreaRect from decorative borders.
        if abs(hough_angle) < 0.35 and abs(rect_angle) > 1.0:
            return 0.0
        if abs(rect_angle) >= 0.35 and abs(hough_angle - rect_angle) <= 2.5:
            angle = (rect_angle + hough_angle) / 2.0
        elif abs(hough_angle) >= 0.35:
            angle = hough_angle
        elif abs(rect_angle) <= 3.0:
            angle = rect_angle
        else:
            angle = 0.0
    else:
        # No Hough support — only trust small MinAreaRect tilts.
        angle = rect_angle if abs(rect_angle) <= 3.0 else 0.0

    if abs(angle) < 0.35:
        return 0.0
    if abs(angle) > 8:
        return 0.0
    return float(angle)


def deskew_image(image):
    """Correct minor page tilt with OpenCV ``warpAffine``.

    Call after grayscale (and optional upscale) and before RapidOCR so text
    boxes align with parent/spouse fields. Skips near-zero / huge angles.
    Expands the canvas so rotation does not clip left/right of wide address lines.

    Args:
        image: Grayscale or BGR ``ndarray``.

    Returns:
        ``(deskewed_gray, angle_degrees)``. Angle is 0.0 when no warp applied.
    """
    import math

    cv2 = _cv2()
    if image is None or getattr(image, "size", 0) == 0:
        return image, 0.0
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    angle = estimate_skew_angle(gray)
    if abs(angle) < 0.35:
        return gray, 0.0

    h, w = gray.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rad = math.radians(angle)
    cos_a, sin_a = abs(math.cos(rad)), abs(math.sin(rad))
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    matrix[0, 2] += (new_w - w) / 2.0
    matrix[1, 2] += (new_h - h) / 2.0
    rotated = cv2.warpAffine(
        gray,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, float(angle)


# Back-compat alias used by older call sites / tests.
_deskew = deskew_image


def _shadow_reduce(gray):
    """Background division to flatten uneven illumination."""
    cv2 = _cv2()
    np = _np()
    try:
        kernel = max(15, (min(gray.shape[:2]) // 20) | 1)
        background = cv2.GaussianBlur(gray, (kernel, kernel), 0)
        background = np.maximum(background, 1)
        norm = (gray.astype(np.float32) / background.astype(np.float32)) * 255.0
        return np.clip(norm, 0, 255).astype(np.uint8)
    except Exception:
        return gray


def _denoise(gray):
    cv2 = _cv2()
    h, w = gray.shape[:2]
    if h * w > 2_500_000:
        return cv2.medianBlur(gray, 3)
    try:
        return cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    except Exception:
        return cv2.medianBlur(gray, 3)


def _binarize(gray):
    cv2 = _cv2()
    np = _np()
    adaptive = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        10,
    )
    _t, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    blended = np.where(adaptive == otsu, adaptive, adaptive)
    return blended.astype(np.uint8)


def _morph_preserve_lines(binary):
    cv2 = _cv2()
    close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    out = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_k, iterations=1)
    dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    out = cv2.dilate(out, dilate_k, iterations=1)

    try:
        h_len = max(20, out.shape[1] // 40)
        v_len = max(20, out.shape[0] // 40)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        inv = cv2.bitwise_not(out)
        h_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, h_kernel)
        v_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel)
        lines = cv2.bitwise_or(h_lines, v_lines)
        inv2 = cv2.bitwise_or(inv, lines)
        out = cv2.bitwise_not(inv2)
    except Exception:
        pass
    return out


def _unsharp(binary_or_gray):
    cv2 = _cv2()
    np = _np()
    blur = cv2.GaussianBlur(binary_or_gray, (0, 0), sigmaX=1.0)
    sharp = cv2.addWeighted(binary_or_gray, 1.4, blur, -0.4, 0)
    return np.clip(sharp, 0, 255).astype(np.uint8)


def _pad_white(img, pad: int = _PAD_PX):
    cv2 = _cv2()
    return cv2.copyMakeBorder(
        img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )


def enhance_image_bytes(image_bytes: bytes) -> EnhanceResult:
    """Run the full OpenCV pipeline; return PNG bytes + metrics."""
    t0 = time.perf_counter()
    steps: list[str] = []
    dpi_est = estimate_image_dpi(image_bytes)
    dpi_before = float(dpi_est.dpi) if dpi_est.dpi and dpi_est.dpi > 0 else None
    dpi_source = dpi_est.source
    try:
        cv2 = _cv2()
    except ImportError as exc:
        return EnhanceResult(
            png_bytes=image_bytes,
            applied=False,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            error=f"opencv_missing: {exc}",
            note="passthrough_no_opencv",
            dpi_before=dpi_before,
            dpi_after=None,
            dpi_source=dpi_source,
        )

    try:
        bgr = _decode_bgr(image_bytes)
        if bgr is None:
            return EnhanceResult(
                png_bytes=image_bytes,
                applied=False,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                error="decode_failed",
                note="passthrough_decode_failed",
                dpi_before=dpi_before,
                dpi_after=None,
                dpi_source=dpi_source,
            )

        # 1. Grayscale
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        steps.append("grayscale")

        # 2. Cubic upscale toward ≥300 DPI equivalent
        h0, w0 = gray.shape[:2]
        if dpi_before is None:
            page_est = _estimate_dpi_from_page_size(w0, h0)
            dpi_before = page_est.dpi
            dpi_source = page_est.source

        scale = _compute_upscale(w0, h0, dpi_before=dpi_before)
        if scale > 1.01:
            gray = cv2.resize(
                gray,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
            steps.append(f"upscale_{scale:.2f}x")
        else:
            scale = 1.0
            steps.append("upscale_skip")

        # 3. Deskew (after grayscale/upscale, before RapidOCR)
        gray, angle = deskew_image(gray)
        steps.append(f"deskew_{angle:.2f}")

        # 4. CLAHE + shadow reduce
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        steps.append("clahe")
        gray = _shadow_reduce(gray)
        steps.append("shadow_divide")

        # 5. Denoise
        gray = _denoise(gray)
        steps.append("denoise")

        # 6. Light unsharp on gray (skip hard binarize / morph — OCR-mild)
        gray = _unsharp(gray)
        steps.append("unsharp")

        # 7. White border
        gray = _pad_white(gray)
        steps.append("pad")

        h1, w1 = gray.shape[:2]
        # Effective DPI after cubic upscale (pad does not change content DPI).
        dpi_after = (
            (float(dpi_before) * float(scale)) if dpi_before else float(_TARGET_DPI)
        )
        # Embed target DPI in file metadata when upscale aimed for ≥300; otherwise
        # mirror effective DPI. dpi_before may be page_letter estimate — still write
        # 300 after a successful target upscale so Windows Properties matches intent.
        if dpi_after >= float(_TARGET_DPI) * 0.9:
            dpi_metadata = float(_TARGET_DPI)
        else:
            dpi_metadata = float(dpi_after)
        png = _encode_png(gray, dpi=dpi_metadata)
        return EnhanceResult(
            png_bytes=png,
            applied=True,
            scale=scale,
            deskew_angle=angle,
            width=int(w1),
            height=int(h1),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            steps=steps,
            note="opencv_pipeline_v2_mild",
            dpi_before=dpi_before,
            dpi_after=dpi_after,
            dpi_metadata=dpi_metadata,
            dpi_source=dpi_source,
        )
    except Exception as exc:
        logger.warning("ScanX enhance failed: %s", exc, exc_info=True)
        return EnhanceResult(
            png_bytes=image_bytes,
            applied=False,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            steps=steps,
            error=f"{type(exc).__name__}: {exc}"[:200],
            note="passthrough_enhance_error",
            dpi_before=dpi_before,
            dpi_after=None,
            dpi_source=dpi_source,
        )


def enhance_image_batch(
    images: list[bytes],
    *,
    max_images: int | None = None,
) -> tuple[list[bytes], dict[str, Any]]:
    """Enhance many page images; aggregate metrics for metrics_json."""
    t0 = time.perf_counter()
    limit = len(images) if max_images is None else min(len(images), max(0, int(max_images)))
    out: list[bytes] = []
    applied_n = 0
    scales: list[float] = []
    angles: list[float] = []
    per_page_ms: list[int] = []
    errors: list[str] = []
    dpi_befores: list[float] = []
    dpi_afters: list[float] = []
    dpi_metas: list[float] = []
    per_page_dpi: list[dict[str, Any]] = []
    dpi_sources: list[str] = []

    for idx, raw in enumerate(images[:limit]):
        from app.services.scanx_cancel import raise_if_cancelled

        raise_if_cancelled()
        result = enhance_image_bytes(raw)
        out.append(result.png_bytes if result.applied else raw)
        if result.applied:
            applied_n += 1
            scales.append(result.scale)
            angles.append(result.deskew_angle)
        per_page_ms.append(result.elapsed_ms)
        if result.error:
            errors.append(f"p{idx}:{result.error}")
        if result.dpi_before and result.dpi_before > 0:
            dpi_befores.append(float(result.dpi_before))
        if result.dpi_after and result.dpi_after > 0:
            dpi_afters.append(float(result.dpi_after))
        if result.dpi_metadata and result.dpi_metadata > 0:
            dpi_metas.append(float(result.dpi_metadata))
        if result.dpi_source:
            dpi_sources.append(result.dpi_source)
        meta_i = (
            int(round(result.dpi_metadata))
            if result.dpi_metadata and result.dpi_metadata > 0
            else None
        )
        per_page_dpi.append(
            {
                "page": idx,
                "dpi_before": int(round(result.dpi_before))
                if result.dpi_before and result.dpi_before > 0
                else None,
                "dpi_after": int(round(result.dpi_after))
                if result.dpi_after and result.dpi_after > 0
                else None,
                "dpi_effective": int(round(result.dpi_after))
                if result.dpi_after and result.dpi_after > 0
                else None,
                "dpi_metadata": meta_i,
                "dpi_source": result.dpi_source,
                "dpi_before_estimated": (
                    result.dpi_source in _ESTIMATED_DPI_SOURCES
                    if result.dpi_source
                    else None
                ),
                "scale": round(float(result.scale), 3),
                "width": result.width,
                "height": result.height,
            }
        )

    if limit < len(images):
        out.extend(images[limit:])

    avg_before = sum(dpi_befores) / len(dpi_befores) if dpi_befores else None
    avg_after = sum(dpi_afters) / len(dpi_afters) if dpi_afters else None
    avg_meta = sum(dpi_metas) / len(dpi_metas) if dpi_metas else None
    src = (
        dpi_sources[0]
        if dpi_sources and len(set(dpi_sources)) == 1
        else ("mixed" if dpi_sources else None)
    )
    scale_avg = sum(scales) / len(scales) if scales else 1.0

    metrics: dict[str, Any] = {
        "enhance_applied": applied_n > 0,
        "enhance_pages": applied_n,
        "enhance_page_count": limit,
        "enhance_ms_total": int((time.perf_counter() - t0) * 1000),
        "enhance_ms_per_page": per_page_ms,
        "enhance_scale_avg": round(scale_avg, 3),
        "enhance_deskew_avg": round(sum(angles) / len(angles), 3) if angles else 0.0,
        "enhance_target_dpi": _TARGET_DPI,
        "enhance_note": "opencv_pipeline_v2_mild" if applied_n else "enhance_none",
        "dpi_pages": per_page_dpi,
    }
    metrics.update(
        _dpi_pair_metrics(
            avg_before, avg_after, src, scale=scale_avg, dpi_metadata=avg_meta
        )
    )
    if dpi_befores:
        metrics["dpi_before_min"] = int(round(min(dpi_befores)))
        metrics["dpi_before_max"] = int(round(max(dpi_befores)))
        metrics["dpi_before_avg"] = int(round(sum(dpi_befores) / len(dpi_befores)))
    if dpi_afters:
        metrics["dpi_after_min"] = int(round(min(dpi_afters)))
        metrics["dpi_after_max"] = int(round(max(dpi_afters)))
        metrics["dpi_after_avg"] = int(round(sum(dpi_afters) / len(dpi_afters)))
    if errors:
        metrics["enhance_errors"] = errors[:8]
    return out, metrics
