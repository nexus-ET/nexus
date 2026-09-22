"""Lightweight heuristic categorizer for ScanX extracted OCR/text.

Runs after successful extract. Failures must never block parse — callers wrap
in try/except and fall back to full text only.
"""

from __future__ import annotations

import re
from typing import Any

from app.constants.scanx import DOCUMENT_TYPE_LABELS, DOCUMENT_TYPE_TO_SUBFOLDER
from app.services.scanx_academic_parse import (
    format_subject_item as _format_subject_item,
    parse_subjects_from_table_rows,
    parse_subjects_from_text,
    quality_subjects,
)
from app.services.scanx_field_extract import (
    fields_by_category,
    is_heading_or_label_line,
    resolve_fields_from_text,
)

# Re-export for callers / tests that imported parsers from this module.
__all__ = (
    "CATEGORY_DEFS",
    "categorize_document_fields",
    "categorize_extracted_text",
    "parse_subjects_from_table_rows",
    "parse_subjects_from_text",
)

# Category ids (stable API/UI keys) → display labels.
CATEGORY_DEFS: tuple[tuple[str, str], ...] = (
    ("document_summary", "Document summary"),
    ("identity", "Identity & personal"),
    ("contact", "Contact"),
    ("academic", "Academic / credentials"),
    ("dates_references", "Dates & references"),
    ("other", "Other details"),
)

_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

# International-ish phones: +cc … or local with separators (min ~8 digits).
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+|00)?(?:\d[\s\-().]*){8,15}\d(?!\w)",
)

_DATE_RE = re.compile(
    r"\b(?:"
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|"
    r"\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
    r"|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}"
    r"|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    r")\b",
    re.IGNORECASE,
)

_PASSPORT_RE = re.compile(
    r"\b(?:passport\s*(?:no|number|#)?\s*[:#]?\s*)([A-Z0-9]{6,12})\b"
    r"|\b([A-Z]{1,2}\d{6,9})\b",
    re.IGNORECASE,
)

_NATIONAL_ID_RE = re.compile(
    r"\b(?:national\s*id|nid|nric|aadhaar|aadhar|ssn|sin|emirates\s*id)"
    r"\s*(?:no|number|#)?\s*[:#]?\s*([A-Z0-9\-]{6,20})\b",
    re.IGNORECASE,
)

# Fallback value-only refs when heading was not captured by field extract.
_REF_RE = re.compile(
    r"\b(?P<label>ref(?:erence)?\s*(?:no|number|id|#)?|"
    r"application\s*(?:no|number|id|#)|"
    r"reg(?:istration)?\s*(?:no|number|id|#)|"
    r"roll\s*(?:no|number|#)|"
    r"candidate\s*(?:no|number|id|#)|"
    r"file\s*(?:no|number|#))"
    r"\s*[:#]?\s*(?P<value>[A-Z0-9][A-Z0-9\-_/]{4,24})\b",
    re.IGNORECASE,
)

_LABELED_NAME_RE = re.compile(
    r"(?im)^(?:full\s*name|candidate\s*name|student\s*name|name|surname|given\s*names?)"
    r"\s*[:\-]\s*(.+)$"
)

_DOB_RE = re.compile(
    r"(?im)^(?:date\s*of\s*birth|d\.?o\.?b\.?|born(?:\s*on)?)\s*[:\-]?\s*(.+)$"
)

_ADDRESS_RE = re.compile(
    r"(?im)^(?:address|residential\s*address|mailing\s*address|permanent\s*address)"
    r"\s*[:\-]\s*(.+)$"
)

_ACADEMIC_LINE_RE = re.compile(
    r"(?i)\b(?:"
    r"university|college|school|institute|bachelor|master|diploma|degree|"
    r"gpa|cgpa|grade|transcript|faculty|major|programme|program|"
    r"ielts|toefl|gre|gmat|sat|band\s*score|overall\s*score|percentile|"
    r"board|marksheet|marks?\s*sheet|grade\s*sheet"
    r")\b"
)

_SECTION_HEADING_RE = re.compile(
    r"(?im)^\s*(?:"
    r"personal\s*(?:details|information|particulars)|"
    r"contact\s*(?:details|information)|"
    r"education(?:al)?\s*(?:history|background|details)?|"
    r"academic(?:s)?(?:\s*(?:record|details|history))?|"
    r"test\s*scores?|examination\s*results?|"
    r"identity|passport|employment|work\s*experience|"
    r"references?|declaration"
    r")\s*:?\s*$"
)

_CGPA_GPA_RE = re.compile(
    r"(?i)\b((?:c\.?\s*g\.?\s*p\.?\s*a\.?)|(?:g\.?\s*p\.?\s*a\.?)|"
    r"cumulative\s+grade\s+point\s+average|grade\s+point\s+average)"
    r"\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9]{1,3})?)\b"
)

_BOARD_LINE_RE = re.compile(
    r"(?im)^(?:board|examining\s+board|examination\s+board|exam\s+board)"
    r"\s*[:\-]\s*(.+)$"
)

_YEAR_LINE_RE = re.compile(
    r"(?im)^(?:year|exam(?:ination)?\s+year|academic\s+year|session|passing\s+year)"
    r"\s*[:\-]\s*(.+)$"
)

_PIPE_SPLIT_RE = re.compile(r"\s*\|\s*")
_WS_RE = re.compile(r"\s+")


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def _split_table_cells(line: str) -> list[str]:
    """Split a pipe-joined table line (or tab-separated OCR row) into cells."""
    raw = (line or "").strip()
    if not raw:
        return []
    if "|" in raw:
        return [_clean(c) for c in _PIPE_SPLIT_RE.split(raw) if _clean(c)]
    if "\t" in raw:
        return [_clean(c) for c in raw.split("\t") if _clean(c)]
    return []


def _header_column_map(cells: list[str]) -> dict[str, int] | None:
    """Thin wrapper — full implementation lives in scanx_academic_parse."""
    from app.services.scanx_academic_parse import header_column_map

    return header_column_map(cells)


def _uniq_items(items: list[dict[str, str]], *, limit: int = 40) -> list[dict[str, str]]:
    """Dedupe items. Known single-value labels keep the longer value; multi rows stay."""
    multi_ok = {
        "line",
        "section",
        "subject",
        "academic detail",
        "score / grade",
        "date",
        "email",
        "phone",
    }
    by_label: dict[str, int] = {}
    seen_pairs: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in items:
        label = _clean(item.get("label") or "")
        value = _clean(item.get("value") or "")
        if not value:
            continue
        if label.lower() in {"score / grade", "academic detail", "line", "section"}:
            if is_heading_or_label_line(value):
                continue
        key = label.lower() or "value"
        pair = (key, value.lower())
        if pair in seen_pairs:
            continue
        if key not in multi_ok and key in by_label:
            idx = by_label[key]
            existing_val = out[idx]["value"]
            if len(value) > len(existing_val) + 1:
                seen_pairs.discard((key, existing_val.lower()))
                out[idx] = {"label": label or "Value", "value": value[:500]}
                seen_pairs.add(pair)
            continue
        seen_pairs.add(pair)
        if key not in multi_ok:
            by_label[key] = len(out)
        out.append({"label": label or "Value", "value": value[:500]})
        if len(out) >= limit:
            break
    return out


def _phone_digit_count(token: str) -> int:
    return sum(1 for ch in token if ch.isdigit())


def _looks_like_phone(token: str) -> bool:
    digits = _phone_digit_count(token)
    if digits < 8 or digits > 15:
        return False
    stripped = token.strip()
    has_plus = stripped.startswith("+")
    has_parens = "(" in token and ")" in token
    # International 00-prefix only when compact (avoid marksheet "009 078 …" noise).
    has_intl_00 = bool(re.match(r"00\d{8,14}$", re.sub(r"[\s\-()]", "", stripped)))
    return has_plus or has_parens or has_intl_00


def _phone_near_label(text: str, start: int) -> bool:
    window = text[max(0, start - 24) : start].lower()
    return bool(
        re.search(r"(?:phone|mobile|tel|cell|contact|whatsapp|ph\.?|mob\.?)\s*[:#]?\s*$", window)
    )


def _mark_spans(occupied: list[tuple[int, int]], start: int, end: int) -> None:
    if end <= start:
        return
    occupied.append((start, end))


def _span_free(occupied: list[tuple[int, int]], start: int, end: int) -> bool:
    for a, b in occupied:
        if start < b and end > a:
            return False
    return True


def categorize_extracted_text(
    text: str | None,
    *,
    original_filename: str | None = None,
    document_type_id: str | None = None,
    page_count: int | None = None,
    content_type: str | None = None,
    byte_size: int | None = None,
    use_llm_fields: bool = True,
) -> dict[str, Any]:
    """Return structured category payload for storage / review API.

    Shape::
        {
          "version": 1,
          "categories": [
            {"id": "...", "label": "...", "items": [{"label","value"}, ...]},
            ...
          ],
          "fields": [{"label","value","category"}, ...],  # heading→value pairs
          "subjects": [{"name","marks","grade"}, ...]     # marksheet rows when present
        }
    """
    raw = (text or "").strip()
    type_id = (document_type_id or "").strip().upper()
    type_label = DOCUMENT_TYPE_LABELS.get(type_id) or type_id or None
    subfolder = DOCUMENT_TYPE_TO_SUBFOLDER.get(type_id)

    summary_items: list[dict[str, str]] = []
    if original_filename:
        summary_items.append({"label": "Filename", "value": original_filename})
    if type_label:
        summary_items.append({"label": "Document type", "value": type_label})
    if subfolder:
        summary_items.append({"label": "Domain folder", "value": subfolder})
    if page_count is not None:
        summary_items.append(
            {
                "label": "Pages / images",
                "value": str(int(page_count)),
            }
        )
    if content_type:
        summary_items.append({"label": "Content type", "value": content_type})
    if byte_size is not None and byte_size >= 0:
        summary_items.append({"label": "File size (bytes)", "value": str(int(byte_size))})
    if raw:
        summary_items.append({"label": "Extracted characters", "value": str(len(raw))})

    identity: list[dict[str, str]] = []
    contact: list[dict[str, str]] = []
    academic: list[dict[str, str]] = []
    dates_refs: list[dict[str, str]] = []
    other: list[dict[str, str]] = []
    occupied: list[tuple[int, int]] = []
    subjects: list[dict[str, str]] = []

    structured_fields: list[dict[str, str]] = []

    if raw:
        # Primary path: preserve heading names (Date of Birth, Roll Number, …).
        # resolve_fields_from_text adds stacked OCR + optional LLM merge.
        structured_fields = resolve_fields_from_text(raw, use_llm=use_llm_fields)
        for cat_id, items in fields_by_category(structured_fields).items():
            if cat_id == "identity":
                identity.extend(items)
            elif cat_id == "academic":
                academic.extend(items)
            elif cat_id == "contact":
                contact.extend(items)
            else:
                other.extend(items)

        labeled_values = {_clean(f.get("value") or "").lower() for f in structured_fields}
        # Reserve value spans so bare date/ref fallbacks do not duplicate headings.
        for f in structured_fields:
            val = _clean(f.get("value") or "")
            if len(val) < 2:
                continue
            start = 0
            while True:
                idx = raw.find(val, start)
                if idx < 0:
                    break
                _mark_spans(occupied, idx, idx + len(val))
                start = idx + len(val)

        for m in _EMAIL_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            contact.append({"label": "Email", "value": m.group(0)})
            _mark_spans(occupied, m.start(), m.end())

        for m in _PHONE_RE.finditer(raw):
            token = _clean(m.group(0))
            if not _looks_like_phone(token) and not _phone_near_label(raw, m.start()):
                continue
            if not _span_free(occupied, m.start(), m.end()):
                continue
            contact.append({"label": "Phone", "value": token})
            _mark_spans(occupied, m.start(), m.end())

        for m in _LABELED_NAME_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            identity.append(
                {
                    "label": _clean(m.group(0).split(":")[0].split("-")[0]),
                    "value": m.group(1),
                }
            )
            _mark_spans(occupied, m.start(), m.end())

        for m in _DOB_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            identity.append({"label": "Date of Birth", "value": m.group(1)})
            _mark_spans(occupied, m.start(), m.end())

        for m in _PASSPORT_RE.finditer(raw):
            value = m.group(1) or m.group(2)
            if not value:
                continue
            if not _span_free(occupied, m.start(), m.end()):
                continue
            # Skip if this looks like a plain year or short number without passport context.
            if m.group(1) is None and not re.search(
                r"(?i)passport", raw[max(0, m.start() - 40) : m.end() + 10]
            ):
                continue
            identity.append({"label": "Passport / ID token", "value": value})
            _mark_spans(occupied, m.start(), m.end())

        for m in _NATIONAL_ID_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            identity.append({"label": "National ID", "value": m.group(1)})
            _mark_spans(occupied, m.start(), m.end())

        for m in _ADDRESS_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            contact.append({"label": "Address", "value": m.group(1)})
            _mark_spans(occupied, m.start(), m.end())

        for m in _REF_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            label_raw = _clean(m.group("label") or "Reference")
            # Title-case heading fragments: "roll no" → "Roll No"
            label = " ".join(part.capitalize() for part in label_raw.split())
            dates_refs.append({"label": label or "Reference", "value": m.group("value")})
            _mark_spans(occupied, m.start(), m.end())

        for m in _DATE_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            # Skip bare dates already captured under a real heading (e.g. Date of Birth).
            if _clean(m.group(0)).lower() in labeled_values:
                continue
            dates_refs.append({"label": "Date", "value": m.group(0)})
            _mark_spans(occupied, m.start(), m.end())

        # Prefer academic lines for ACADEMICS / TEST-SCORES domains; still scan all types.
        prefer_academic = subfolder in {"ACADEMICS", "TEST-SCORES"} or type_id in {
            "IELTS",
            "TOEFL",
            "GRE",
            "GMAT",
            "OTHER_TEST_SCORE",
            "TR_TRANSCRIPT",
            "DIPLOMA",
            "GRADE_SHEET",
            "ACADEMIC_CERTIFICATE",
        }

        subjects = quality_subjects(parse_subjects_from_text(raw))
        subject_line_keys: set[str] = set()
        subject_names: set[str] = set()
        for subj in subjects:
            academic.append(_format_subject_item(subj))
            # Track pipe-style lines so they are not duplicated under Other.
            name = _clean(subj.get("name") or "")
            marks = _clean(subj.get("marks") or subj.get("total") or "")
            grade = _clean(subj.get("grade") or "")
            theory = _clean(subj.get("theory") or "")
            practical = _clean(subj.get("practical") or "")
            if name:
                subject_line_keys.add(name.lower())
                subject_names.add(name.lower())
            bits = [b for b in (name, theory, practical, marks, grade) if b]
            if bits:
                subject_line_keys.add(" | ".join(bits).lower())
                subject_line_keys.add(" ".join(bits).lower())
            for score in (theory, practical, marks):
                if score:
                    subject_line_keys.add(score.lower())

        # Strip Theory / Practical / subject-mark rows that leaked into structured fields.
        def _is_marks_leak_field(f: dict[str, str]) -> bool:
            lab = _clean(f.get("label") or "").lower()
            val = _clean(f.get("value") or "").lower()
            if lab in {"theory", "practical", "thory", "prac", "prac."}:
                return True
            if lab == "subject":
                return True
            if lab in {"total marks", "total scores"} and subjects:
                # Keep a single certificate Total Marks in fields; drop duplicates later.
                return False
            if val and val in subject_line_keys:
                return True
            if any(sn and sn in val for sn in subject_names if len(sn) >= 3):
                if re.search(r"\d", val) and lab in {
                    "line",
                    "score / grade",
                    "academic detail",
                    "section",
                }:
                    return True
            return False

        structured_fields = [f for f in structured_fields if not _is_marks_leak_field(f)]
        # Rebuild identity/academic/contact/other from filtered fields for buckets that
        # were already populated from the unfiltered list above.
        identity = [i for i in identity if not _is_marks_leak_field(i)]
        academic = [i for i in academic if (i.get("label") or "") == "Subject" or not _is_marks_leak_field(i)]
        contact = [i for i in contact if not _is_marks_leak_field(i)]
        other = [i for i in other if not _is_marks_leak_field(i)]
        # Drop Theory/Practical from flat fields list after filter.
        structured_fields = [
            f
            for f in structured_fields
            if _clean(f.get("label") or "").lower() not in {"theory", "practical", "thory"}
        ]

        for m in _CGPA_GPA_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            label_raw = m.group(1) or ""
            item_label = (
                "CGPA"
                if re.search(r"(?i)c\.?\s*g\.?\s*p\.?\s*a|cumulative", label_raw)
                else "GPA"
            )
            academic.append({"label": item_label, "value": _clean(m.group(2))})
            _mark_spans(occupied, m.start(), m.end())

        for m in _BOARD_LINE_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            academic.append({"label": "Board", "value": m.group(1)})
            _mark_spans(occupied, m.start(), m.end())

        for m in _YEAR_LINE_RE.finditer(raw):
            if not _span_free(occupied, m.start(), m.end()):
                continue
            academic.append({"label": "Year", "value": m.group(1)})
            _mark_spans(occupied, m.start(), m.end())

        for line in raw.splitlines():
            cleaned = _clean(line)
            if len(cleaned) < 4:
                continue
            lower = cleaned.lower()
            if lower in subject_line_keys:
                continue
            if any(
                lower.startswith(f"{sk} |") or lower.startswith(f"{sk}—") or lower == sk
                for sk in subject_line_keys
                if sk
            ):
                continue
            # Known heading / label-only OCR lines — never Score or Academic values.
            if is_heading_or_label_line(cleaned):
                continue
            # Already captured as a labeled heading→value field.
            if any(
                _clean(f.get("label") or "").lower() in lower
                and _clean(f.get("value") or "").lower() in lower
                for f in structured_fields
            ):
                continue
            # Skip lines that duplicate an already-captured field value or label.
            if any(
                _clean(f.get("value") or "").lower() == lower
                or _clean(f.get("label") or "").lower() == lower
                for f in structured_fields
            ):
                continue
            # Pipe header row for marksheets.
            cells = _split_table_cells(cleaned)
            if cells and _header_column_map(cells):
                continue
            if _SECTION_HEADING_RE.match(cleaned):
                # Theory / Practical are score columns, not section banners.
                if re.fullmatch(
                    r"(?i)(?:theory|thory|practical|prac\.?|total(?:\s*marks?)?)",
                    cleaned.rstrip(":"),
                ):
                    continue
                other.append({"label": "Section", "value": cleaned.rstrip(":")})
                continue
            if _BOARD_LINE_RE.match(cleaned) or _YEAR_LINE_RE.match(cleaned) or _CGPA_GPA_RE.search(cleaned):
                # Already captured as Board / Year / CGPA|GPA fields.
                continue
            if _ACADEMIC_LINE_RE.search(cleaned):
                # Avoid dumping near-duplicate board/school banners.
                boardish = re.sub(r"[^a-z0-9]+", " ", lower)
                if any(
                    _clean(f.get("label") or "").lower() in {"board", "school", "exam"}
                    and (
                        lower in _clean(f.get("value") or "").lower()
                        or _clean(f.get("value") or "").lower() in lower
                        or re.sub(
                            r"[^a-z0-9]+", " ", _clean(f.get("value") or "").lower()
                        ).split()[:4]
                        == boardish.split()[:4]
                    )
                    for f in structured_fields
                ):
                    continue
                academic.append({"label": "Academic detail", "value": cleaned})
            elif prefer_academic and re.search(r"\b\d{2,3}(?:\.\d+)?\b", cleaned) and len(cleaned) < 120:
                # Short numeric lines near scores on test/academic docs.
                # Require a real score phrase — not bare "marks obtained" banners.
                if re.search(
                    r"(?i)\b(?:score|band|overall|gpa|cgpa|percent|percentage|grade)\b",
                    cleaned,
                ) and not re.search(r"(?i)marks?\s*obtained", cleaned):
                    academic.append({"label": "Score / grade", "value": cleaned})

        # Leftover short lines that were never claimed as structured hits.
        claimed_lower = {
            _clean(i["value"]).lower()
            for bucket in (identity, contact, academic, dates_refs)
            for i in bucket
        }
        claimed_lower |= subject_line_keys
        claimed_lower |= {_clean(f.get("value") or "").lower() for f in structured_fields}
        claimed_labels = {
            _clean(f.get("label") or "").lower() for f in structured_fields
        }
        _number_words = re.compile(
            r"(?i)^(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|"
            r"ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|"
            r"EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|"
            r"EIGHTY|NINETY|HUNDRED)(?:\s+(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|"
            r"SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|"
            r"SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|"
            r"SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED)){0,8}$"
        )
        for line in raw.splitlines():
            cleaned = _clean(line)
            if len(cleaned) < 8 or len(cleaned) > 200:
                continue
            lower = cleaned.lower()
            if lower in claimed_lower:
                continue
            if is_heading_or_label_line(cleaned):
                continue
            if _number_words.match(cleaned):
                continue
            # OCR fragment noise (Gu LG 200, C L, …).
            if re.fullmatch(r"(?i)[A-Za-z]{1,2}(?:\s+[A-Za-z]{1,2})+(?:\s+\d{1,4})?", cleaned):
                continue
            if any(claim and claim in lower for claim in claimed_lower):
                continue
            if any(lab and lab in lower for lab in claimed_labels if len(lab) >= 4):
                continue
            if any(
                _clean(f.get("label") or "").lower() in lower
                and _clean(f.get("value") or "").lower() in lower
                for f in structured_fields
            ):
                continue
            cells = _split_table_cells(cleaned)
            if cells and (_header_column_map(cells) or len(cells) >= 2):
                # Table body rows already represented as Subject items.
                if subjects:
                    continue
            if _EMAIL_RE.search(cleaned) or _PHONE_RE.search(cleaned):
                continue
            if _SECTION_HEADING_RE.match(cleaned):
                continue
            if _LABELED_NAME_RE.match(cleaned) or _DOB_RE.match(cleaned) or _ADDRESS_RE.match(cleaned):
                continue
            if re.match(r"^[A-Za-z][A-Za-z0-9 .'/()]{1,48}\s*[:\-–—]\s*.+$", cleaned):
                continue
            # Never dump subject / theory / practical / marks lines into Other.
            if subjects and (
                re.fullmatch(r"(?i)(?:theory|thory|practical|prac\.?|total(?:\s*marks?)?)", cleaned)
                or any(sn == lower or lower.startswith(f"{sn} ") for sn in subject_names)
                or (
                    re.search(r"\d{1,4}", cleaned)
                    and any(sn and sn in lower for sn in subject_names)
                )
            ):
                continue
            # Keep a small sample of leftover lines for manual review.
            if len(other) >= 12:
                break
            if cleaned.lower() not in {o["value"].lower() for o in other}:
                other.append({"label": "Line", "value": cleaned})

    buckets: dict[str, list[dict[str, str]]] = {
        "document_summary": _uniq_items(summary_items),
        "identity": _uniq_items(identity),
        "contact": _uniq_items(contact),
        "academic": _uniq_items(academic, limit=50),
        "dates_references": _uniq_items(dates_refs),
        "other": _uniq_items(other, limit=20),
    }

    # Always expose full extracted text under Other for review UI (UI scrolls; do not truncate).
    if raw:
        # Preserve newlines — do not run through _uniq_items/_clean.
        other_items = list(buckets["other"])
        other_items.append({"label": "Full text preview", "value": raw})
        buckets["other"] = other_items

    categories = [
        {
            "id": cat_id,
            "label": label,
            "items": buckets.get(cat_id, []),
        }
        for cat_id, label in CATEGORY_DEFS
        if buckets.get(cat_id)
    ]

    payload: dict[str, Any] = {
        "version": 1,
        "categories": categories,
    }
    # Flat label–value list for clients that prefer a single fields array.
    if structured_fields:
        flat: list[dict[str, str]] = []
        seen_labels: set[str] = set()
        for f in structured_fields:
            lab = _clean(f.get("label") or "Field")
            val = _clean(f.get("value") or "")
            if not val:
                continue
            lab_l = lab.lower()
            # Drop Theory/Practical column fields; subjects table owns those.
            if lab_l in {"theory", "practical", "thory", "prac", "prac.", "subject"}:
                continue
            # One Total Marks only.
            if lab_l in {"total marks", "total scores"}:
                if "total marks" in seen_labels:
                    continue
                lab = "Total Marks"
                lab_l = "total marks"
            if lab_l in seen_labels:
                continue
            seen_labels.add(lab_l)
            flat.append(
                {
                    "label": lab,
                    "value": val,
                    "category": f.get("category") or "other",
                }
            )
        if flat:
            payload["fields"] = flat
    # Structured marksheet rows for API / UI (also mirrored under Academic items).
    if subjects:
        payload["subjects"] = subjects
    return payload


def categorize_document_fields(
    *,
    text: str | None,
    original_filename: str | None = None,
    document_type_id: str | None = None,
    page_count: int | None = None,
    content_type: str | None = None,
    byte_size: int | None = None,
    use_llm_fields: bool = True,
) -> dict[str, Any] | None:
    """Best-effort wrapper used by the worker. Returns None on failure."""
    try:
        return categorize_extracted_text(
            text,
            original_filename=original_filename,
            document_type_id=document_type_id,
            page_count=page_count,
            content_type=content_type,
            byte_size=byte_size,
            use_llm_fields=use_llm_fields,
        )
    except Exception:
        return None
