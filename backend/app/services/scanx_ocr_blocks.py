"""ScanX OCR text blocks: boxes, confidence, spatial reading order.

Transforms raw RapidOCR / PaddleOCR detections into ordered blocks with an
80% confidence flag for counsellor review.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Spec: confidence < 0.80 → low-confidence / requires_manual_review.
OCR_CONFIDENCE_THRESHOLD = 0.80


@dataclass
class OcrTextBlock:
    block_id: str
    bounding_box: list[list[float]]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    raw_ocr_text: str
    cleaned_text: str
    confidence: float
    is_low_confidence: bool
    reading_order_index: int
    page_index: int = 0
    # Grid cell coordinates when spatial table reconstruction assigns them.
    row_index: int | None = None
    column_index: int | None = None

    @property
    def text(self) -> str:
        """Prefer cleaned text for embeddings / reading order (legacy alias)."""
        cleaned = (self.cleaned_text or "").strip()
        if cleaned:
            return self.cleaned_text
        return self.raw_ocr_text or ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "block_id": self.block_id,
            "bounding_box": self.bounding_box,
            "raw_ocr_text": self.raw_ocr_text,
            "cleaned_text": self.cleaned_text,
            "confidence": self.confidence,
            "is_low_confidence": self.is_low_confidence,
            "reading_order_index": self.reading_order_index,
            "page_index": self.page_index,
            # Backward-compat for older FE / metrics consumers.
            "text": self.text,
        }
        if self.row_index is not None:
            out["row_index"] = self.row_index
        if self.column_index is not None:
            out["column_index"] = self.column_index
        return out


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_box(raw: Any) -> list[list[float]] | None:
    """Accept 4-point polygons or [x_min,y_min,x_max,y_max] → 4 corners."""
    if raw is None:
        return None
    try:
        import numpy as np

        arr = np.asarray(raw, dtype=float)
    except Exception:
        return None
    if arr.size == 8:
        pts = arr.reshape(4, 2)
    elif arr.size == 4:
        x0, y0, x1, y1 = (float(v) for v in arr.reshape(4))
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    elif arr.ndim == 2 and arr.shape[0] >= 4 and arr.shape[1] >= 2:
        pts = arr[:4, :2]
    else:
        return None
    return [[float(p[0]), float(p[1])] for p in pts]


def _box_stats(box: list[list[float]]) -> dict[str, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return {
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "cx": (x0 + x1) / 2.0,
        "cy": (y0 + y1) / 2.0,
        "w": max(1.0, x1 - x0),
        "h": max(1.0, y1 - y0),
    }


def blocks_from_rapid_output(
    result: Any,
    *,
    page_index: int = 0,
    id_prefix: str = "p0",
) -> list[OcrTextBlock]:
    """Parse RapidOCROutput (boxes, txts, scores) into OcrTextBlock list."""
    if result is None:
        return []

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    # Older rapidocr-onnxruntime: list of (box, text, score) or [box, (text, score)]
    if boxes is None and isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            out: list[OcrTextBlock] = []
            for i, row in enumerate(result):
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                box = _normalize_box(row[0])
                payload = row[1]
                conf = 1.0
                if isinstance(payload, (list, tuple)):
                    text = str(payload[0]).strip() if payload else ""
                    if len(payload) > 1:
                        conf = _as_float(payload[1], 1.0)
                else:
                    text = str(payload).strip()
                    if len(row) > 2:
                        conf = _as_float(row[2], 1.0)
                if not text or box is None:
                    continue
                conf = max(0.0, min(1.0, conf))
                out.append(
                    OcrTextBlock(
                        block_id=f"{id_prefix}-b{i}",
                        bounding_box=box,
                        raw_ocr_text=text,
                        cleaned_text=text,
                        confidence=conf,
                        is_low_confidence=conf < OCR_CONFIDENCE_THRESHOLD,
                        reading_order_index=i,
                        page_index=page_index,
                    )
                )
            return out
        return []

    if not txts:
        return []

    box_list = list(boxes) if boxes is not None else [None] * len(txts)
    score_list = list(scores) if scores is not None else [1.0] * len(txts)
    n = min(len(txts), len(box_list), len(score_list))
    out = []
    for i in range(n):
        text = str(txts[i]).strip()
        if not text:
            continue
        box = _normalize_box(box_list[i])
        if box is None:
            y = float(i * 20)
            box = [[0.0, y], [100.0, y], [100.0, y + 16.0], [0.0, y + 16.0]]
        conf = max(0.0, min(1.0, _as_float(score_list[i], 1.0)))
        out.append(
            OcrTextBlock(
                block_id=f"{id_prefix}-b{i}",
                bounding_box=box,
                raw_ocr_text=text,
                cleaned_text=text,
                confidence=conf,
                is_low_confidence=conf < OCR_CONFIDENCE_THRESHOLD,
                reading_order_index=i,
                page_index=page_index,
            )
        )
    return out


def blocks_from_paddle_output(
    result: Any,
    *,
    page_index: int = 0,
    id_prefix: str = "p0",
) -> list[OcrTextBlock]:
    """Best-effort parse of PaddleOCR 2.x/3.x results into blocks."""
    if result is None:
        return []

    out: list[OcrTextBlock] = []

    if isinstance(result, list) and result and not isinstance(result[0], list):
        for item in result:
            rec = getattr(item, "rec_texts", None)
            scores = getattr(item, "rec_scores", None)
            polys = getattr(item, "rec_polys", None) or getattr(item, "dt_polys", None)
            if rec is None and isinstance(item, dict):
                rec = item.get("rec_texts") or item.get("texts")
                scores = item.get("rec_scores") or item.get("scores")
                polys = item.get("rec_polys") or item.get("dt_polys") or item.get("boxes")
            if rec:
                score_list = list(scores) if scores is not None else [1.0] * len(rec)
                poly_list = list(polys) if polys is not None else [None] * len(rec)
                for i, text_raw in enumerate(rec):
                    text = str(text_raw).strip()
                    if not text:
                        continue
                    box = _normalize_box(poly_list[i] if i < len(poly_list) else None)
                    if box is None:
                        y = float(len(out) * 20)
                        box = [[0.0, y], [100.0, y], [100.0, y + 16.0], [0.0, y + 16.0]]
                    conf = max(
                        0.0,
                        min(
                            1.0,
                            _as_float(score_list[i] if i < len(score_list) else 1.0, 1.0),
                        ),
                    )
                    out.append(
                        OcrTextBlock(
                            block_id=f"{id_prefix}-b{len(out)}",
                            bounding_box=box,
                            raw_ocr_text=text,
                            cleaned_text=text,
                            confidence=conf,
                            is_low_confidence=conf < OCR_CONFIDENCE_THRESHOLD,
                            reading_order_index=len(out),
                            page_index=page_index,
                        )
                    )
                continue
            if isinstance(item, list):
                out.extend(
                    blocks_from_paddle_output(
                        item,
                        page_index=page_index,
                        id_prefix=f"{id_prefix}-n{len(out)}",
                    )
                )
        if out:
            return out

    pages = result if isinstance(result, list) else [result]
    for page in pages:
        if page is None or not isinstance(page, (list, tuple)):
            continue
        for row in page:
            if row is None or not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            box = _normalize_box(row[0])
            payload = row[1]
            conf = 1.0
            if isinstance(payload, (list, tuple)) and payload:
                text = str(payload[0]).strip()
                if len(payload) > 1:
                    conf = _as_float(payload[1], 1.0)
            else:
                text = str(payload).strip()
            if not text:
                continue
            if box is None:
                y = float(len(out) * 20)
                box = [[0.0, y], [100.0, y], [100.0, y + 16.0], [0.0, y + 16.0]]
            conf = max(0.0, min(1.0, conf))
            out.append(
                OcrTextBlock(
                    block_id=f"{id_prefix}-b{len(out)}",
                    bounding_box=box,
                    raw_ocr_text=text,
                    cleaned_text=text,
                    confidence=conf,
                    is_low_confidence=conf < OCR_CONFIDENCE_THRESHOLD,
                    reading_order_index=len(out),
                    page_index=page_index,
                )
            )
    return out


def _cluster_lines(
    items: list[tuple[OcrTextBlock, dict[str, float]]],
    *,
    y_tol: float,
) -> list[list[tuple[OcrTextBlock, dict[str, float]]]]:
    """Group boxes into horizontal lines by vertical center proximity / overlap."""
    if not items:
        return []
    ordered = sorted(items, key=lambda t: (t[1]["cy"], t[1]["cx"]))
    lines: list[list[tuple[OcrTextBlock, dict[str, float]]]] = []
    for item in ordered:
        _blk, st = item
        placed = False
        for line in lines:
            line_cy = statistics.median(m[1]["cy"] for m in line)
            line_h = statistics.median(m[1]["h"] for m in line)
            tol = max(y_tol, line_h * 0.55)
            if abs(st["cy"] - line_cy) <= tol:
                y0 = max(st["y0"], min(m[1]["y0"] for m in line))
                y1 = min(st["y1"], max(m[1]["y1"] for m in line))
                if y1 >= y0 or abs(st["cy"] - line_cy) <= tol:
                    line.append(item)
                    placed = True
                    break
        if not placed:
            lines.append([item])
    lines.sort(key=lambda ln: statistics.median(m[1]["cy"] for m in ln))
    for line in lines:
        line.sort(key=lambda t: t[1]["cx"])
    return lines


def _detect_column_count(
    items: list[tuple[OcrTextBlock, dict[str, float]]],
    *,
    layout: str = "document",
) -> int:
    """Heuristic: 2+ columns when a clear horizontal gap splits centers.

    Form/passport pages often have a right-side photo gutter — require a
    stronger gap before enabling column mode so biodata labels stay LTR.
    """
    if len(items) < 6:
        return 1
    cxs = sorted(st["cx"] for _b, st in items)
    width = max(st["x1"] for _b, st in items) - min(st["x0"] for _b, st in items)
    if width <= 1:
        return 1
    gaps: list[tuple[float, float]] = []
    for a, b in zip(cxs, cxs[1:]):
        gap = b - a
        min_gap = width * (0.22 if layout == "form" else 0.12)
        if gap > min_gap:
            gaps.append((gap, (a + b) / 2.0))
    if not gaps:
        return 1
    gaps.sort(reverse=True)
    best_gap, mid = gaps[0]
    need = width * (0.28 if layout == "form" else 0.15)
    mid_lo, mid_hi = (0.45, 0.85) if layout == "form" else (0.25, 0.75)
    if best_gap >= need and mid_lo * width < mid < mid_hi * width:
        return 2
    return 1


def spatial_sort_blocks(
    blocks: list[OcrTextBlock],
    *,
    layout: str = "document",
) -> list[OcrTextBlock]:
    """Enforce Western reading order: top→bottom, left→right (column-aware)."""
    return sort_ocr_boxes_by_reading_order(blocks, layout=layout)


def sort_ocr_boxes_by_reading_order(
    blocks: list[OcrTextBlock],
    *,
    layout: str = "document",
) -> list[OcrTextBlock]:
    """Cluster OCR boxes into horizontal lines (by y), sort left→right (x).

    Form layout keeps label/value pairs on the same row from being torn apart
    by false two-column detection (common on passport biodata pages).
    """
    if len(blocks) <= 1:
        for i, b in enumerate(blocks):
            b.reading_order_index = i
            b.is_low_confidence = b.confidence < OCR_CONFIDENCE_THRESHOLD
        return list(blocks)

    by_page: dict[int, list[OcrTextBlock]] = {}
    for blk in blocks:
        by_page.setdefault(int(blk.page_index or 0), []).append(blk)

    ordered: list[OcrTextBlock] = []
    for page_idx in sorted(by_page.keys()):
        ordered.extend(
            _sort_page_blocks_reading_order(by_page[page_idx], layout=layout)
        )

    for i, blk in enumerate(ordered):
        blk.reading_order_index = i
        blk.is_low_confidence = blk.confidence < OCR_CONFIDENCE_THRESHOLD
    return ordered


def _sort_page_blocks_reading_order(
    blocks: list[OcrTextBlock],
    *,
    layout: str,
) -> list[OcrTextBlock]:
    if len(blocks) <= 1:
        return list(blocks)

    decorated = [(b, _box_stats(b.bounding_box)) for b in blocks]
    heights = [st["h"] for _b, st in decorated]
    y_factor = 0.45 if layout == "form" else 0.5
    y_tol = max(8.0, statistics.median(heights) * y_factor)

    n_cols = _detect_column_count(decorated, layout=layout)
    if n_cols >= 2:
        xs = [st["cx"] for _b, st in decorated]
        split = statistics.median(xs)
        columns: list[list[tuple[OcrTextBlock, dict[str, float]]]] = [[], []]
        for item in decorated:
            columns[0 if item[1]["cx"] < split else 1].append(item)
        ordered: list[OcrTextBlock] = []
        for col in columns:
            if not col:
                continue
            lines = _cluster_lines(col, y_tol=y_tol)
            for line in lines:
                line.sort(key=lambda t: (t[1]["x0"], t[1]["cx"]))
                for blk, _st in line:
                    ordered.append(blk)
        return ordered

    lines = _cluster_lines(decorated, y_tol=y_tol)
    ordered: list[OcrTextBlock] = []
    for line in lines:
        line.sort(key=lambda t: (t[1]["x0"], t[1]["cx"]))
        for blk, _st in line:
            ordered.append(blk)
    return ordered


def blocks_to_reading_text(blocks: list[OcrTextBlock]) -> str:
    """Join spatially sorted blocks: same line → spaces, next line → newline.

    Keeps passport labels adjacent to their values (e.g. ``Place of Birth DELHI``).
    """
    usable = [b for b in blocks if (b.text or "").strip()]
    if not usable:
        return ""
    if len(usable) == 1:
        return usable[0].text.strip()

    decorated = [(b, _box_stats(b.bounding_box)) for b in usable]
    heights = [st["h"] for _b, st in decorated]
    y_tol = max(8.0, statistics.median(heights) * 0.55)

    lines = _cluster_lines(decorated, y_tol=y_tol)
    out_lines: list[str] = []
    for line in lines:
        line.sort(key=lambda t: (t[1]["x0"], t[1]["cx"]))
        tokens = [blk.text.strip() for blk, _st in line if blk.text.strip()]
        if tokens:
            out_lines.append(" ".join(tokens))
    return "\n".join(out_lines).strip()


def _cluster_x_centers(centers: list[float], *, tol: float) -> list[float]:
    """Greedy 1D cluster of x-centers → sorted column anchors."""
    if not centers:
        return []
    ordered = sorted(centers)
    clusters: list[list[float]] = [[ordered[0]]]
    for x in ordered[1:]:
        if abs(x - statistics.median(clusters[-1])) <= tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [statistics.median(c) for c in clusters]


def _assign_column(cx: float, anchors: list[float]) -> int:
    best_i, best_d = 0, abs(cx - anchors[0])
    for i, a in enumerate(anchors[1:], start=1):
        d = abs(cx - a)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _cell_text_for_grid(blk: OcrTextBlock) -> str:
    """Prefer cleaned cell text; drop bilingual / Tamil→Latin OCR garbage."""
    text = (blk.text or "").strip()
    if not text:
        return ""
    try:
        from app.services.ocr_cleaner import is_ocr_gibberish_line
        from app.services.scanx_embeddings import _ocr_line_is_noise

        if is_ocr_gibberish_line(text) or _ocr_line_is_noise(text):
            return ""
    except Exception:
        pass
    return text


def reconstruct_table_matrices(
    blocks: list[OcrTextBlock],
    *,
    min_rows: int = 3,
    min_cols: int = 2,
    annotate: bool = True,
) -> list[list[list[str]]]:
    """Rebuild row×column cell grids from spatially boxed OCR detections.

    When RapidOCR emits one box per cell, flat reading order loses Theory /
    Practical / Total alignment. Cluster boxes into lines, infer shared column
    x-anchors across consecutive multi-cell lines, and return matrices of cell
    strings suitable for ``parse_subjects_from_table_rows``.

    When ``annotate`` is True, sets ``row_index`` / ``column_index`` on blocks
    that land in a reconstructed cell.
    """
    if len(blocks) < min_rows * min_cols:
        return []

    by_page: dict[int, list[OcrTextBlock]] = {}
    for blk in blocks:
        by_page.setdefault(int(blk.page_index or 0), []).append(blk)

    matrices: list[list[list[str]]] = []
    for _page, page_blocks in sorted(by_page.items()):
        decorated = [(b, _box_stats(b.bounding_box)) for b in page_blocks]
        if len(decorated) < min_rows * min_cols:
            continue
        heights = [st["h"] for _b, st in decorated]
        y_tol = max(8.0, statistics.median(heights) * 0.5)
        lines = _cluster_lines(decorated, y_tol=y_tol)
        # Keep runs of lines that look tabular (≥2 cells).
        runs: list[list[list[tuple[OcrTextBlock, dict[str, float]]]]] = []
        current: list[list[tuple[OcrTextBlock, dict[str, float]]]] = []
        for line in lines:
            if len(line) >= 2:
                current.append(line)
            else:
                if len(current) >= min_rows:
                    runs.append(current)
                current = []
        if len(current) >= min_rows:
            runs.append(current)

        for run in runs:
            all_cx = [st["cx"] for line in run for _b, st in line]
            widths = [st["w"] for line in run for _b, st in line]
            x_tol = max(12.0, statistics.median(widths) * 0.55)
            anchors = _cluster_x_centers(all_cx, tol=x_tol)
            if len(anchors) < min_cols:
                continue
            # Drop sparse columns (appear on < half of multi-cell lines).
            col_hits = [0] * len(anchors)
            for line in run:
                seen_cols: set[int] = set()
                for _b, st in line:
                    seen_cols.add(_assign_column(st["cx"], anchors))
                for c in seen_cols:
                    col_hits[c] += 1
            keep = [i for i, h in enumerate(col_hits) if h >= max(2, len(run) // 2)]
            if len(keep) < min_cols:
                continue
            anchors = [anchors[i] for i in keep]
            n_cols = len(anchors)
            matrix: list[list[str]] = []
            for row_i, line in enumerate(run):
                cells = [""] * n_cols
                # Stable left→right within a line; merge colliding cells with space.
                for blk, st in sorted(line, key=lambda t: t[1]["cx"]):
                    text = _cell_text_for_grid(blk)
                    if not text:
                        continue
                    col = _assign_column(st["cx"], anchors)
                    if annotate:
                        blk.row_index = row_i
                        blk.column_index = col
                    if cells[col]:
                        cells[col] = f"{cells[col]} {text}".strip()
                    else:
                        cells[col] = text
                if any(cells):
                    matrix.append(cells)
            if len(matrix) >= min_rows and max(len(r) for r in matrix) >= min_cols:
                matrices.append(matrix)
    return matrices


def annotate_blocks_with_grid(blocks: list[OcrTextBlock]) -> list[OcrTextBlock]:
    """Assign ``row_index`` / ``column_index`` via table reconstruction (in place)."""
    if not blocks:
        return blocks
    reconstruct_table_matrices(blocks, annotate=True)
    return blocks


def detect_table_regions_from_image(
    image_bytes: bytes,
    *,
    max_regions: int = 8,
) -> list[dict[str, Any]]:
    """Morphological / line-based table ROI detection (OpenCV when available).

    Does not alter OCR pixels — returns axis-aligned boxes for metrics and
    optional crop hints. Empty list when OpenCV is missing or no grid found.
    """
    if not image_bytes:
        return []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return []
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        if h < 80 or w < 80:
            return []
        # Mild adaptive threshold → invert so lines are white.
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12
        )
        h_len = max(30, w // 30)
        v_len = max(30, h // 30)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
        grid = cv2.bitwise_or(h_lines, v_lines)
        # Dilate intersections so connected components form table-sized blobs.
        mix_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        grid = cv2.dilate(grid, mix_k, iterations=2)
        contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        page_area = float(h * w)
        regions: list[dict[str, Any]] = []
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = float(bw * bh)
            if area < page_area * 0.04 or area > page_area * 0.95:
                continue
            if bw < w * 0.25 or bh < h * 0.08:
                continue
            # Prefer wide marksheet-like aspect ratios.
            aspect = bw / max(1.0, float(bh))
            if aspect < 0.6:
                continue
            regions.append(
                {
                    "x": int(x),
                    "y": int(y),
                    "width": int(bw),
                    "height": int(bh),
                    "area_ratio": round(area / page_area, 4),
                    "aspect": round(aspect, 3),
                }
            )
        regions.sort(key=lambda r: r["area_ratio"], reverse=True)
        return regions[: max(1, int(max_regions))]
    except Exception:
        logger.debug("ScanX table region detect failed", exc_info=True)
        return []


def drop_garbage_ocr_blocks(blocks: list[OcrTextBlock]) -> list[OcrTextBlock]:
    """Clear ``cleaned_text`` on unmapped non-English / gibberish OCR tokens.

    Keeps ``raw_ocr_text`` for audit. Valid English, digits, and intentional
    bilingual labels (already normalized upstream) are preserved.
    """
    if not blocks:
        return blocks
    try:
        from app.services.ocr_cleaner import is_ocr_gibberish_line
        from app.services.scanx_embeddings import _ocr_line_is_noise
    except Exception:
        return blocks

    for blk in blocks:
        raw = (blk.raw_ocr_text or "").strip()
        cleaned = (blk.cleaned_text or "").strip() or raw
        if not cleaned:
            continue
        if is_ocr_gibberish_line(cleaned) or _ocr_line_is_noise(cleaned):
            # Allow intentional local-script subject names (Tamil letters etc.)
            # when they are mostly one script and not CJK/Latin soup.
            if _looks_like_intentional_local_script(cleaned):
                continue
            blk.cleaned_text = ""
    return blocks


def _looks_like_intentional_local_script(text: str) -> bool:
    """True for compact Tamil/Indic subject labels (not Latin OCR soup)."""
    s = (text or "").strip()
    if not s or len(s) > 48:
        return False
    # Tamil block U+0B80–U+0BFF; Devanagari U+0900–U+097F.
    indic = sum(1 for c in s if "\u0900" <= c <= "\u097f" or "\u0b80" <= c <= "\u0bff")
    latin = sum(1 for c in s if ("A" <= c <= "Z") or ("a" <= c <= "z"))
    if indic >= 2 and latin == 0:
        return True
    return False


def format_table_matrices_as_text(matrices: list[list[list[str]]]) -> str:
    """Serialize reconstructed grids as ``cell | cell`` lines for downstream parse."""
    lines: list[str] = []
    for matrix in matrices or []:
        for row in matrix:
            cells = [c.strip() for c in row if (c or "").strip()]
            if cells:
                lines.append(" | ".join(cells))
        if lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()


def blocks_to_reading_text_with_tables(blocks: list[OcrTextBlock]) -> str:
    """Reading-order text plus reconstructed ``|`` table lines when a grid is detected.

    Flat line join is always included; pipe matrices are appended when spatial
    clustering finds ≥3×2 cell grids so Theory/Practical/Total stay aligned.
    """
    base = blocks_to_reading_text(blocks)
    matrices = reconstruct_table_matrices(blocks)
    if not matrices:
        return base
    table_text = format_table_matrices_as_text(matrices)
    if not table_text:
        return base
    if not base:
        return table_text
    # Avoid duplicating when reading order already used pipes.
    if " | " in base and table_text in base:
        return base
    return f"{base}\n\n{table_text}".strip()


def blocks_to_json(blocks: list[OcrTextBlock]) -> list[dict[str, Any]]:
    return [b.to_dict() for b in blocks]


def summarize_blocks(blocks: list[OcrTextBlock]) -> dict[str, Any]:
    """Metrics for metrics_json / counsellor flags."""
    if not blocks:
        return {
            "ocr_block_count": 0,
            "ocr_low_confidence_count": 0,
            "ocr_confidence_threshold": OCR_CONFIDENCE_THRESHOLD,
            "requires_manual_review": False,
            "ocr_mean_confidence": None,
            "ocr_min_confidence": None,
            "ocr_low_confidence_block_ids": [],
        }
    confs = [b.confidence for b in blocks]
    low = [b for b in blocks if b.is_low_confidence]
    return {
        "ocr_block_count": len(blocks),
        "ocr_low_confidence_count": len(low),
        "ocr_confidence_threshold": OCR_CONFIDENCE_THRESHOLD,
        "requires_manual_review": len(low) > 0,
        "ocr_mean_confidence": round(sum(confs) / len(confs), 4),
        "ocr_min_confidence": round(min(confs), 4),
        "ocr_low_confidence_block_ids": [b.block_id for b in low[:40]],
    }
