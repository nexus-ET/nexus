"""Optional Ollama LLM structured extract for ScanX marksheet subjects.

Embeddings continue to use nomic-embed-text (EMBEDDING_PROVIDER → ollama when
OpenAI is unset). This module is chat-only: returns
``{subjects:[{name, marks, grade?}]}`` JSON when heuristic parsers find too few
quality rows on marksheet-like OCR text.

Uses stdlib ``urllib`` so it works even when ``httpx`` is not installed in the
worker venv.
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
from app.services.scanx_academic_parse import merge_subjects

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract academic marksheet subjects from noisy OCR text. "
    "Return ONLY valid JSON with this shape: "
    '{"subjects":[{"name":"Physics","theory":"097","practical":"050","total":"147","marks":"147","grade":"A"}]} . '
    "Each subject is one row with optional theory, practical, and total scores. "
    "marks must equal the consolidated total (theory+practical or printed total). "
    "Never invent separate subjects named Theory, Practical, or Total Marks. "
    "Omit rows that are not subjects (board name, school, roll, dates, certificate totals). "
    "If nothing is found, return {\"subjects\":[]}."
)


def _ollama_native_base() -> str:
    configured = (
        settings.OLLAMA_BASE_URL
        or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    )
    return configured.rstrip("/").removesuffix("/v1")


def _parse_subjects_payload(raw: str) -> list[dict[str, str]]:
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
    rows = data.get("subjects")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        marks = str(row.get("marks") or row.get("score") or row.get("total") or "").strip()
        grade = str(row.get("grade") or "").strip()
        theory = str(row.get("theory") or "").strip()
        practical = str(row.get("practical") or "").strip()
        total = str(row.get("total") or "").strip()
        if not name:
            continue
        if re.fullmatch(r"(?i)(?:theory|thory|practical|prac\.?|total(?:\s*marks?)?)", name):
            continue
        item: dict[str, str] = {"name": name[:200], "marks": (marks or total)[:80]}
        if grade:
            item["grade"] = grade[:40]
        if theory:
            item["theory"] = theory[:80]
        if practical:
            item["practical"] = practical[:80]
        if total:
            item["total"] = total[:80]
        elif marks:
            item["total"] = marks[:80]
        out.append(item)
    return merge_subjects(out)


def extract_subjects_via_llm(
    text: str | None,
    *,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    """Sync Ollama chat call → subject rows. Empty on any failure."""
    if not getattr(settings, "SCANX_LLM_SUBJECTS_ENABLED", True):
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
            "ScanX LLM subjects skipped — provider=%s model=%s (ollama chat required)",
            provider,
            model_id,
        )
        return []

    clipped = raw if len(raw) <= 6000 else raw[:6000]
    timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "SCANX_LLM_SUBJECTS_TIMEOUT_SECONDS", 45.0)
    )

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Extract every subject name and marks obtained from this marksheet OCR:\n\n"
                    f"{clipped}"
                ),
            },
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 800},
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
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        logger.warning(
            "ScanX LLM subject extract failed model=%s", model_id, exc_info=True
        )
        return []

    subjects = _parse_subjects_payload(content)
    logger.info("ScanX LLM subjects model=%s count=%s", model_id, len(subjects))
    return subjects
