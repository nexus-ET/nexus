"""Post-OCR cleanup for ScanX via local Ollama (official ``ollama`` package).

Runs after RapidOCR/Paddle spatial sorting. Preserves ``raw_ocr_text`` for
audit, writes ``cleaned_text`` for embeddings/parse, and never fails the OCR
job — Ollama errors fall back to raw (or light regex) text.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

from app.config import settings
from app.services.ai_providers import parse_model_ref
from app.services.scanx_ocr_blocks import OcrTextBlock

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You clean noisy OCR text from academic documents (marksheets, transcripts). "
    "Return ONLY valid JSON: "
    '{"blocks":[{"block_id":"string","cleaned_text":"string"}],'
    '"marks":[{"subject":"string","theory":"string","prac":"string",'
    '"total":"string","words":"string"}]} . '
    "For each input block: remove noise characters, stray punctuation, and "
    "meaningless symbols (#, |, *, scanner grain artifacts). "
    "Correct obvious OCR misreadings using context. "
    "REJECT gibberish: if a block is meaningless multi-word fragments, broken "
    "character clusters, or not a valid dictionary/academic term (examples: "
    "'Ciamr aGwrium', 'Epulona Glowes', 'ulona Gloweos'), set cleaned_text to "
    "an empty string \"\". "
    "Drop unmapped non-English garbage (misread Tamil/unicode Latin soup). "
    "Keep valid English labels and intentional local-script subject names only "
    "when they are clear (e.g. real Tamil script), not corrupted Latin fragments. "
    "Do NOT alter numbers, names, grades, marks, roll numbers, dates, or other "
    "structural academic values. "
    "Preserve certificate labels exactly when readable "
    "(e.g. keep TMR CODE NO — do not drop the leading T into MR CODE NO). "
    "Maintain layout intent (keep each block's "
    "content as a single line; do not merge or split blocks). "
    "When the page is a marksheet, also fill marks[] with one row per subject: "
    "subject name, theory, prac (practical / Prac / Pracal OCR), total, and "
    "optional English number-words for the total (e.g. ONE SIX NINE). "
    "Return one cleaned entry per input block_id. If a block needs no change, "
    "echo the original text as cleaned_text."
)

# Conservative noise strip — keep letters (incl. Tamil etc.), digits, common punct.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_MULTI_PIPE_RE = re.compile(r"[|]{2,}")
_MULTI_HASH_STAR_RE = re.compile(r"[#*]{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
# Scanner grain / isolated symbol soup (keep single ., -, / used in dates).
_SYMBOL_SOUP_RE = re.compile(r"(?:^| )[^\w\s./\-–—:]{2,}(?= |$)")
_LEADING_JUNK_RE = re.compile(r"^[^A-Za-z0-9\u0080-\uffff]{1,6}(?=[A-Za-z0-9\u0080-\uffff])")
# Mid-word capital / camel OCR junk ("aGwrium").
_MID_CAP_RE = re.compile(r"[a-z][A-Z]")
# Rare digraphs / signature-block OCR soup stems.
_GIBBERISH_STEM_RE = re.compile(
    r"(?i)(?:ciamr|agwrium|epulona|glowe[so]?|ulona|gloweos|gwrium|"
    r"cerniidt|gumi|crour|as\s+iulag|cgrqou)"
)
_KEEP_TWO_TOKEN_RE = re.compile(
    r"(?i)\b(?:school|board|college|jesus|infant|higher|secondary|state|"
    r"member|secretary|department|government|examination|certificate|"
    r"tamil|english|physics|chemistry|biology|mathematics|science|"
    r"accountancy|economics|commerce|history|geography)\b"
)


def is_ocr_gibberish_line(text: str | None) -> bool:
    """Deterministic reject for signature/stamp OCR soup (even when Ollama is down)."""
    s = (text or "").strip()
    if not s or len(s) > 64:
        return False
    # Keep digits / codes / dates.
    if re.search(r"\d", s):
        return False
    if _KEEP_TWO_TOKEN_RE.search(s):
        return False
    if _MID_CAP_RE.search(s):
        return True
    if _GIBBERISH_STEM_RE.search(s):
        return True
    # Proper Title Case pairs (possible real names): only stem/rare digraph reject.
    if re.fullmatch(r"[A-Z][a-z]{3,13}\s+[A-Z][a-z]{3,13}", s):
        return bool(
            re.search(r"(?i)(?:gw|kq|xz|zx|qq|vv|jx|qx|vz|pz)", s)
        )
    # Mixed / lower two-token fragments (signature OCR soup).
    if re.fullmatch(r"[A-Za-z]{4,14}\s+[A-Za-z]{4,14}", s) and not s.isupper():
        vowels = sum(1 for c in s.lower() if c in "aeiou")
        if vowels <= 4:
            return True
        if re.search(r"(?i)(?:gw|kq|xz|zx|qq|vv|jx|qx|vz)", s):
            return True
    return False


def _ollama_native_host() -> str:
    configured = (
        settings.OLLAMA_BASE_URL
        or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    )
    return configured.rstrip("/").removesuffix("/v1")


def light_regex_clean(text: str) -> str:
    """Cheap fallback when Ollama is unavailable — deterministic junk reduction."""
    t = _CTRL_RE.sub("", text or "")
    t = _CJK_RE.sub("", t)
    t = _MULTI_PIPE_RE.sub(" ", t)
    t = _MULTI_HASH_STAR_RE.sub("", t)
    t = _SYMBOL_SOUP_RE.sub(" ", t)
    t = _LEADING_JUNK_RE.sub("", t)
    t = _MULTI_SPACE_RE.sub(" ", t)
    t = t.strip()
    if is_ocr_gibberish_line(t):
        return ""
    return t


def _ensure_raw_fields(blocks: list[OcrTextBlock]) -> None:
    for blk in blocks:
        raw = (getattr(blk, "raw_ocr_text", None) or "").strip()
        if not raw:
            # Legacy blocks that only had ``text``.
            legacy = getattr(blk, "cleaned_text", None) or ""
            raw = str(legacy).strip()
            blk.raw_ocr_text = raw
        if not (getattr(blk, "cleaned_text", None) or "").strip():
            blk.cleaned_text = raw


def _apply_light_fallback(blocks: list[OcrTextBlock]) -> list[OcrTextBlock]:
    _ensure_raw_fields(blocks)
    for blk in blocks:
        raw = blk.raw_ocr_text or ""
        if is_ocr_gibberish_line(raw):
            blk.cleaned_text = ""
        else:
            blk.cleaned_text = light_regex_clean(raw) or raw
    return blocks


def _parse_cleaned_payload(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    if not isinstance(data, dict):
        return {}
    rows = data.get("blocks")
    if not isinstance(rows, list):
        return {}
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        bid = str(row.get("block_id") or "").strip()
        cleaned = row.get("cleaned_text")
        if cleaned is None:
            cleaned = row.get("text")
        if not bid or cleaned is None:
            continue
        out[bid] = str(cleaned).strip()
    return out


def _parse_marks_from_cleaner_payload(raw: str) -> list[dict[str, str]]:
    """Extract optional marks[] from the cleaner JSON response."""
    text = (raw or "").strip()
    if not text:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    rows = data.get("marks")
    if not isinstance(rows, list):
        return []
    try:
        from app.services.scanx_academic_parse import (
            marks_row_to_subject,
            subjects_to_marks,
        )

        subjects = [marks_row_to_subject(r) for r in rows if isinstance(r, dict)]
        return subjects_to_marks(subjects)
    except Exception:
        out: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            subject = str(row.get("subject") or row.get("name") or "").strip()
            if not subject:
                continue
            item: dict[str, str] = {"subject": subject[:200]}
            for key, alias in (
                ("theory", "theory"),
                ("prac", "prac"),
                ("practical", "prac"),
                ("total", "total"),
                ("marks", "total"),
                ("words", "words"),
            ):
                val = str(row.get(key) or "").strip()
                if val and alias not in item:
                    item[alias] = val[:120]
            out.append(item)
        return out[:60]


def _blocks_payload(blocks: list[OcrTextBlock], *, max_chars: int = 8000) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    used = 0
    for blk in blocks:
        raw = (blk.raw_ocr_text or "").strip()
        if not raw:
            continue
        entry = {"block_id": blk.block_id, "text": raw}
        size = len(raw) + len(blk.block_id) + 24
        if used + size > max_chars and payload:
            break
        payload.append(entry)
        used += size
    return payload


def _cleaned_preserves_structure(raw: str, cleaned: str) -> bool:
    """Reject Ollama edits that drop letters from short academic labels (TMR→MR).

    Empty cleaned_text is allowed when the raw block is gibberish (anomaly drop).
    """
    raw_s = (raw or "").strip()
    clean_s = (cleaned or "").strip()
    if not clean_s:
        # Allow explicit empty only for gibberish / after light strip empties.
        return is_ocr_gibberish_line(raw_s) or not light_regex_clean(raw_s)
    if len(raw_s) <= 48 and re.search(r"(?i)\bcode\s*no", raw_s):
        # Keep letter runs of length ≥2 from the raw label (TMR, CODE, NO).
        raw_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{2,}", raw_s)}
        clean_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{2,}", clean_s)}
        if "tmr" in raw_tokens and "tmr" not in clean_tokens and "mr" in clean_tokens:
            return False
    # Never allow cleaned text to drop all digits when raw had digits (marks/codes).
    if re.search(r"\d", raw_s) and not re.search(r"\d", clean_s) and len(raw_s) <= 24:
        return False
    # Reject if model invented more gibberish.
    if is_ocr_gibberish_line(clean_s):
        return False
    return True


def _chat_via_http(
    *,
    host: str,
    model_id: str,
    user_content: str,
    timeout: float,
) -> str | None:
    """Native Ollama /api/chat when the ``ollama`` package is not installed."""
    chat_url = f"{host.rstrip('/')}/api/chat"
    body = json.dumps(
        {
            "model": model_id,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 2048},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_content},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        chat_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        logger.warning(
            "ScanX OCR cleaner HTTP failed model=%s host=%s: %s",
            model_id,
            host,
            exc,
        )
        return None
    message = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(message, dict):
        return str(message.get("content") or "") or None
    return None


def _chat_clean_blocks(
    blocks: list[OcrTextBlock],
) -> tuple[dict[str, str] | None, list[dict[str, str]], str | None]:
    """Call Ollama chat; return (block map | None, marks[], raw content)."""
    if not getattr(settings, "SCANX_OCR_CLEANER_ENABLED", True):
        logger.info("ScanX OCR cleaner disabled via SCANX_OCR_CLEANER_ENABLED")
        return None, [], None

    model_ref = (
        getattr(settings, "SCANX_OCR_CLEANER_MODEL", None)
        or getattr(settings, "SCANX_LLM_MODEL", None)
        or settings.INTEL_AI_MODEL
        or "ollama:llama3.2"
    )
    provider, model_id = parse_model_ref(model_ref)
    if provider != "ollama" or not model_id:
        logger.info(
            "ScanX OCR cleaner skipped — provider=%s model=%s (ollama required)",
            provider,
            model_id,
        )
        return None, [], None

    payload_blocks = _blocks_payload(blocks)
    if not payload_blocks:
        return {}, [], None

    timeout = float(getattr(settings, "SCANX_OCR_CLEANER_TIMEOUT_SECONDS", 30.0) or 30.0)
    host = _ollama_native_host()
    user_content = (
        "Clean these OCR blocks and extract marksheet rows when present. "
        "Return JSON with the same block_ids and optional marks[] "
        "(subject, theory, prac, total, words):\n\n"
        + json.dumps({"blocks": payload_blocks}, ensure_ascii=False)
    )

    content: str | None = None
    try:
        from ollama import Client

        try:
            client = Client(host=host, timeout=timeout)
            response = client.chat(
                model=model_id,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                format="json",
                options={"temperature": 0.0, "num_predict": 2048},
            )
            if isinstance(response, dict):
                content = (response.get("message") or {}).get("content") or ""
            else:
                message = getattr(response, "message", None)
                content = getattr(message, "content", None) or ""
        except Exception:
            logger.warning(
                "ScanX OCR cleaner Client.chat failed model=%s host=%s; trying HTTP",
                model_id,
                host,
                exc_info=True,
            )
            content = None
    except ImportError:
        logger.info(
            "ScanX OCR cleaner: ollama package missing — using HTTP /api/chat at %s",
            host,
        )

    if not (content or "").strip():
        content = _chat_via_http(
            host=host,
            model_id=model_id,
            user_content=user_content,
            timeout=timeout,
        )

    if not (content or "").strip():
        logger.warning(
            "ScanX OCR cleaner empty/unavailable model=%s host=%s — light regex fallback",
            model_id,
            host,
        )
        return None, [], None

    mapped = _parse_cleaned_payload(str(content))
    marks = _parse_marks_from_cleaner_payload(str(content))
    if not mapped:
        logger.warning("ScanX OCR cleaner unparseable response model=%s", model_id)
        return None, marks, str(content)
    logger.info(
        "ScanX OCR cleaner model=%s cleaned=%s/%s marks=%s",
        model_id,
        len(mapped),
        len(payload_blocks),
        len(marks),
    )
    return mapped, marks, str(content)


def clean_ocr_blocks(
    blocks: list[OcrTextBlock] | None,
    *,
    raw_page_text: str | None = None,
) -> list[OcrTextBlock]:
    """Clean spatially sorted OCR blocks in place (and return the same list).

    Low-confidence flags, bounding boxes, and block_ids are preserved.
    ``cleaned_text`` is used for embeddings; ``raw_ocr_text`` stays original.
    """
    cleaned, _marks = clean_ocr_blocks_with_marks(blocks, raw_page_text=raw_page_text)
    return cleaned


def _blocks_look_like_passport(blocks: list[OcrTextBlock]) -> bool:
    """True when OCR already shows a TD3 MRZ / Indian passport page-2 labels.

    Skip the marksheet Ollama cleaner on identity pages — it rewrites labels
    non-deterministically (Father/Guardian, Date of Issue, Spouse).
    """
    hits = 0
    for blk in blocks:
        raw = str(blk.raw_ocr_text or blk.cleaned_text or "")
        compact = re.sub(r"\s+", "", raw.upper())
        if compact.startswith("P<") and "<<" in compact:
            return True
        if re.search(r"[A-Z]\d{7}<[A-Z0-9<]{12,}", compact):
            return True
        low = raw.lower()
        if re.search(r"name of (?:father|mother|spouse)|legal guard", low):
            hits += 1
        if re.search(r"date of (?:issue|lssue|expir)", low):
            hits += 1
        if hits >= 2:
            return True
    return False


def clean_ocr_blocks_with_marks(
    blocks: list[OcrTextBlock] | None,
    *,
    raw_page_text: str | None = None,
) -> tuple[list[OcrTextBlock], list[dict[str, str]]]:
    """Like ``clean_ocr_blocks``, also returning optional Ollama ``marks[]`` rows."""
    del raw_page_text  # reserved for callers that only have page text context
    block_list = list(blocks or [])
    if not block_list:
        return block_list, []

    _ensure_raw_fields(block_list)

    if not getattr(settings, "SCANX_OCR_CLEANER_ENABLED", True):
        _apply_light_fallback(block_list)
        from app.services.scanx_ocr_blocks import drop_garbage_ocr_blocks

        drop_garbage_ocr_blocks(block_list)
        return block_list, []

    # Identity / passport pages: light regex only. The marksheet Ollama
    # cleaner rewrites Father/Guardian/DOI labels differently each run.
    if _blocks_look_like_passport(block_list):
        _apply_light_fallback(block_list)
        from app.services.scanx_ocr_blocks import drop_garbage_ocr_blocks

        drop_garbage_ocr_blocks(block_list)
        return block_list, []

    mapped, marks, _raw = _chat_clean_blocks(block_list)
    if mapped is None:
        _apply_light_fallback(block_list)
        from app.services.scanx_ocr_blocks import drop_garbage_ocr_blocks

        drop_garbage_ocr_blocks(block_list)
        return block_list, marks

    for blk in block_list:
        raw = blk.raw_ocr_text or ""
        # Deterministic pre-filter: drop gibberish from cleaned_text (keep raw).
        if is_ocr_gibberish_line(raw):
            blk.cleaned_text = ""
            continue
        cleaned = mapped.get(blk.block_id)
        if cleaned is not None and not str(cleaned).strip():
            # Model explicitly rejected the block as noise.
            blk.cleaned_text = ""
            continue
        if (
            cleaned is None
            or not str(cleaned).strip()
            or not _cleaned_preserves_structure(raw, str(cleaned))
        ):
            blk.cleaned_text = light_regex_clean(raw) or (
                "" if is_ocr_gibberish_line(raw) else raw
            )
        else:
            # Light pass after LLM to strip residual control/CJK without
            # changing letters/digits the model kept.
            post = light_regex_clean(str(cleaned).strip())
            blk.cleaned_text = post if post is not None else str(cleaned).strip()
            if is_ocr_gibberish_line(blk.cleaned_text):
                blk.cleaned_text = ""
        # Keep review flag / boxes / ids untouched.

    from app.services.scanx_ocr_blocks import drop_garbage_ocr_blocks

    drop_garbage_ocr_blocks(block_list)
    return block_list, marks


def structure_marks_from_ocr(
    *,
    text: str | None,
    blocks: list[OcrTextBlock] | None = None,
    cleaner_marks: list[dict[str, str]] | None = None,
    prior_subjects: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """OCR → spatial/grid → clean → schema map → ``marks[]`` for persistence.

    Deterministic table/heuristic parse is authoritative; Ollama marks fill gaps.
    Graceful when Ollama is down (``cleaner_marks`` empty).
    """
    from app.services.scanx_academic_parse import (
        annotate_subjects_with_ocr_confidence,
        attach_marks_schema,
        marks_row_to_subject,
        merge_subjects,
        parse_subjects_from_table_rows,
        resolve_subjects_from_text,
        subjects_to_marks,
    )
    from app.services.scanx_ocr_blocks import (
        annotate_blocks_with_grid,
        reconstruct_table_matrices,
    )

    block_list = list(blocks or [])
    if block_list:
        annotate_blocks_with_grid(block_list)

    table_subjects: list[dict[str, str]] = []
    for matrix in reconstruct_table_matrices(block_list, annotate=False):
        table_subjects.extend(parse_subjects_from_table_rows(matrix))

    heuristic = resolve_subjects_from_text(
        text,
        use_llm=False,
        prior_subjects=prior_subjects,
    )
    llm_marks_as_subjects = [
        marks_row_to_subject(m) for m in (cleaner_marks or []) if isinstance(m, dict)
    ]
    merged = merge_subjects(table_subjects, heuristic, llm_marks_as_subjects)
    merged = annotate_subjects_with_ocr_confidence(merged, block_list)
    payload = attach_marks_schema({"subjects": merged}, merged)
    return list(payload.get("marks") or subjects_to_marks(merged))


def clean_ocr_text(text: str | None) -> str:
    """Clean a raw OCR string when structured blocks are unavailable."""
    raw = (text or "").strip()
    if not raw:
        return ""

    if not getattr(settings, "SCANX_OCR_CLEANER_ENABLED", True):
        return light_regex_clean(raw) or raw

    # Reuse block path with a single synthetic block.
    synthetic = [
        OcrTextBlock(
            block_id="page-0",
            bounding_box=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            raw_ocr_text=raw,
            cleaned_text=raw,
            confidence=1.0,
            is_low_confidence=False,
            reading_order_index=0,
            page_index=0,
        )
    ]
    cleaned, _marks = clean_ocr_blocks_with_marks(synthetic)
    out = (cleaned[0].cleaned_text if cleaned else "") or light_regex_clean(raw) or raw
    return out.strip()
