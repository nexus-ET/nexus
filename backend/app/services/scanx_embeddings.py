"""Document chunk embeddings for ScanX — reuses EMBEDDING_* provider config only.

Does not write to education_*_embeddings taxonomy tables.
Embeddings are best-effort with a short wall-clock budget so parse jobs
leave Parsing promptly when Ollama/OpenAI is slow or down.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time

from app.config import settings
from app.services.taxonomy_embeddings import (
    EmbeddingUnavailableError,
    _embed_ollama,
    _embed_openai,
    _model_and_expected_dim,
    _resolved_provider,
)

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")
# CJK / fullwidth punctuation from Chinese PP-OCR models misreading Tamil glyphs.
_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# Space-separated short OCR crumbs: "gi a ein", "um u", "C L", "u G 200G".
_FRAG_LINE_RE = re.compile(
    r"(?i)^(?:[a-z]{1,4}|\d{1,4}[a-z]{0,2})(?:\s+(?:[a-z]{1,4}|\d{1,4}[a-z]{0,2})){1,12}$"
)
# Broken letter-spaced words: "i e t i t t tion", "Cerniidt i e t i t t tion".
_SPACED_LETTERS_RE = re.compile(r"(?i)(?:\b[a-z]\s+){3,}[a-z]\b")

# Keep ScanX parse jobs snappy — do not inherit the 120s taxonomy Ollama timeout.
DEFAULT_EMBED_BUDGET_SECONDS = 12.0
DEFAULT_PER_CHUNK_TIMEOUT_SECONDS = 8.0


def normalize_utf8_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.encode("utf-8", errors="replace").decode("utf-8")
    return _WS_RE.sub(" ", text).strip()


def _ocr_line_is_noise(line: str) -> bool:
    """True for RapidOCR garbage lines (Tamil→CJK crumbs, 1–2 letter fragments)."""
    s = (line or "").strip()
    if not s:
        return False
    # Keep numeric / mark / serial lines.
    if re.fullmatch(r"[\d\s.,/\-–—]+", s) and re.search(r"\d", s):
        return False
    # Keep short pure digit codes (register no. fragments).
    if re.fullmatch(r"\d{4,}", s):
        return False
    # Keep TMR / MR / register-style letter+digit codes ("G526345", "A12345").
    # Must run before digit-heavy noise rules (single-letter prefixes yield no
    # [A-Za-z]{2,} "word", so G526345 was incorrectly dropped).
    if re.fullmatch(r"[A-Za-z]\d{4,12}", s):
        return False
    if re.fullmatch(r"[A-Za-z]{1,3}\d{5,12}", s):
        return False
    # Keep month/year and calendar dates ("MAR 2016", "06.06.1999").
    if re.search(r"\b(?:19|20)\d{2}\b", s) or re.search(
        r"\b\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b", s
    ):
        return False
    # Keep known certificate month tokens with a year already handled; also
    # "MAR 2016" style when month is 3 letters + year (year check above).
    if re.fullmatch(
        r"(?i)(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)"
        r"(?:[A-Z]*)?\s+\d{4}",
        s,
    ):
        return False

    cjk = len(_CJK_RE.findall(s))
    latin = sum(1 for c in s if ("A" <= c <= "Z") or ("a" <= c <= "z"))
    digits = sum(1 for c in s if c.isdigit())
    words = re.findall(r"[A-Za-z]{2,}", s)
    long_words = [w for w in words if len(w) >= 4]

    # Mostly CJK / mixed glyph junk.
    if cjk >= 2 and latin < 10:
        return True
    if cjk >= 1 and latin + digits < 6:
        return True

    # Accent / Latin-1 junk crumbs ("6ùQu") with almost no real English.
    if re.search(r"[^\x00-\x7F]", s) and len(long_words) == 0 and len(s) <= 12:
        return True

    # Ultra-short crumbs: "C", "G", "iu", "TT".
    if len(s) <= 3 and not s.isdigit():
        return True

    # Keep labeled field lines ("Roll No: 12345", "Name: Test") — digit-heavy
    # rules below would otherwise drop them.
    if re.match(
        r"(?i)^[A-Za-z][A-Za-z0-9 .'/()]{0,48}\s*[:\-–—|]\s*\S+",
        s,
    ):
        return False

    # Keep Title Case academic tokens (DOCX native often uses "Tamil"/"English").
    # ALLCAPS of length ≥ 3 kept (TAMIL / THEORY / HSG); ultra-short ALLCAPS
    # still fall through to the ≤3 / ≤2 crumb rules above/below.
    if re.fullmatch(r"[A-Z][a-z]{2,20}", s):
        return False
    if s.isupper() and len(s) >= 3 and re.fullmatch(r"[A-Z]{3,24}", s):
        return False

    # Passport File No. stamps (NG1063937171819) — keep letter+digit office codes.
    if re.fullmatch(r"[A-Za-z]{1,5}\d{6,14}[A-Za-z0-9]{0,4}", s) and not re.search(
        r"\d{6}[MFx]\d{4}", s
    ):
        return False

    # Single lowercase token junk from Tamil OCR ("gumi", "crour").
    if re.fullmatch(r"[a-z]{3,10}", s):
        return True
    if re.fullmatch(r"[A-Za-z]{1,5}", s) and s.isupper() and len(s) <= 2:
        return True

    # Space-separated short fragments — allow a 4-letter crumb ("rein") but not
    # real words (length ≥ 5).
    if _FRAG_LINE_RE.fullmatch(s) and not any(len(w) >= 5 for w in words):
        return True

    # Mixed alnum OCR crumbs ("CgrQou9i") — not certificate codes (those are longer digits).
    if re.fullmatch(r"[A-Za-z]{2,10}\d[A-Za-z0-9]{0,6}", s) and len(s) <= 14:
        return True

    # Short two-token Tamil OCR crumbs ("As iuLag").
    if re.fullmatch(r"(?i)[a-z]{1,3}\s+[a-z]{4,10}", s) and not s.isupper():
        return True

    # Camel/gibberish tokens without spaces (not ALLCAPS subject names).
    if (
        re.fullmatch(r"[A-Za-z]{6,16}", s)
        and not s.isupper()
        and not s.istitle()
        and s.lower()
        not in {
            "mathematics",
            "chemistry",
            "biology",
            "physics",
            "english",
            "accountancy",
            "economics",
            "commerce",
            "geography",
            "history",
        }
    ):
        return True

    # Heavily letter-spaced OCR (Tamil line read as spaced Latin).
    single_letter_tokens = len(re.findall(r"(?i)(?<![a-z])[a-z](?![a-z])", s))
    if _SPACED_LETTERS_RE.search(s) and (
        len(long_words) <= 1 or single_letter_tokens >= 4
    ):
        return True

    # Prefix junk + spaced letters: "Cerniidt i e t i t t tion".
    if single_letter_tokens >= 4 and len(s) <= 48:
        return True

    # Address crumbs with commas + many digits ("C6i , 6m6 -600 006").
    if sum(ch.isdigit() for ch in s) >= 4 and ("," in s or s.count("-") >= 1) and not any(
        len(w) >= 5 for w in words
    ):
        return True
    # Digit-heavy crumbs without a real word — but keep roll/register/code lines.
    if sum(ch.isdigit() for ch in s) >= 5 and not any(len(w) >= 5 for w in words):
        if re.search(
            r"(?i)\b(?:roll|reg(?:ister)?|code|marks?|total|phone|date|dob|sl\.?\s*no)\b",
            s,
        ):
            return False
        return True

    # Two-token gibberish near signature block ("ulona Gloweos", "Epulona Glowes",
    # "Ciamr aGwrium"). Prefer shared deterministic helper when available.
    try:
        from app.services.ocr_cleaner import is_ocr_gibberish_line

        if is_ocr_gibberish_line(s):
            return True
        # Helper said keep — do not apply the looser vowel heuristic below.
        if re.fullmatch(r"[A-Za-z]{4,14}\s+[A-Za-z]{4,14}", s):
            return False
    except Exception:
        pass
    if re.search(r"[a-z][A-Z]", s):  # mid-word capital: aGwrium
        return True
    if re.fullmatch(r"[A-Za-z]{4,12}\s+[A-Za-z]{4,12}", s) and not s.isupper():
        if re.search(r"(?i)\b(?:school|board|college|jesus|infant)\b", s):
            return False
        # Proper Title Case names ("John Smith") — keep unless rare digraph.
        if re.fullmatch(r"[A-Z][a-z]{3,13}\s+[A-Z][a-z]{3,13}", s):
            return bool(re.search(r"(?i)(?:gw|kq|xz|zx|qq|vv|jx|qx|vz)", s))
        vowels = sum(1 for c in s.lower() if c in "aeiou")
        if vowels <= 4:
            return True

    # Parenthetical OCR soup near stamps.
    if s.count("(") >= 1 and sum(ch.isalpha() for ch in s) <= 12 and len(s) <= 40:
        if not re.search(r"(?i)\b(?:hr|sec|school|code)\b", s):
            return True

    return False


def clean_ocr_extracted_text(value: str | None) -> str:
    """Drop RapidOCR noise lines; strip residual CJK from otherwise useful lines."""
    if not value:
        return ""
    text = value.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            out.append("")
            continue
        # Bilingual marksheet labels: keep English after "/" when left is OCR junk.
        # e.g. "GUTGG6/ GENERAL EDUCATION" → "GENERAL EDUCATION"
        #      "L QU /NAME OF THE SCHOOL" → "NAME OF THE SCHOOL"
        if "/" in line:
            left, right = line.split("/", 1)
            left, right = left.strip(" :-–—|"), right.strip(" :-–—|")
            if right and (
                re.match(
                    r"(?i)^(general\s+education|name\s+of\s+the\s+school|"
                    r"date\s+of\s+birth|roll\s*no\.?|t?mr\s*code|medium\s+of|"
                    r"group\s*code|permanent\s+register|total\s*marks?|"
                    r"signature|member\s+secretary)",
                    right,
                )
                or (
                    len(right) >= 10
                    and len(re.findall(r"[A-Za-z]{3,}", right)) >= 2
                    and (_ocr_line_is_noise(left) or len(left) <= 14)
                )
            ):
                line = right
        if _ocr_line_is_noise(line):
            continue
        # Strip CJK leftovers inside otherwise English lines.
        cleaned = _CJK_RE.sub("", line)
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        # Drop leading symbol soup before a clear English label.
        cleaned = re.sub(
            r"^[^A-Za-z0-9]{1,6}(?=[A-Za-z])",
            "",
            cleaned,
        ).strip()
        if not cleaned or _ocr_line_is_noise(cleaned):
            continue
        out.append(cleaned)
    # Collapse excess blank lines.
    lines: list[str] = []
    blank_run = 0
    for line in out:
        if not line:
            blank_run += 1
            if blank_run <= 1:
                lines.append("")
            continue
        blank_run = 0
        lines.append(line)
    return "\n".join(lines).strip()


def normalize_extracted_display(value: str | None) -> str:
    """Keep line breaks for counsellor review; collapse spaces; drop OCR noise lines."""
    if not value:
        return ""
    return clean_ocr_extracted_text(value)


def normalize_native_document_text(value: str | None) -> str:
    """Light normalize for born-digital PDF/DOCX — do not apply OCR noise filters.

    Native extracts already have clean Title Case subject names; the OCR cleaner
    historically wiped them (``Tamil`` / ``English``) and left blank review text.
    """
    if not value:
        return ""
    text = value.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    blank_run = 0
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            blank_run += 1
            if blank_run <= 1:
                lines.append("")
            continue
        blank_run = 0
        lines.append(line)
    return "\n".join(lines).strip()


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 120) -> list[str]:
    cleaned = normalize_utf8_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def source_text_hash(source_text: str, *, model: str) -> str:
    payload = f"{model}\n{source_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def embed_document_chunk(
    text: str, *, timeout_seconds: float | None = None
) -> tuple[list[float], str, str]:
    """Embed a document chunk. Returns (vector, model, source_text_hash)."""
    source = normalize_utf8_text(text)
    if not source:
        raise EmbeddingUnavailableError("Cannot embed empty document chunk.")

    model, expected_dim = _model_and_expected_dim()
    provider = _resolved_provider()
    if provider == "ollama":
        vector = _embed_ollama(source, model=model, timeout_seconds=timeout_seconds)
    else:
        vector = _embed_openai(source, model=model, dimensions=expected_dim)

    if not vector:
        raise EmbeddingUnavailableError("Embedding provider returned an empty vector.")
    return vector, model, source_text_hash(source, model=model)


def _empty_chunk_row(idx: int, chunk: str) -> dict:
    return {
        "chunk_index": idx,
        "chunk_text": chunk,
        "char_start": None,
        "char_end": None,
        "embedding": None,
        "embedding_dimensions": None,
        "embedding_model": None,
        "source_text_hash": None,
    }


def embed_chunks_best_effort(
    chunks: list[str],
    *,
    budget_seconds: float | None = None,
    per_chunk_timeout_seconds: float | None = None,
) -> tuple[list[dict], dict]:
    """Embed chunks within a wall-clock budget; leave nulls when over budget / provider down.

    Returns (rows, stats) where stats includes timing and skip reasons.
    """
    budget = float(
        budget_seconds
        if budget_seconds is not None
        else getattr(settings, "SCANX_EMBED_BUDGET_SECONDS", DEFAULT_EMBED_BUDGET_SECONDS)
        or DEFAULT_EMBED_BUDGET_SECONDS
    )
    per_chunk_cap = float(
        per_chunk_timeout_seconds
        if per_chunk_timeout_seconds is not None
        else DEFAULT_PER_CHUNK_TIMEOUT_SECONDS
    )

    started = time.perf_counter()
    deadline = started + max(0.5, budget)
    rows: list[dict] = []
    embedded_ok = 0
    skipped_budget = 0
    failed = 0
    first_error: str | None = None

    for idx, chunk in enumerate(chunks):
        row = _empty_chunk_row(idx, chunk)
        remaining = deadline - time.perf_counter()
        if remaining <= 0.05:
            skipped_budget += 1
            rows.append(row)
            continue
        chunk_timeout = min(per_chunk_cap, max(0.5, remaining))
        try:
            vector, model, text_hash = embed_document_chunk(
                chunk, timeout_seconds=chunk_timeout
            )
            row.update(
                {
                    "embedding": vector,
                    "embedding_dimensions": len(vector),
                    "embedding_model": model,
                    "source_text_hash": text_hash,
                }
            )
            embedded_ok += 1
        except EmbeddingUnavailableError as exc:
            failed += 1
            if first_error is None:
                first_error = str(exc)[:240]
            logger.info("ScanX chunk embed skipped idx=%s: %s", idx, exc)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            if first_error is None:
                first_error = f"{type(exc).__name__}: {exc}"[:240]
            logger.exception("ScanX chunk embed failed idx=%s", idx)
        rows.append(row)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    note = None
    if not chunks:
        note = None
    elif embedded_ok == 0 and (failed or skipped_budget):
        note = "embeddings_failed"
    elif skipped_budget or (embedded_ok and embedded_ok < len(chunks)):
        note = "embeddings_pending"
    elif embedded_ok == len(chunks):
        note = "embeddings_ok"

    stats = {
        "chunk_count": len(chunks),
        "embedded_count": embedded_ok,
        "embed_failed": failed,
        "embed_skipped_budget": skipped_budget,
        "embed_elapsed_ms": elapsed_ms,
        "embed_budget_seconds": budget,
        "embeddings_note": note,
        "embed_error": first_error,
    }
    logger.info(
        "ScanX embed budget done chunks=%s embedded=%s failed=%s skipped_budget=%s "
        "elapsed_ms=%s budget_s=%s note=%s",
        len(chunks),
        embedded_ok,
        failed,
        skipped_budget,
        elapsed_ms,
        budget,
        note,
    )
    return rows, stats
