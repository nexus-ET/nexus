"""ScanX image OCR: RapidOCR primary, PaddleOCR fallback.

Configured via ``SCANX_OCR_ENGINE`` (default ``rapid``) and
``SCANX_OCR_FALLBACK`` (default ``paddle``). Preserves Unicode (Tamil etc.).

Paddle requires both ``paddleocr`` and ``paddlepaddle``. When the primary
engine is unavailable or fails, Paddle may run — but metrics always record
``engine`` plus ``fallback_reason`` so silent fallback look-alikes are visible.
"""

from __future__ import annotations

import io
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services.ocr_cleaner import (
    clean_ocr_blocks_with_marks,
    clean_ocr_text,
    structure_marks_from_ocr,
)
from app.services.scanx_cancel import (
    ScanxJobCancelled,
    add_job_wait_ms,
    is_cancel_requested,
)
from app.services.scanx_ocr_blocks import (
    OcrTextBlock,
    annotate_blocks_with_grid,
    blocks_from_paddle_output,
    blocks_from_rapid_output,
    blocks_to_reading_text,
    blocks_to_reading_text_with_tables,
    detect_table_regions_from_image,
    sort_ocr_boxes_by_reading_order,
    spatial_sort_blocks,
)

logger = logging.getLogger(__name__)

_paddle_engine: Any | None = None
_rapid_engine: Any | None = None
# Separate locks: a hung PaddleOCR() model download must not block Rapid init.
_paddle_engine_lock = threading.Lock()
_rapid_engine_lock = threading.Lock()


def _ocr_concurrency() -> int:
    """Max concurrent RapidOCR/Paddle inference slots (SCANX_OCR_CONCURRENCY)."""
    try:
        n = int(getattr(settings, "SCANX_OCR_CONCURRENCY", 1) or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, n)


# Serialize heavy OCR inference across engines (not construction after timeout).
# Sized from SCANX_OCR_CONCURRENCY (default 1) so Rapid + Paddle never overlap.
_ocr_run_slots = threading.Semaphore(_ocr_concurrency())
# Fail only when the slot looks stuck — waiting on a live OCR is queue time.
# Peer may hold the slot for a full OCR budget plus abandon-drain (~180s).
_OCR_SLOT_STUCK_FLOOR_SEC = 600.0
_OCR_SLOT_DRAIN_ALLOWANCE_SEC = 180.0


def _ocr_slot_stuck_wait_sec(timeout_seconds: float) -> float:
    """How long a waiter may block before the busy slot is treated as stuck."""
    budget = ocr_budget_seconds()
    try:
        share = max(0.0, float(timeout_seconds))
    except (TypeError, ValueError):
        share = budget
    return max(
        _OCR_SLOT_STUCK_FLOOR_SEC,
        budget * 2.0 + _OCR_SLOT_DRAIN_ALLOWANCE_SEC,
        share + _OCR_SLOT_DRAIN_ALLOWANCE_SEC,
    )


_ENGINE_PADDLE = "paddle"
_ENGINE_RAPID = "rapid"
_KNOWN_ENGINES = frozenset({_ENGINE_PADDLE, _ENGINE_RAPID})

# Cache first probe failure so we do not spam ImportError stacks every page.
_paddle_probe_error: str | None = None
_paddle_probe_done = False

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class OcrResult:
    text: str | None
    engine: str
    note: str  # ocr_ok | ocr_empty | ocr_timeout | ocr_failed | ocr_unavailable
    elapsed_ms: int
    page_count: int = 1
    # When fallback ran because primary could not: short reason.
    fallback_reason: str | None = None
    # Configured primary at call time (rapid | paddle).
    primary_engine: str | None = None
    # Spatially ordered text blocks (box + confidence) for counsellor review.
    blocks: list[OcrTextBlock] = field(default_factory=list)
    # Structured marksheet rows for Dynamic Table (subject/theory/prac/total/words).
    marks: list[dict[str, str]] = field(default_factory=list)
    # Morphological table ROIs detected alongside OCR (metrics only).
    table_regions: list[dict[str, Any]] = field(default_factory=list)


def ocr_budget_seconds() -> float:
    try:
        return max(5.0, float(getattr(settings, "SCANX_OCR_BUDGET_SECONDS", 240.0) or 240.0))
    except (TypeError, ValueError):
        return 240.0


def _fallback_reserve_seconds(total_budget: float) -> float:
    """Seconds held back so a hung/slow primary cannot starve the fallback.

    Without a reserve, the primary can consume the full ``SCANX_OCR_BUDGET_SECONDS``
    wall clock; the loop then skips fallback with a misleading timeout reason
    and the UI shows empty extract.

    Keep the reserve modest: Rapid (typical primary) is fast on CPU. A large
    reserve (~45%) historically starved a slow Paddle primary. When Rapid is
    primary and Paddle is fallback, Rapid usually finishes quickly and leaves
    most of the remaining budget for Paddle.
    """
    budget = max(0.0, float(total_budget))
    if budget <= 20.0:
        return max(5.0, budget * 0.35)
    if budget <= 60.0:
        # Small budgets: leave ~20% (min 8s) for fallback.
        return min(15.0, max(8.0, budget * 0.2))
    # Fair share for primary first: ~12–15% reserved, capped at 25s.
    return min(25.0, max(12.0, budget * 0.12))


def _engine_role(engine_name: str) -> str:
    """primary | fallback | unused — for logs only; does not change runtime order."""
    if engine_name == configured_ocr_engine():
        return "primary"
    fallback = configured_ocr_fallback()
    if fallback and engine_name == fallback:
        return "fallback"
    return "unused"


def _warm_engine(engine_name: str) -> bool:
    """Best-effort construct an OCR engine (used to pre-warm fallback while primary runs)."""
    try:
        _probe_engine_import(engine_name)
        if engine_name == _ENGINE_PADDLE:
            _get_paddle_engine()
        elif engine_name == _ENGINE_RAPID:
            _get_rapid_engine()
        return True
    except Exception:
        logger.debug(
            "ScanX OCR pre-warm failed for %s", engine_name, exc_info=True
        )
        return False


def prewarm_ocr_engines(*, include_fallback: bool = True) -> None:
    """Load configured OCR engines so first mark-sheet OCR is inference-only.

    Warms ``SCANX_OCR_ENGINE`` first, then ``SCANX_OCR_FALLBACK`` if different.
    Runtime still tries primary first; fallback pre-warm only avoids a cold
    Paddle download after a Rapid timeout. Safe from API / RQ startup.
    Does not raise — failures leave cold-start path intact.
    """
    primary = configured_ocr_engine()
    fallback = configured_ocr_fallback() if include_fallback else None
    if fallback == primary:
        fallback = None
    logger.info(
        "ScanX OCR pre-warm: primary=%s fallback=%s (runtime uses primary first)",
        primary,
        fallback or "none",
    )
    if not _warm_engine(primary):
        logger.warning(
            "ScanX OCR primary engine %s did not pre-warm; first page may cold-start or fall back",
            primary,
        )
    if fallback and not _warm_engine(fallback):
        logger.warning(
            "ScanX OCR fallback engine %s did not pre-warm",
            fallback,
        )


def configured_ocr_engine() -> str:
    raw = str(getattr(settings, "SCANX_OCR_ENGINE", _ENGINE_RAPID) or _ENGINE_RAPID)
    name = raw.strip().lower()
    if name in {"rapidocr", "rapid-ocr"}:
        return _ENGINE_RAPID
    if name in {"paddleocr", "paddle-ocr"}:
        return _ENGINE_PADDLE
    return name if name in _KNOWN_ENGINES else _ENGINE_RAPID


def configured_ocr_fallback() -> str | None:
    raw = getattr(settings, "SCANX_OCR_FALLBACK", _ENGINE_PADDLE)
    if raw is None:
        return None
    name = str(raw).strip().lower()
    if not name or name in {"none", "off", "disabled"}:
        return None
    if name in {"rapidocr", "rapid-ocr"}:
        return _ENGINE_RAPID
    if name in {"paddleocr", "paddle-ocr"}:
        return _ENGINE_PADDLE
    return name if name in _KNOWN_ENGINES else _ENGINE_PADDLE


def _normalize_image_input(content: bytes | str | Path) -> bytes:
    if isinstance(content, (str, Path)):
        return Path(content).read_bytes()
    return content


# Longest side for CPU OCR. Enhanced ~300 DPI pages can exceed this; keep
# enough headroom that Rapid's Det.limit_side_len can still use the upscale
# (default Rapid uses 736 and would erase a 92→300 DPI gain).
_OCR_MAX_SIDE_PX = 3000

# RapidOCR defaults (limit_side_len=736, max_side_len=2000) renormalize pages
# so external cubic upscale barely affects detection. Prefer higher limits.
_RAPID_DET_LIMIT_SIDE_LEN = 1600
_RAPID_GLOBAL_MAX_SIDE_LEN = 3000

# Dense identity / multi-page PDF defaults (override via settings).
_RAPID_DEFAULT_BOX_THRESH = 0.35
_RAPID_DEFAULT_UNCLIP_RATIO = 1.8
_RAPID_DEFAULT_TEXT_SCORE = 0.4


def _rapid_runtime_kwargs() -> dict[str, Any]:
    """Per-call RapidOCR knobs for faint / tightly spaced passport text."""
    return {
        "use_cls": True,
        "box_thresh": float(
            getattr(settings, "SCANX_RAPID_BOX_THRESH", _RAPID_DEFAULT_BOX_THRESH)
            or _RAPID_DEFAULT_BOX_THRESH
        ),
        "unclip_ratio": float(
            getattr(settings, "SCANX_RAPID_UNCLIP_RATIO", _RAPID_DEFAULT_UNCLIP_RATIO)
            or _RAPID_DEFAULT_UNCLIP_RATIO
        ),
        "text_score": float(
            getattr(settings, "SCANX_RAPID_TEXT_SCORE", _RAPID_DEFAULT_TEXT_SCORE)
            or _RAPID_DEFAULT_TEXT_SCORE
        ),
    }


def get_optimized_rapidocr_engine(
    *,
    on_progress: "ProgressCallback | None" = None,
) -> Any:
    """Build / return a RapidOCR engine tuned for dense identity documents.

    Uses angle classification, a lower box threshold (≈0.35), and a slightly
    larger unclip ratio so faint or closely spaced passport labels are kept
    without drowning the page in noise. The same engine instance iterates
    every enhanced page in ``_run_rapid_on_frames``.
    """
    return _get_rapid_engine(on_progress=on_progress, optimized=True)


def _downscale_for_ocr(frame: Any) -> Any:
    """Shrink huge pages before Paddle/Rapid so CPU inference finishes in-budget."""
    try:
        w, h = frame.size
    except Exception:
        return frame
    longest = max(int(w or 0), int(h or 0))
    if longest <= _OCR_MAX_SIDE_PX:
        return frame
    scale = _OCR_MAX_SIDE_PX / float(longest)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    try:
        from PIL import Image

        resample = getattr(Image, "Resampling", Image).LANCZOS
        return frame.resize(new_size, resample)
    except Exception:
        return frame


def _pil_frames(content: bytes) -> list[Any]:
    from PIL import Image

    img = Image.open(io.BytesIO(content))
    frames: list[Any] = []
    try:
        n = int(getattr(img, "n_frames", 1) or 1)
    except Exception:
        n = 1
    # Cap frames so a huge TIFF cannot blow the OCR budget alone.
    max_frames = max(1, int(getattr(settings, "SCANX_MAX_PAGES", 10) or 10))
    for i in range(min(n, max_frames)):
        try:
            img.seek(i)
        except EOFError:
            break
        frame = _downscale_for_ocr(img.convert("RGB"))
        frames.append(frame.copy())
    if not frames:
        frames.append(_downscale_for_ocr(img.convert("RGB")))
    return frames


def _texts_from_rapid_output(result: Any) -> list[str]:
    if result is None:
        return []
    txts = getattr(result, "txts", None)
    if txts:
        return [str(t).strip() for t in txts if str(t).strip()]
    # Older rapidocr-onnxruntime style: (boxes, texts, scores) or list of lines
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2 and isinstance(first[1], str):
            return [str(row[1]).strip() for row in result if len(row) >= 2 and str(row[1]).strip()]
        if all(isinstance(x, str) for x in result):
            return [x.strip() for x in result if x.strip()]
    return []


def _texts_from_paddle_output(result: Any) -> list[str]:
    """Parse PaddleOCR 2.x ``ocr()`` and 3.x ``predict()`` result shapes."""
    if result is None:
        return []

    # PP-OCR 3.x: list of result objects with .rec_texts / dict-like
    if isinstance(result, list) and result and not isinstance(result[0], list):
        lines: list[str] = []
        for item in result:
            rec = getattr(item, "rec_texts", None)
            if rec is None and isinstance(item, dict):
                rec = item.get("rec_texts") or item.get("texts")
            if rec:
                lines.extend(str(t).strip() for t in rec if str(t).strip())
                continue
            # Nested classic page: [[[box], (text, score)], ...]
            if isinstance(item, list):
                lines.extend(_texts_from_paddle_output(item))
        if lines:
            return lines

    # Classic: result is [page_lines] where page_lines is list of [box, (text, score)]
    pages = result if isinstance(result, list) else [result]
    lines: list[str] = []
    for page in pages:
        if page is None:
            continue
        if isinstance(page, dict):
            rec = page.get("rec_texts") or page.get("texts") or page.get("txts")
            if rec:
                lines.extend(str(t).strip() for t in rec if str(t).strip())
            continue
        if not isinstance(page, (list, tuple)):
            continue
        for row in page:
            if row is None:
                continue
            if isinstance(row, str):
                if row.strip():
                    lines.append(row.strip())
                continue
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            payload = row[1]
            if isinstance(payload, (list, tuple)) and payload:
                text = str(payload[0]).strip()
            else:
                text = str(payload).strip()
            if text:
                lines.append(text)
    return lines


def _paddle_unavailable_message(exc: BaseException) -> str:
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    detail = f"{type(exc).__name__}: {exc}"
    # paddlepaddle has no Windows/Linux wheels for Python 3.14+ yet.
    if sys.version_info >= (3, 14) and (
        "paddle" in detail.lower() or isinstance(exc, ModuleNotFoundError)
    ):
        return (
            f"paddlepaddle unavailable on Python {py} "
            f"(wheels support 3.9-3.13); {detail}"
        )
    return detail


def _probe_paddle() -> None:
    """Require both paddleocr and paddlepaddle — paddleocr alone cannot run."""
    global _paddle_probe_done, _paddle_probe_error
    if _paddle_probe_done:
        if _paddle_probe_error:
            raise ImportError(_paddle_probe_error)
        return
    try:
        import os

        # Must be set before importing paddle (3.3.x oneDNN/PIR CPU crash).
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_enable_pir_api", "0")
        import paddle  # noqa: F401
        import paddleocr  # noqa: F401
        from paddleocr import PaddleOCR  # noqa: F401
    except Exception as exc:
        _paddle_probe_error = _paddle_unavailable_message(exc)
        _paddle_probe_done = True
        raise ImportError(_paddle_probe_error) from exc
    _paddle_probe_error = None
    _paddle_probe_done = True


def _paddle_models_likely_cached() -> bool:
    """Best-effort check for PP-OCR weights under ~/.paddlex (first-run download)."""
    try:
        root = Path.home() / ".paddlex" / "official_models"
        if not root.is_dir():
            return False
        # Det + rec weights are the heavy first-run downloads.
        det = list(root.glob("PP-OCR*/inference.pdiparams"))
        rec = list(root.glob("PP-OCR*rec*/inference.pdiparams")) or [
            p for p in det if "rec" in p.parent.name.lower()
        ]
        return bool(det) and any(p.stat().st_size > 1_000_000 for p in det)
    except Exception:
        return False


def _emit_progress(on_progress: ProgressCallback | None, message: str) -> None:
    if is_cancel_requested():
        raise ScanxJobCancelled()
    if not on_progress:
        return
    try:
        on_progress(message)
    except ScanxJobCancelled:
        raise
    except Exception:
        logger.debug("ScanX OCR progress callback failed", exc_info=True)


def _get_paddle_engine(*, on_progress: ProgressCallback | None = None) -> Any:
    global _paddle_engine
    with _paddle_engine_lock:
        if _paddle_engine is None:
            # PaddlePaddle 3.3.x + oneDNN/PIR crashes on CPU inference
            # (ConvertPirAttribute2RuntimeAttribute). Disable before import.
            import os

            os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("FLAGS_enable_pir_api", "0")
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

            if _paddle_models_likely_cached():
                _emit_progress(on_progress, "Loading PaddleOCR engine…")
            else:
                _emit_progress(
                    on_progress,
                    "Downloading OCR models (first run — may take several minutes)…",
                )

            from paddleocr import PaddleOCR

            # Prefer quiet / CPU defaults; tolerate API drift across 2.x / 3.x.
            # PaddleOCR 3.x rejects unknown kwargs (ValueError), so try several
            # signatures and catch Exception (not only TypeError).
            # enable_mkldnn=False is required on paddlepaddle 3.3.x CPU (oneDNN bug).
            # Disable doc-orientation / unwarp / textline-ori pipelines — they load
            # extra PP-LCNet/UVDoc weights and dominate CPU time on mark sheets.
            last_exc: BaseException | None = None
            for kwargs in (
                {
                    "lang": "en",
                    "device": "cpu",
                    "enable_mkldnn": False,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_textline_orientation": False,
                },
                {
                    "lang": "en",
                    "enable_mkldnn": False,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_textline_orientation": False,
                },
                {"lang": "en", "device": "cpu", "enable_mkldnn": False},
                {"lang": "en", "enable_mkldnn": False},
                {
                    "use_angle_cls": False,
                    "lang": "en",
                    "show_log": False,
                    "use_gpu": False,
                    "enable_mkldnn": False,
                },
                {"lang": "en", "device": "cpu"},
                {"lang": "en"},
                {},
            ):
                try:
                    _emit_progress(on_progress, "Initializing PaddleOCR…")
                    _paddle_engine = PaddleOCR(**kwargs)
                    break
                except Exception as exc:
                    last_exc = exc
                    continue
            if _paddle_engine is None:
                raise RuntimeError(
                    f"PaddleOCR() construction failed: {last_exc}"
                ) from last_exc
            logger.info(
                "ScanX OCR paddle engine constructed (role=%s, paddleocr+paddlepaddle)",
                _engine_role(_ENGINE_PADDLE),
            )
            _emit_progress(on_progress, "PaddleOCR ready — running OCR…")
        return _paddle_engine


def _get_rapid_engine(
    *,
    on_progress: ProgressCallback | None = None,
    optimized: bool = True,
) -> Any:
    global _rapid_engine
    with _rapid_engine_lock:
        if _rapid_engine is None:
            _emit_progress(on_progress, "Loading RapidOCR engine…")
            try:
                from rapidocr import RapidOCR
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore

            box_thresh = float(
                getattr(settings, "SCANX_RAPID_BOX_THRESH", _RAPID_DEFAULT_BOX_THRESH)
                or _RAPID_DEFAULT_BOX_THRESH
            )
            unclip = float(
                getattr(settings, "SCANX_RAPID_UNCLIP_RATIO", _RAPID_DEFAULT_UNCLIP_RATIO)
                or _RAPID_DEFAULT_UNCLIP_RATIO
            )
            text_score = float(
                getattr(settings, "SCANX_RAPID_TEXT_SCORE", _RAPID_DEFAULT_TEXT_SCORE)
                or _RAPID_DEFAULT_TEXT_SCORE
            )

            # Prefer params= (rapidocr ≥1.x). Fall through for older onnxruntime.
            param_attempts: list[dict[str, Any]] = []
            if optimized:
                param_attempts.append(
                    {
                        "Global.use_cls": True,
                        "Global.text_score": text_score,
                        "Global.max_side_len": _RAPID_GLOBAL_MAX_SIDE_LEN,
                        "Det.limit_side_len": _RAPID_DET_LIMIT_SIDE_LEN,
                        "Det.thresh": 0.3,
                        "Det.box_thresh": box_thresh,
                        "Det.unclip_ratio": unclip,
                        "Det.use_dilation": True,
                        "Engine.intra_op_num_threads": 1,
                        "Engine.inter_op_num_threads": 1,
                    }
                )
            param_attempts.append(
                {
                    "Det.limit_side_len": _RAPID_DET_LIMIT_SIDE_LEN,
                    "Global.max_side_len": _RAPID_GLOBAL_MAX_SIDE_LEN,
                    "Global.use_cls": True,
                }
            )

            last_exc: Exception | None = None
            for params in param_attempts:
                try:
                    _rapid_engine = RapidOCR(params=params)
                    last_exc = None
                    break
                except TypeError as exc:
                    last_exc = exc
                    continue
                except Exception as exc:
                    last_exc = exc
                    continue
            if _rapid_engine is None:
                try:
                    _rapid_engine = RapidOCR()
                except Exception as exc:
                    raise RuntimeError(
                        f"RapidOCR() construction failed: {last_exc or exc}"
                    ) from exc
            logger.info(
                "ScanX OCR rapid engine constructed (role=%s, rapidocr/onnxruntime optimized=%s) "
                "det_limit_side_len=%s max_side_len=%s box_thresh=%s unclip=%s text_score=%s",
                _engine_role(_ENGINE_RAPID),
                optimized,
                _RAPID_DET_LIMIT_SIDE_LEN,
                _RAPID_GLOBAL_MAX_SIDE_LEN,
                box_thresh,
                unclip,
                text_score,
            )
        return _rapid_engine


def _page_text_from_blocks_or_lines(
    blocks: list[OcrTextBlock],
    fallback_lines: list[str],
) -> str | None:
    """Prefer spatially ordered block text; fall back to legacy line join."""
    ordered = blocks_to_reading_text(blocks)
    if ordered:
        return ordered
    if fallback_lines:
        return "\n".join(fallback_lines)
    return None


def _finalize_ocr_blocks(
    blocks: list[OcrTextBlock],
    *,
    fallback_text: str | None = None,
    on_progress: ProgressCallback | None = None,
    image_bytes: bytes | None = None,
) -> tuple[str | None, list[OcrTextBlock], list[dict[str, str]], list[dict[str, Any]]]:
    """Post spatial-sort: garbage filter → Ollama clean → grid → marks schema.

    Called after the OCR engine Future completes so cleaner latency does not
    burn the engine timeout slice (cleaner has its own timeout setting).
    """
    table_regions: list[dict[str, Any]] = []
    if image_bytes:
        try:
            table_regions = detect_table_regions_from_image(image_bytes)
        except Exception:
            table_regions = []

    if blocks:
        _emit_progress(on_progress, "OCR cleanup (Ollama)…")
        cleaned, cleaner_marks = clean_ocr_blocks_with_marks(blocks)
        annotate_blocks_with_grid(cleaned)
        # Prefer table-aware join so Theory/Practical/Total columns stay aligned.
        text = blocks_to_reading_text_with_tables(cleaned) or blocks_to_reading_text(
            cleaned
        )
        page_text = text or fallback_text
        marks: list[dict[str, str]] = []
        try:
            marks = structure_marks_from_ocr(
                text=page_text,
                blocks=cleaned,
                cleaner_marks=cleaner_marks,
            )
        except Exception:
            logger.debug("ScanX marks structuring failed", exc_info=True)
            marks = cleaner_marks or []
        return page_text, cleaned, marks, table_regions
    if fallback_text:
        _emit_progress(on_progress, "OCR cleanup (Ollama)…")
        cleaned_text = clean_ocr_text(fallback_text) or fallback_text
        marks = []
        try:
            marks = structure_marks_from_ocr(text=cleaned_text, blocks=None)
        except Exception:
            marks = []
        return cleaned_text, [], marks, table_regions
    return None, [], [], table_regions


def _run_paddle_on_frames(
    frames: list[Any],
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, list[OcrTextBlock]]:
    import numpy as np

    engine = _get_paddle_engine(on_progress=on_progress)
    page_texts: list[str] = []
    all_blocks: list[OcrTextBlock] = []
    total = len(frames) or 1
    for idx, frame in enumerate(frames, start=1):
        if is_cancel_requested():
            raise ScanxJobCancelled()
        _emit_progress(on_progress, f"PaddleOCR page {idx}/{total}…")
        arr = np.asarray(frame)
        out: Any = None
        if hasattr(engine, "predict"):
            try:
                out = engine.predict(arr)
            except Exception as exc:
                # Do not treat as success — fall through to classic ocr() / empty→Rapid.
                logger.warning(
                    "ScanX Paddle predict() failed on frame %s/%s: %s",
                    idx,
                    total,
                    exc,
                )
                out = None
        if out is None and hasattr(engine, "ocr"):
            try:
                out = engine.ocr(arr, cls=True)
            except TypeError:
                out = engine.ocr(arr)
            except Exception as exc:
                logger.warning(
                    "ScanX Paddle ocr() failed on frame %s/%s: %s",
                    idx,
                    total,
                    exc,
                )
                out = None
        page_index = idx - 1
        blocks = sort_ocr_boxes_by_reading_order(
            blocks_from_paddle_output(
                out, page_index=page_index, id_prefix=f"p{page_index}"
            ),
            layout="document",
        )
        all_blocks.extend(blocks)
        page_text = _page_text_from_blocks_or_lines(
            blocks, _texts_from_paddle_output(out)
        )
        if page_text:
            page_texts.append(page_text)
    return "\n\n".join(page_texts).strip(), all_blocks


def _run_rapid_on_frames(
    frames: list[Any],
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, list[OcrTextBlock]]:
    import numpy as np

    engine = get_optimized_rapidocr_engine(on_progress=on_progress)
    call_kwargs = _rapid_runtime_kwargs()
    page_texts: list[str] = []
    all_blocks: list[OcrTextBlock] = []
    total = len(frames) or 1
    for idx, frame in enumerate(frames, start=1):
        if is_cancel_requested():
            raise ScanxJobCancelled()
        _emit_progress(on_progress, f"RapidOCR page {idx}/{total}…")
        arr = np.asarray(frame)
        try:
            out = engine(arr, **call_kwargs)
        except TypeError:
            # Older rapidocr-onnxruntime may not accept box_thresh/unclip kwargs.
            try:
                out = engine(arr, use_cls=True)
            except TypeError:
                out = engine(arr)
        page_index = idx - 1
        blocks = sort_ocr_boxes_by_reading_order(
            blocks_from_rapid_output(
                out, page_index=page_index, id_prefix=f"p{page_index}"
            ),
            layout="form",
        )
        all_blocks.extend(blocks)
        page_text = _page_text_from_blocks_or_lines(
            blocks, _texts_from_rapid_output(out)
        )
        if page_text:
            page_texts.append(page_text)
    return "\n\n".join(page_texts).strip(), all_blocks


def _probe_engine_import(engine_name: str) -> None:
    if engine_name == _ENGINE_PADDLE:
        _probe_paddle()
        return
    if engine_name == _ENGINE_RAPID:
        try:
            import rapidocr  # noqa: F401
        except ImportError:
            import rapidocr_onnxruntime  # noqa: F401
        return
    raise ImportError(f"Unknown OCR engine: {engine_name}")


def _run_engine(
    engine_name: str,
    frames: list[Any],
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, list[OcrTextBlock]]:
    if engine_name == _ENGINE_PADDLE:
        return _run_paddle_on_frames(frames, on_progress=on_progress)
    if engine_name == _ENGINE_RAPID:
        return _run_rapid_on_frames(frames, on_progress=on_progress)
    raise ValueError(f"Unknown OCR engine: {engine_name}")


def _try_engine(
    engine_name: str,
    frames: list[Any],
    *,
    timeout_seconds: float,
    on_progress: ProgressCallback | None = None,
) -> tuple[str | None, str, str | None, list[OcrTextBlock]]:
    """Run one engine under a wall-clock timeout.

    Returns ``(text_or_none, note, error_detail, blocks)`` where note is
    ocr_ok|ocr_empty|ocr_timeout|ocr_failed|ocr_unavailable.
    """
    empty_blocks: list[OcrTextBlock] = []
    try:
        _probe_engine_import(engine_name)
    except ImportError as exc:
        detail = str(exc) or repr(exc)
        logger.warning(
            "ScanX OCR engine %s unavailable — will fall back if configured. Detail: %s",
            engine_name,
            detail,
        )
        return None, "ocr_unavailable", detail, empty_blocks

    if timeout_seconds <= 0.5:
        return (
            None,
            "ocr_timeout",
            f"{engine_name}_timeout_budget_exhausted",
            empty_blocks,
        )

    # Fresh executor per attempt so a timed-out Paddle model download cannot
    # permanently occupy a shared worker and block Rapid fallback forever.
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"scanx-ocr-{engine_name}"
    )
    acquired = _ocr_run_slots.acquire(blocking=False)
    if not acquired:
        _emit_progress(on_progress, "Waiting for OCR slot…")
        wait_cap = _ocr_slot_stuck_wait_sec(timeout_seconds)
        wait_t0 = time.perf_counter()
        deadline = time.monotonic() + wait_cap
        while True:
            if is_cancel_requested():
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                raise ScanxJobCancelled()
            remaining_wait = deadline - time.monotonic()
            if remaining_wait <= 0:
                waited_ms = int((time.perf_counter() - wait_t0) * 1000)
                add_job_wait_ms(waited_ms)
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                logger.warning(
                    "ScanX OCR slot appears stuck after %.1fs engine=%s",
                    wait_cap,
                    engine_name,
                )
                return None, "ocr_timeout", "ocr_slot_wait_timeout", empty_blocks
            got = _ocr_run_slots.acquire(timeout=min(5.0, remaining_wait))
            if got:
                acquired = True
                waited_ms = int((time.perf_counter() - wait_t0) * 1000)
                add_job_wait_ms(waited_ms)
                break
            elapsed_wait = int(time.perf_counter() - wait_t0)
            _emit_progress(
                on_progress,
                f"Waiting for OCR slot… {elapsed_wait}s",
            )

    stop_hb = threading.Event()
    release_slot = True

    def _heartbeat() -> None:
        tick = 0
        try:
            while not stop_hb.wait(15.0):
                tick += 1
                _emit_progress(
                    on_progress,
                    f"{engine_name} OCR running… {tick * 15}s",
                )
        except ScanxJobCancelled:
            return

    hb_thread = threading.Thread(
        target=_heartbeat,
        name=f"scanx-ocr-hb-{engine_name}",
        daemon=True,
    )
    hb_thread.start()
    text = ""
    blocks: list[OcrTextBlock] = []
    try:
        # Engine construction (model download / ONNX load) must not burn the
        # inference slice — especially Paddle cold-start on CPU mark sheets.
        if engine_name == _ENGINE_RAPID and _rapid_engine is None:
            _emit_progress(on_progress, "Loading RapidOCR engine…")
            try:
                init_future = executor.submit(_get_rapid_engine, on_progress=on_progress)
                init_future.result(timeout=max(8.0, min(25.0, timeout_seconds * 0.5)))
            except FuturesTimeout:
                logger.warning("ScanX OCR Rapid engine init timed out")
                return None, "ocr_timeout", "rapid_init_timeout", empty_blocks
            except ScanxJobCancelled:
                raise
            except Exception as exc:
                logger.exception("ScanX OCR Rapid engine init failed: %s", exc)
                return (
                    None,
                    "ocr_unavailable",
                    f"rapid_init_{type(exc).__name__}: {exc}",
                    empty_blocks,
                )
        elif engine_name == _ENGINE_PADDLE and _paddle_engine is None:
            _emit_progress(on_progress, "Loading PaddleOCR engine…")
            try:
                # Allow generous init (cached models ~10–40s; first download longer).
                init_cap = max(45.0, min(120.0, timeout_seconds * 0.6))
                init_future = executor.submit(
                    _get_paddle_engine, on_progress=on_progress
                )
                init_future.result(timeout=init_cap)
            except FuturesTimeout:
                logger.warning("ScanX OCR Paddle engine init timed out")
                return None, "ocr_timeout", "paddle_init_timeout", empty_blocks
            except ScanxJobCancelled:
                raise
            except Exception as exc:
                logger.exception("ScanX OCR Paddle engine init failed: %s", exc)
                return (
                    None,
                    "ocr_unavailable",
                    f"paddle_init_{type(exc).__name__}: {exc}",
                    empty_blocks,
                )

        # Never inflate past the caller's allocated share — floors used to force
        # Rapid≥15s / Paddle≥30s, then grant another 35s to fallback and double
        # the CPU load (orphaned primary thread + fallback) → APScheduler misses.
        infer_timeout = max(0.5, float(timeout_seconds))

        future = executor.submit(
            _run_engine, engine_name, frames, on_progress=on_progress
        )
        try:
            text, blocks = future.result(timeout=infer_timeout)
        except FuturesTimeout:
            logger.warning(
                "ScanX OCR (%s) timed out after %.1fs (%s frame(s))",
                engine_name,
                infer_timeout,
                len(frames),
            )
            # Hold the OCR slot until the abandoned worker finishes so fallback
            # does not run concurrent Rapid+Paddle on the same CPU.
            release_slot = False

            def _drain_and_release() -> None:
                try:
                    future.result(timeout=180.0)
                except Exception:
                    pass
                finally:
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    _ocr_run_slots.release()

            threading.Thread(
                target=_drain_and_release,
                name=f"scanx-ocr-drain-{engine_name}",
                daemon=True,
            ).start()
            return (
                None,
                "ocr_timeout",
                f"{engine_name}_timeout_{infer_timeout:.0f}s",
                empty_blocks,
            )
        except ScanxJobCancelled:
            raise
        except Exception as exc:
            logger.exception("ScanX OCR (%s) failed: %s", engine_name, exc)
            return (
                None,
                "ocr_failed",
                f"{engine_name}_{type(exc).__name__}: {exc}",
                empty_blocks,
            )
    finally:
        stop_hb.set()
        if release_slot:
            _ocr_run_slots.release()
            # Do not wait=True: a hung Paddle download must not block forever.
            executor.shutdown(wait=False, cancel_futures=True)

    cleaned = (text or "").strip() or None
    if cleaned:
        logger.info("ScanX OCR succeeded with engine=%s", engine_name)
        return cleaned, "ocr_ok", None, list(blocks or [])
    logger.info("ScanX OCR engine=%s returned empty text", engine_name)
    return None, "ocr_empty", f"{engine_name}_empty_text", list(blocks or [])


def _resolve_engine_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = str(raw).strip().lower()
    if name in {"rapidocr", "rapid-ocr", _ENGINE_RAPID}:
        return _ENGINE_RAPID
    if name in {"paddleocr", "paddle-ocr", _ENGINE_PADDLE}:
        return _ENGINE_PADDLE
    return name if name in _KNOWN_ENGINES else None


def extract_text_from_image(
    content: bytes | str | Path,
    *,
    timeout_seconds: float | None = None,
    force_engine: str | None = None,
    prefer_engine: str | None = None,
    on_progress: ProgressCallback | None = None,
    _after_slot_wait_retry: bool = False,
) -> OcrResult:
    """OCR PNG/JPEG/TIFF bytes or a filesystem path.

    Tries ``SCANX_OCR_ENGINE`` first (or ``force_engine`` / ``prefer_engine``);
    on ImportError / runtime failure / empty result / timeout, tries
    ``SCANX_OCR_FALLBACK`` within a reserved budget slice (primary cannot
    consume 100% of the wall clock). Fallback engine is pre-warmed while
    primary runs. Always returns; never raises to the worker.

    ``prefer_engine`` sets primary but keeps a fallback (the other engine /
    configured fallback). ``force_engine`` disables fallback entirely.
    Enhanced scans typically pass ``prefer_engine="rapid"``.

    When every engine attempt fails solely because the OCR slot wait timed out
    (peer held the slot — ``ocr_slot_wait_timeout``), retries **once** after the
    slot is free. Waiting on a live slot remains queue time; this retry is only
    after an actual timeout. Does not loop. Does not re-OCR when text was
    already returned.

    Metrics callers should persist ``engine``, ``fallback_reason``, and
    ``primary_engine`` so counsellors can see Rapid vs Paddle.
    """
    t0 = time.perf_counter()
    budget = float(timeout_seconds) if timeout_seconds is not None else ocr_budget_seconds()
    if force_engine:
        name = force_engine.strip().lower()
        if name in {"rapidocr", "rapid-ocr"}:
            primary = _ENGINE_RAPID
        elif name in {"paddleocr", "paddle-ocr"}:
            primary = _ENGINE_PADDLE
        else:
            primary = name if name in _KNOWN_ENGINES else configured_ocr_engine()
        fallback = None  # forced path: no silent switch
    elif prefer_engine:
        preferred = _resolve_engine_name(prefer_engine) or configured_ocr_engine()
        primary = preferred
        # Keep fallback available: configured fallback if different, else the
        # other known engine (enhanced scans: Rapid primary → Paddle fallback).
        configured_fb = configured_ocr_fallback()
        if configured_fb and configured_fb != primary:
            fallback = configured_fb
        elif primary == _ENGINE_RAPID:
            fallback = _ENGINE_PADDLE
        elif primary == _ENGINE_PADDLE:
            fallback = _ENGINE_RAPID
        else:
            fallback = None
    else:
        primary = configured_ocr_engine()
        fallback = configured_ocr_fallback()
        if fallback == primary:
            fallback = None

    def _fail(note: str, engine: str = primary, reason: str | None = None) -> OcrResult:
        return OcrResult(
            text=None,
            engine=engine,
            note=note,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            page_count=0,
            fallback_reason=reason,
            primary_engine=primary,
        )

    try:
        raw = _normalize_image_input(content)
    except Exception as exc:
        logger.info("ScanX OCR could not read image input: %s", exc)
        return _fail("ocr_failed", reason=str(exc))

    if not raw:
        return _fail("ocr_empty")

    try:
        frames = _pil_frames(raw)
    except Exception as exc:
        logger.info("ScanX OCR could not open image: %s", exc)
        return _fail("ocr_failed", reason=str(exc))

    engines: list[str] = [primary]
    if fallback:
        engines.append(fallback)

    last_note = "ocr_unavailable"
    last_engine = primary
    last_detail: str | None = None
    primary_fail_detail: str | None = None
    # Keep a slice of the wall-clock budget for the fallback engine.
    reserve = _fallback_reserve_seconds(budget) if fallback else 0.0

    # Pre-warm fallback while primary runs so fallback init is not charged
    # against the reserved slice after a primary timeout.
    if fallback and fallback != primary:
        threading.Thread(
            target=_warm_engine,
            args=(fallback,),
            name=f"scanx-ocr-warm-{fallback}",
            daemon=True,
        ).start()

    for idx, engine_name in enumerate(engines):
        if is_cancel_requested():
            raise ScanxJobCancelled()
        elapsed = time.perf_counter() - t0
        remaining = budget - elapsed
        has_more = idx + 1 < len(engines)

        if has_more:
            # Cap primary so the reserved slice is still available afterward.
            primary_share = max(0.5, budget - reserve)
            engine_timeout = primary_share - elapsed
            if engine_timeout <= 0.5:
                logger.warning(
                    "ScanX OCR primary share exhausted before %s; skipping to %s",
                    engine_name,
                    engines[idx + 1],
                )
                primary_fail_detail = primary_fail_detail or "primary_share_exhausted"
                last_detail = "primary_share_exhausted"
                continue
        else:
            # Last engine (fallback or sole): use remaining time only — never invent
            # a 35–60s grant past the caller's wall budget (that starved APScheduler).
            engine_timeout = remaining
            if idx > 0 and engine_timeout < reserve and remaining > 0:
                engine_timeout = min(reserve, remaining)
            if idx > 0 and remaining <= 0.5:
                logger.warning(
                    "ScanX OCR skipping fallback %s — primary %s used the full budget (%s)",
                    engine_name,
                    primary,
                    primary_fail_detail,
                )
                last_detail = f"{primary}_exhausted_budget_no_fallback"
                break

        text, note, detail, blocks = _try_engine(
            engine_name,
            frames,
            timeout_seconds=max(0.5, engine_timeout),
            on_progress=on_progress,
        )
        last_note = note
        last_engine = engine_name
        last_detail = detail
        if idx == 0 and note != "ocr_ok":
            primary_fail_detail = detail or note

        if text:
            used_fallback = engine_name != primary
            if used_fallback:
                reason = (
                    f"{primary}->{engine_name}: {primary_fail_detail or 'primary_failed'}"
                )
                logger.warning(
                    "ScanX OCR fallback: primary=%s failed (%s); using engine=%s",
                    primary,
                    primary_fail_detail,
                    engine_name,
                )
            else:
                reason = None
            # Spatial sort already done inside the engine run; Ollama cleanup
            # runs here (outside the engine Future timeout).
            cleaned_text, cleaned_blocks, marks, table_regions = _finalize_ocr_blocks(
                list(blocks or []),
                fallback_text=text,
                on_progress=on_progress,
                image_bytes=raw,
            )
            return OcrResult(
                text=cleaned_text or text,
                engine=engine_name,
                note="ocr_ok",
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                page_count=len(frames),
                fallback_reason=reason,
                primary_engine=primary,
                blocks=list(cleaned_blocks or []),
                marks=list(marks or []),
                table_regions=list(table_regions or []),
            )
        # Empty / fail / unavailable / timeout → try next engine within reserved budget.
        if note == "ocr_timeout" and has_more:
            logger.warning(
                "ScanX OCR falling back from %s after timeout -> %s",
                engine_name,
                engines[idx + 1],
            )
        elif note in {"ocr_unavailable", "ocr_failed", "ocr_empty"} and has_more:
            logger.warning(
                "ScanX OCR falling back from %s (%s: %s) -> %s",
                engine_name,
                note,
                detail,
                engines[idx + 1],
            )

    if fallback and last_engine == primary and primary_fail_detail:
        # Fallback never produced text (and may never have been attempted).
        reason = (
            f"{primary}->{fallback}_skipped_or_failed: "
            f"{primary_fail_detail or last_detail or last_note}"
        )
    elif last_engine != primary or primary_fail_detail:
        reason = (
            f"{primary}->{last_engine}: {primary_fail_detail or last_detail or last_note}"
        )
    else:
        reason = last_detail

    # One retry after OCR slot wait timeout (peer held the slot). Waiting on a
    # live slot is queue time; this fires only after an actual wait timeout.
    # Do not loop. Do not retry when text was already returned above.
    slot_wait_hit = (
        last_note == "ocr_timeout"
        and (
            last_detail == "ocr_slot_wait_timeout"
            or "ocr_slot_wait_timeout" in str(primary_fail_detail or "")
            or "ocr_slot_wait_timeout" in str(reason or "")
        )
    )
    if slot_wait_hit and not _after_slot_wait_retry:
        logger.warning(
            "ScanX OCR slot wait timed out — retrying once after slot is free"
        )
        _emit_progress(on_progress, "Retrying OCR after slot wait timeout…")
        retried = extract_text_from_image(
            content,
            timeout_seconds=timeout_seconds,
            force_engine=force_engine,
            prefer_engine=prefer_engine,
            on_progress=on_progress,
            _after_slot_wait_retry=True,
        )
        if retried.note == "ocr_ok":
            retry_reason = (
                f"ocr_slot_wait_timeout_retry_ok:{retried.engine}"
                if not retried.fallback_reason
                else f"ocr_slot_wait_timeout_retry: {retried.fallback_reason}"
            )
        elif retried.fallback_reason:
            retry_reason = f"ocr_slot_wait_timeout_retry: {retried.fallback_reason}"
        else:
            retry_reason = "ocr_slot_wait_timeout_retry"
        return OcrResult(
            text=retried.text,
            engine=retried.engine,
            note=retried.note,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            page_count=retried.page_count,
            fallback_reason=retry_reason,
            primary_engine=retried.primary_engine or primary,
            blocks=list(retried.blocks or []),
            marks=list(retried.marks or []),
            table_regions=list(retried.table_regions or []),
        )

    return OcrResult(
        text=None,
        engine=last_engine,
        note=last_note,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
        page_count=len(frames),
        fallback_reason=reason,
        primary_engine=primary,
    )
