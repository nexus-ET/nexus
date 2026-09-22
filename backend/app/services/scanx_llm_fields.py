"""Optional Ollama LLM structured extract for ScanX transcript key-value fields.

Complements heuristic ``scanx_field_extract`` when stacked/bilingual OCR misses
labels such as Date of Birth, Roll Number, or Group Code. Chat-only (same
Ollama path as subject assist). Failures return [] and never block parse.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.services.ai_providers import parse_model_ref
from app.services.scanx_field_extract import merge_fields

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract EVERY labeled field from noisy academic transcript / marksheet OCR. "
    "Return ONLY valid JSON: "
    '{"fields":[{"label":"Date of Birth","value":"06.06.1999"},'
    '{"label":"Roll Number","value":"478100"},'
    '{"label":"Group Code","value":"103"}]} . '
    "Use the original English heading text as label when visible "
    "(Date of Birth, Roll No., Group Code, Permanent Register No, "
    "Medium of Instruction, Name of the School, Total Marks, Maximum Marks, "
    "Candidate Name, "
    "Session, Board, Certificate No, TMR Code No, Issue Date, etc.). "
    "Include all identity and academic key-value pairs you can find. "
    "Ignore subject mark rows (Tamil 169, Physics 147, …). "
    "If nothing is found, return {\"fields\":[]}."
)

_KNOWN_CAT = {
    "date of birth": "identity",
    "candidate name": "identity",
    "father's name": "identity",
    "mother's name": "identity",
    "roll number": "academic",
    "roll no": "academic",
    "roll no.": "academic",
    "registration no": "academic",
    "permanent register no": "academic",
    "group code": "academic",
    "mr code no": "academic",
    "tmr code no": "academic",
    "medium of instruction": "academic",
    "certificate no": "academic",
    "school": "academic",
    "name of the school": "academic",
    "board": "academic",
    "session": "academic",
    "year of passing": "academic",
    "total marks": "academic",
    "total scores": "academic",
    "maximum marks": "academic",
    "exam": "academic",
    "stream": "academic",
    "issue date": "academic",
}


def _ollama_native_base() -> str:
    configured = (
        settings.OLLAMA_BASE_URL
        or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    )
    return configured.rstrip("/").removesuffix("/v1")


def _category_for(label: str) -> str:
    key = (label or "").strip().lower().rstrip(".:")
    if key in _KNOWN_CAT:
        return _KNOWN_CAT[key]
    for alias, cat in _KNOWN_CAT.items():
        if key.startswith(alias):
            return cat
    return "other"


def _parse_fields_payload(raw: str) -> list[dict[str, str]]:
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
    rows = data.get("fields") or data.get("key_values") or data.get("pairs")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("key") or row.get("name") or "").strip()
        value = str(row.get("value") or "").strip()
        if not label or not value:
            continue
        # Drop subject-like rows.
        if re.match(r"(?i)^subject$", label):
            continue
        cat = str(row.get("category") or "").strip() or _category_for(label)
        out.append(
            {
                "label": label[:120],
                "value": value[:500],
                "category": cat[:40],
            }
        )
    return merge_fields(out)


def extract_fields_via_llm(
    text: str | None,
    *,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    """Sync Ollama chat call → label/value fields. Empty on any failure."""
    if not getattr(settings, "SCANX_LLM_FIELDS_ENABLED", True):
        return []
    raw = (text or "").strip()
    if len(raw) < 12:
        return []

    model_ref = (
        getattr(settings, "SCANX_LLM_MODEL", None)
        or settings.INTEL_AI_MODEL
        or "ollama:llama3.2"
    )
    provider, model_id = parse_model_ref(model_ref)
    if provider != "ollama" or not model_id:
        logger.info(
            "ScanX LLM fields skipped — provider=%s model=%s (ollama chat required)",
            provider,
            model_id,
        )
        return []

    clipped = raw if len(raw) <= 6000 else raw[:6000]
    timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "SCANX_LLM_FIELDS_TIMEOUT_SECONDS", 45.0)
    )

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Extract ALL key-value fields (not subjects/marks) from this transcript OCR:\n\n"
                    f"{clipped}"
                ),
            },
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.0, "seed": 0, "num_predict": 1200},
    }
    chat_url = f"{_ollama_native_base()}/api/chat"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        chat_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw_body)
        content = (data.get("message") or {}).get("content") or ""
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        logger.warning(
            "ScanX LLM field extract failed model=%s", model_id, exc_info=True
        )
        return []

    fields = _parse_fields_payload(content)
    logger.info("ScanX LLM fields model=%s count=%s", model_id, len(fields))
    return fields
