"""Ollama refinement for ScanX passport field mapping.

Runs after heuristic MRZ + labeled extraction. Fills blank schema keys from
spatially sorted OCR text so Personal Info / Document Details / MRZ / Audit
groups are as complete as possible. Failures never block the parse job.
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
from app.services.scanx_passport import (
    PASSPORT_FIELD_KEYS,
    _clean_person_name,
    _is_blank_spouse_value,
    _is_garbage_file_number,
    _is_plausible_person_name,
    is_plausible_nationality,
    resolve_nationality,
)

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract passport / identity-document fields from OCR text that is "
    "already sorted in reading order (top→bottom, left→right; same-line "
    "labels stay beside their values). "
    "Return ONLY valid JSON with these keys (use null when unknown — never invent):\n"
    "surname, given_names, date_of_birth, sex, nationality, country_code, place_of_birth, "
    "document_number, document_type, place_of_issue, "
    "date_of_issue, date_of_expiry, mrz_string, father_name, mother_name, "
    "spouse_name, address, file_number.\n"
    "Rules:\n"
    "- Prefer dates as DD-MM-YYYY when day/month/year are clear "
    "(or the office display format).\n"
    "- sex: M, F, or X only.\n"
    "- country_code: ISO 3166-1 alpha-3 (e.g. IND). "
    "nationality: full printed nationality only (e.g. INDIAN, BRITISH) — "
    "never the 3-letter code, never OCR mashups that mix Sex / Date of Birth "
    "labels (reject strings like 'FAIQ SEX CROUFUFT DALE OF BIRTH'). "
    "Locate the Nationality / Nationalité / Citizenship anchor and take the "
    "value immediately beside or below it; if unsure, prefer MRZ nationality "
    "code mapped to the demonym (IND→INDIAN).\n"
    "- document_number is the passport number.\n"
    "- Do not return issuing_state.\n"
    "- document_type: usually P for passport.\n"
    "- given_names: all given / first names (not the surname).\n"
    "- Never copy one field into another blank field. If Surname is blank on "
    "the document, leave surname null — do not reuse given_names. If Given "
    "Name is blank, leave given_names null — do not reuse surname. The same "
    "applies to places, dates, file_number, document_number, parents, spouse, "
    "address, nationality, and sex.\n"
    "- father_name / mother_name: the person's name only — never label text "
    "(Father / Legal Guardian / Guardlan) and never a passport number.\n"
    "- spouse_name: OPTIONAL. Many passports have no Spouse field. Set null "
    "when the OCR has no 'Name of Spouse' / 'Spouse name' label, or the value "
    "cell is blank (N/A, -, empty, or OCR crumbs like 'went'). Never invent a "
    "spouse; never copy father_name, mother_name, or Address-line OCR into "
    "spouse_name.\n"
    "- date_of_issue: printed Date of Issue / Date of lssue / DOI (not MRZ). "
    "If two dates sit under Issue/Expiry, the earlier is issue and the later "
    "is expiry.\n"
    "- file_number: Indian File No. / File Number / FILENO / A3/F No. stamp "
    "(letter+digits such as NG1063937171819, or office codes like HYD/1234/19). "
    "Never the passport number, never dates, never 'Pita No.' / father labels, "
    "never Date of Issue/Expiry text. Use null when the value is missing.\n"
    "- address: keep every printed address line (join with commas); keep PIN/ZIP.\n"
    "- mrz_string: full MRZ lines joined with \\n when visible (TD3).\n"
    "- Map Place of Birth / Given Name(s) / Place of Issue / File No carefully "
    "to the adjacent value — never reuse a field label as a value.\n"
    "- Ignore CamScanner / watermark noise.\n"
    "- Ignore notary, attestation, advocate, true-copy, verified, and "
    "stamp-duty comments. Do not use that text as a name, date, or address."
)

_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$"
)


def _ollama_native_base() -> str:
    configured = (
        settings.OLLAMA_BASE_URL
        or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    )
    return configured.rstrip("/").removesuffix("/v1")


def _parse_passport_payload(raw: str) -> dict[str, Any]:
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
    # Some models nest under "passport" / "fields".
    if "passport" in data and isinstance(data["passport"], dict):
        data = data["passport"]
    out: dict[str, Any] = {}
    for key in PASSPORT_FIELD_KEYS:
        if key not in data:
            continue
        val = data.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if not s or s.lower() in {"null", "none", "n/a", "na", "-"}:
            continue
        if key == "address":
            s = re.sub(r"[\r\n]+", ", ", s)
            s = re.sub(r"\s*,\s*", ", ", s).strip(" ,")
        if key == "sex":
            u = s.upper().strip()
            if u in {"M", "F", "X"}:
                s = u
            elif u.startswith("MALE") or u == "M":
                s = "M"
            elif u.startswith("FEMALE") or u == "F":
                s = "F"
            elif u in {"X", "X / X", "UNSPECIFIED"}:
                s = "X"
            else:
                continue
        if key == "nationality":
            demonym, _code = resolve_nationality(s)
            if not demonym:
                continue
            s = demonym
        if key == "country_code":
            from app.services.scanx_passport import _to_alpha3, _VALID_ALPHA3

            code = _to_alpha3(s)
            if not code or code not in _VALID_ALPHA3:
                continue
            s = code
        if key in {"date_of_birth", "date_of_issue", "date_of_expiry"}:
            from app.services.scanx_dates import normalize_scanx_date

            formatted = normalize_scanx_date(s)
            if not formatted and not _DATE_RE.match(s) and not re.search(r"\d", s):
                continue
            if formatted:
                s = formatted
            elif not _DATE_RE.match(s) and not re.search(r"\d", s):
                continue
        if key in {"father_name", "mother_name", "spouse_name"}:
            cleaned = _clean_person_name(s)
            if not cleaned or not _is_plausible_person_name(cleaned):
                continue
            if key == "spouse_name" and _is_blank_spouse_value(cleaned):
                continue
            s = cleaned
        if key == "file_number" and _is_garbage_file_number(s):
            continue
        out[key] = s[:800] if key == "address" else s[:400]
    return out


def refine_passport_fields_via_llm(
    text: str | None,
    *,
    existing: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Fill blank passport schema keys via Ollama. Returns only new/filled keys."""
    if not getattr(settings, "SCANX_LLM_PASSPORT_ENABLED", True):
        return {}
    raw = (text or "").strip()
    if len(raw) < 24:
        return {}

    model_ref = (
        getattr(settings, "SCANX_LLM_MODEL", None)
        or settings.INTEL_AI_MODEL
        or "ollama:llama3.2"
    )
    provider, model_id = parse_model_ref(model_ref)
    if provider != "ollama" or not model_id:
        logger.info(
            "ScanX LLM passport skipped — provider=%s model=%s (ollama chat required)",
            provider,
            model_id,
        )
        return {}

    known = existing if isinstance(existing, dict) else {}
    already = {}
    for k in PASSPORT_FIELD_KEYS:
        val = known.get(k)
        if val is None or not str(val).strip():
            continue
        # Treat OCR-bleed nationality as blank so the model can correct it.
        if k == "nationality" and not is_plausible_nationality(str(val)):
            continue
        already[k] = val
    missing = [k for k in PASSPORT_FIELD_KEYS if k not in already]
    # Allow spouse fill when OCR has a fuzzy Spouse label OR unlabeled 3-name
    # evidence. Value-shape gates still reject invented/junk names.
    from app.services.scanx_passport import _passport_has_spouse_evidence

    allow_spouse = _passport_has_spouse_evidence(raw)
    if "spouse_name" in missing and not allow_spouse:
        missing = [k for k in missing if k != "spouse_name"]
    if not missing:
        return {}

    clipped = raw if len(raw) <= 8000 else raw[:8000]
    timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "SCANX_LLM_PASSPORT_TIMEOUT_SECONDS", 60.0)
    )

    hint = ""
    if already:
        hint = (
            "\n\nAlready extracted (do not contradict unless clearly wrong; "
            "focus on filling blanks):\n"
            + json.dumps(already, ensure_ascii=False)[:1500]
        )

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Map this spatially sorted passport OCR into the JSON schema. "
                    f"Prefer filling: {', '.join(missing)}.\n\n"
                    f"{clipped}{hint}"
                ),
            },
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.0, "seed": 0, "num_predict": 1400},
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
            "ScanX LLM passport refine failed model=%s", model_id, exc_info=True
        )
        return {}

    parsed = _parse_passport_payload(content)
    # Only return keys that were blank (or missing) in existing.
    filled: dict[str, Any] = {}
    for key, val in parsed.items():
        if key not in PASSPORT_FIELD_KEYS:
            continue
        if key == "spouse_name" and not allow_spouse:
            continue
        cur = already.get(key)
        if cur is not None and str(cur).strip():
            continue
        filled[key] = val
    logger.info(
        "ScanX LLM passport model=%s filled=%s",
        model_id,
        list(filled.keys()),
    )
    return filled
