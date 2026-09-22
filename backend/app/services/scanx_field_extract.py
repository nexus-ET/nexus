"""Label–value field extraction for ScanX OCR / PDF / DOCX text.

Preserves heading names (e.g. "Date of Birth", "Roll Number", "Group Code")
instead of value-only dumps. Handles same-line ``Label: value``, two-cell
tables, and stacked bilingual OCR (Tamil Nadu HSC: label lines then value
lines). Used by the categorizer; failures must not block parse.
"""

from __future__ import annotations

import re
from typing import Any

_WS_RE = re.compile(r"\s+")
_PIPE_SPLIT_RE = re.compile(r"\s*\|\s*")
# Same-line whitespace only — never cross newlines into the next OCR row.
_SAME_LINE_WS = r"[^\S\n]"

# Canonical label, category bucket, case-insensitive aliases (longest match wins).
_FIELD_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Date of Birth",
        "identity",
        (
            "date of birth",
            "date ofbirth",
            "birth date",
            "birthdate",
            "born on",
            "born",
            "d.o.b.",
            "d.o.b",
            "dob",
        ),
    ),
    (
        "Candidate Name",
        "identity",
        (
            "candidate name",
            "student name",
            "pupil name",
            "full name",
            "name of candidate",
            "name of student",
            "examinée name",
            "examinee name",
            "name of the candidate",
        ),
    ),
    (
        "Father's Name",
        "identity",
        (
            "father's name",
            "fathers name",
            "father name",
            "name of father",
            "name of father / legal guardian",
            "father / legal guardian",
        ),
    ),
    ("Mother's Name", "identity", ("mother's name", "mothers name", "mother name", "name of mother")),
    ("Spouse Name", "identity", ("spouse's name", "spouses name", "spouse name", "name of spouse")),
    ("Guardian's Name", "identity", ("guardian's name", "guardians name", "guardian name")),
    ("Gender", "identity", ("gender", "sex")),
    ("Nationality", "identity", ("nationality", "citizenship")),
    (
        "Roll Number",
        "academic",
        (
            "roll number",
            "roll no.",
            "roll no",
            "roll #",
            "rollnum",
            "roll",
        ),
    ),
    (
        "Registration No",
        "academic",
        (
            "registration number",
            "registration no.",
            "registration no",
            "regn. no.",
            "regn no",
            "reg. no.",
            "reg no.",
            "reg no",
            "reg number",
        ),
    ),
    (
        "Permanent Register No",
        "academic",
        (
            "permanent register number",
            "permanent register no.",
            "permanent register no",
            "permanent register",
            "permanent reg no",
            "prn",
        ),
    ),
    (
        "Admission No",
        "academic",
        ("admission number", "admission no.", "admission no", "adm. no.", "adm no"),
    ),
    (
        "Certificate No",
        "academic",
        (
            "certificate number",
            "certificate no.",
            "certificate no",
            "certificate sl. no.",
            "certificate sl no",
            "certificate sl.no",
            "cert. no.",
            "cert no",
            "sl. no.",
            "sl no",
        ),
    ),
    (
        "Seat No",
        "academic",
        ("seat number", "seat no.", "seat no", "seat #"),
    ),
    (
        "Group Code",
        "academic",
        (
            "group code",
            "grp code",
            "group no.",
            "group no",
            "group number",
            "grp no",
        ),
    ),
    (
        "TMR Code No",
        "academic",
        (
            "tmr code number",
            "tmr code no.",
            "tmr code no",
            "tmr code",
            "mr code number",
            "mr code no.",
            "mr code no",
            "mr code",
            "emr code no",
            "emr code",
        ),
    ),
    (
        "Code Number",
        "academic",
        ("code number", "code no.", "code no", "exam code", "centre code", "center code"),
    ),
    (
        "Medium of Instruction",
        "academic",
        (
            "medium of instruction",
            "medium of study",
            "instruction medium",
            "medium",
        ),
    ),
    (
        "Total Marks",
        "academic",
        (
            "total marks",
            "total scores",
            "total score",
            "grand total",
            "aggregate marks",
            "aggregate",
            "total obtained",
        ),
    ),
    # Theory / Practical are per-subject score columns — never document fields.
    # Certificate column maxima use "Maximum Marks" (marks obtained for 200).
    (
        "Maximum Marks",
        "academic",
        (
            "maximum marks",
            "max marks",
            "max. marks",
            "out of",
            "marks obtained for",
            "theory maximum",
            "theory max",
            "practical maximum",
            "practical max",
        ),
    ),
    ("Percentage", "academic", ("percentage", "percent", "% marks", "pct")),
    ("CGPA", "academic", ("c.g.p.a.", "cgpa", "cumulative grade point average")),
    ("GPA", "academic", ("g.p.a.", "gpa", "grade point average")),
    ("Grade", "academic", ("overall grade", "final grade", "result grade", "division", "class obtained")),
    ("Result", "academic", ("result", "pass/fail", "qualification status")),
    ("Board", "academic", ("examining board", "examination board", "exam board", "board of school examinations", "board")),
    (
        "School",
        "academic",
        (
            "name of the school",
            "name of school",
            "school name",
            "school / college",
            "school/college",
            "school",
        ),
    ),
    ("College", "academic", ("college name", "college / university", "name of college", "college")),
    ("University", "academic", ("university name", "name of university", "university")),
    ("Class", "academic", ("class / grade", "class/grade", "class", "standard", "grade level")),
    ("Session", "academic", ("academic session", "exam session", "session", "academic year", "month year")),
    (
        "Year of Passing",
        "academic",
        ("year of passing", "passing year", "examination year", "exam year", "year"),
    ),
    ("Exam", "academic", ("examination name", "exam name", "name of examination", "examination", "exam")),
    ("Stream", "academic", ("stream", "faculty", "general education")),
    ("Centre", "academic", ("exam centre", "exam center", "centre", "center")),
    ("Email", "contact", ("e-mail", "email address", "email id", "email")),
    ("Phone", "contact", ("phone number", "mobile number", "contact number", "telephone", "phone", "mobile", "tel")),
    ("Address", "contact", ("residential address", "mailing address", "permanent address", "address")),
    ("Passport No", "identity", ("passport number", "passport no.", "passport no", "passport")),
    ("National ID", "identity", ("national id", "nid", "nric", "aadhaar", "aadhar", "emirates id")),
    (
        "Issue Date",
        "academic",
        (
            "date of issue",
            "date of lssue",
            "date of issuc",
            "issued on",
            "issue date",
            "dated",
        ),
    ),
)

# Sort aliases longest-first so "date of birth" beats "dob", "roll number" beats "roll no".
_ALIAS_INDEX: list[tuple[str, str, str]] = []
for _canon, _cat, _aliases in _FIELD_DEFS:
    for _alias in _aliases:
        _ALIAS_INDEX.append((_alias.lower(), _canon, _cat))
_ALIAS_INDEX.sort(key=lambda t: len(t[0]), reverse=True)

# Short / ambiguous aliases only match with an explicit separator (":" / "-" / "#").
_SHORT_ALIASES = {
    a
    for a, _, _ in _ALIAS_INDEX
    if len(a) <= 5
    or a
    in {
        "board",
        "school",
        "college",
        "class",
        "session",
        "year",
        "exam",
        "examination",
        "stream",
        "result",
        "phone",
        "mobile",
        "email",
        "address",
        "passport",
        "percent",
        "grade",
        "aggregate",
        "institution",
        "university",
        "standard",
        "medium",
        "centre",
        "center",
        "dated",
        "prn",
        "roll",
        "born",
    }
}
_LONG_ALIASES = [a for a, _, _ in _ALIAS_INDEX if a not in _SHORT_ALIASES]
_SHORT_ALIAS_LIST = [a for a, _, _ in _ALIAS_INDEX if a in _SHORT_ALIASES]

_LONG_ALIAS_PATTERN = "|".join(re.escape(a) for a in _LONG_ALIASES) or "a^"
_SHORT_ALIAS_PATTERN = "|".join(re.escape(a) for a in _SHORT_ALIAS_LIST) or "a^"
_ALL_ALIAS_PATTERN = "|".join(re.escape(a) for a, _, _ in _ALIAS_INDEX)

# Stop a value when another known heading begins on the same line.
_NEXT_LABEL_BOUNDARY = (
    rf"(?={_SAME_LINE_WS}+(?:{_ALL_ALIAS_PATTERN})\b{_SAME_LINE_WS}*[:\-–—#]|{_SAME_LINE_WS}{{2,}}|{_SAME_LINE_WS}*[|;]|$)"
)

# Multi-word / distinctive aliases: Label: value or Label value (same line only).
_KNOWN_LONG_RE = re.compile(
    rf"(?im)\b({_LONG_ALIAS_PATTERN})\b(?:{_SAME_LINE_WS}*[:\-–—#]{_SAME_LINE_WS}*|{_SAME_LINE_WS}{{1,3}})(.+?){_NEXT_LABEL_BOUNDARY}"
)
# Short aliases require an explicit separator to avoid prose false positives.
_KNOWN_SHORT_RE = re.compile(
    rf"(?im)\b({_SHORT_ALIAS_PATTERN})\b{_SAME_LINE_WS}*[:\-–—#]{_SAME_LINE_WS}*(.+?){_NEXT_LABEL_BOUNDARY}"
)

# Generic "Some Label: value" on a line (unknown headings).
_GENERIC_LABELED_RE = re.compile(
    r"(?im)^(?P<label>[A-Za-z][A-Za-z0-9 .'/()]{1,48}?)\s*[:\-–—]\s*(?P<value>.+)$"
)

# Two-cell label | value (or tab) rows.
_LABELISH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 .'/()]{1,48}$")

_DATE_VALUE_RE = re.compile(
    r"^(?:"
    r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}"
    r"|"
    r"\d{4}[./\-]\d{1,2}[./\-]\d{1,2}"
    r"|"
    r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+\d{4}"
    r")$",
    re.IGNORECASE,
)
_SESSION_VALUE_RE = re.compile(
    r"^(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+\d{4}$",
    re.IGNORECASE,
)
_NUMBER_WORDS_RE = re.compile(
    r"(?i)^(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|"
    r"ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|"
    r"EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|"
    r"EIGHTY|NINETY|HUNDRED)(?:\s+(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|"
    r"SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|"
    r"SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|"
    r"SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED)){0,8}$"
)
_SUBJECT_NAME_RE = re.compile(
    r"(?i)^(?:tamil|english|physics|chemistry|biology|mathematics|maths?|"
    r"history|geography|commerce|accountancy|economics|computer\s*science|"
    r"botany|zoology|business\s*maths?)$"
)
_MEDIUM_VALUE_RE = re.compile(
    r"(?i)^(?:tamil|english|hindi|malayalam|telugu|kannada|urdu|french|"
    r"sanskrit|arabic|bengali|marathi|gujarati)$"
)
_MARKSHEET_HEADER_RE = re.compile(
    r"(?i)^(?:subject|subjects|theory|thory|practical|prac\.?|"
    r"marks?\s*obtained(?:\s*for)?(?:\s+\d{1,4})?|"
    r"and\s+obtained\s+the\s+following\s+marks)$"
)
_SLASH_LABEL_RE = re.compile(
    r"(?i)(?:^|[/／])\s*("
    r"date\s+of\s+birth|roll\s*no\.?|roll\s*number|"
    r"permanent\s+register\s*no\.?|medium\s+of\s+instruction|"
    r"group\s*code|name\s+of\s+the\s+school|name\s+of\s+school|"
    r"total\s*marks|t?mr\s*code\s*no\.?|code\s*no\.?|"
    r"certificate\s*sl\.?\s*no\.?|certificate\s*no\.?"
    r")\b"
)

# Column / section banners that are labels, never field values.
_HEADING_BANNER_RE = re.compile(
    r"(?i)^(?:marks?\s*obtained(?:\s*for)?(?:\s+\d{1,4})?|"
    r"and\s+obtained\s+the\s+following\s+marks|"
    r"subject|subjects|theory|thory|practical|prac\.?|"
    r"(?:gu\s*)?/?\s*name\s+of\s+the\s+school|"
    r"name\s+of\s+school)\s*:?\s*$"
)
_MAX_MARKS_BANNER_RE = re.compile(
    r"(?i)^marks?\s*obtained\s*for\s+(\d{1,4})\s*$"
)
_THEORY_HEADER_LINE_RE = re.compile(r"(?i)^(?:theory|thory)\s*:?\s*$")
_PRACTICAL_HEADER_LINE_RE = re.compile(r"(?i)^(?:practical|prac\.?)\s*:?\s*$")
_TOTAL_MARKS_LINE_RE = re.compile(
    r"(?i)^(?:(?:gl\s+\w+/)?total\s*marks?|grand\s*total)\s*:?\s*$"
)
_MR_CODE_FRAGMENT_RE = re.compile(r"^[A-Za-z]\d{1,5}$")
_MR_CODE_DIGITS_RE = re.compile(r"^\d{3,8}$")
_MR_CODE_FULL_RE = re.compile(r"^[A-Za-z]?\d{5,12}$")


def extract_mark_column_fields(text: str | None) -> list[dict[str, str]]:
    """Pull certificate-level Total Marks (once) — not Theory/Practical columns.

    Theory / Practical are per-subject score columns handled by
    ``scanx_academic_parse``; emitting them here duplicated marks into the
    Document fields table and made Theory/Practical look like categories.

    Still recognizes stacked maxima banners (THORY 160 / PRAC 50) only to
    reinforce Maximum Marks when ``MARKS OBTAINED FOR`` is absent.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    theory_max = ""
    practical_max = ""
    i = 0
    while i < len(lines) - 1:
        line = lines[i]
        nxt = lines[i + 1]
        if _THEORY_HEADER_LINE_RE.match(line) and re.fullmatch(r"\d{1,4}", nxt):
            theory_max = nxt
            i += 2
            continue
        if _PRACTICAL_HEADER_LINE_RE.match(line) and re.fullmatch(r"\d{1,4}", nxt):
            practical_max = nxt
            i += 2
            continue
        if _TOTAL_MARKS_LINE_RE.match(line) and re.fullmatch(r"\d{2,4}", nxt):
            _add_field(out, seen, label="Total Marks", value=nxt, category="academic")
            i += 2
            continue
        # Same-line certificate total only — ignore bare Theory:/Practical: scores.
        m_same = re.match(
            r"(?i)^(?:(?:gl\s+\w+/)?total\s*marks?|grand\s*total)"
            r"\s*[:\-–—|]?\s*(\d{1,4})\s*$",
            line,
        )
        if m_same:
            _add_field(
                out, seen, label="Total Marks", value=m_same.group(1), category="academic"
            )
        i += 1

    if theory_max and practical_max and not any(
        f.get("label") == "Maximum Marks" for f in out
    ):
        try:
            combined = str(int(theory_max) + int(practical_max))
            _add_field(
                out, seen, label="Maximum Marks", value=combined, category="academic"
            )
        except ValueError:
            pass

    # Explicit TOTAL row in a pipe table: "TOTAL | 824" / "Total Marks | 0824".
    for line in lines:
        cells = _split_table_cells(line)
        if len(cells) < 2:
            continue
        left = cells[0]
        if re.fullmatch(r"(?i)total(?:\s*marks?)?", left) or _TOTAL_MARKS_LINE_RE.match(left):
            # Skip subject-table header rows that include Theory|Practical|Total.
            if any(_THEORY_HEADER_LINE_RE.match(c) or _PRACTICAL_HEADER_LINE_RE.match(c) for c in cells):
                continue
            for cell in cells[1:]:
                if re.fullmatch(r"\d{2,4}", cell):
                    _add_field(
                        out, seen, label="Total Marks", value=cell, category="academic"
                    )
                    break

    return out


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def _split_table_cells(line: str) -> list[str]:
    raw = (line or "").strip()
    if not raw:
        return []
    if "|" in raw:
        return [_clean(c) for c in _PIPE_SPLIT_RE.split(raw) if _clean(c)]
    if "\t" in raw:
        return [_clean(c) for c in raw.split("\t") if _clean(c)]
    return []


def _resolve_alias(raw_label: str) -> tuple[str, str] | None:
    key = _clean(raw_label).lower().rstrip(".:#")
    if not key:
        return None
    for alias, canon, cat in _ALIAS_INDEX:
        if key == alias or key.rstrip(".") == alias.rstrip("."):
            return canon, cat
    # Soft match only for longer aliases ("roll number of candidate").
    for alias, canon, cat in _ALIAS_INDEX:
        if len(alias) < 8:
            continue
        if key.startswith(alias) and (
            len(key) == len(alias) or key[len(alias)] in " ./"
        ):
            return canon, cat
    # Shared rapidfuzz anchors (Sp0use / Name of Spouce / Foter, ...).
    try:
        from app.services.scanx_label_map import (
            best_fuzzy_alias,
            match_passport_field_label,
        )

        pk = match_passport_field_label(key)
        passport_to_ui = {
            "father_name": ("Father's Name", "identity"),
            "mother_name": ("Mother's Name", "identity"),
            "spouse_name": ("Spouse Name", "identity"),
            "date_of_birth": ("Date of Birth", "identity"),
            "nationality": ("Nationality", "identity"),
            "sex": ("Gender", "identity"),
        }
        if pk in passport_to_ui:
            return passport_to_ui[pk]
        aliases = [a for a, _, _ in _ALIAS_INDEX]
        hit = best_fuzzy_alias(key, aliases)
        if hit:
            alias_hit = hit[0]
            for alias, canon, cat in _ALIAS_INDEX:
                if alias == alias_hit:
                    return canon, cat
    except Exception:
        pass
    return None


def _value_ok(value: str, *, label: str) -> bool:
    v = _clean(value)
    if not v or len(v) > 400:
        return False
    # Reject values that are just another label / header remnant.
    if _resolve_alias(v) and len(v) < 40 and ":" not in v:
        return False
    if _line_is_label_only(v):
        return False
    lower = v.lower()
    if lower in {"n/a", "na", "-", "—", "nil", "none", "null", "for 200", "hsg", "went"}:
        return False
    if label.lower() in {
        "father's name",
        "mother's name",
        "spouse name",
        "guardian's name",
    }:
        if re.search(
            r"(?i)\b(?:legal|guardian|guardlan|curdian|address|went|spouse)\b",
            v,
        ):
            return False
        if re.search(r"(?i)(?:^|[\s/])(?:fn|afy|faf)(?:[\s/]|$)", v):
            return False
        if re.search(r"\b[A-Z]\d{7}\b", v, re.IGNORECASE):
            return False
        if re.fullmatch(r"(?i)(?:/|name)+", v):
            return False
    # Short / ambiguous headings must not swallow prose sentences.
    short_labels = {
        "code number",
        "year",
        "year of passing",
        "class",
        "grade",
        "roll number",
        "board",
        "school",
        "college",
        "exam",
        "session",
        "result",
        "stream",
        "phone",
        "email",
        "medium of instruction",
        "group code",
        "tmr code no",
        "mr code no",
    }
    if label.lower() in short_labels and len(v) > 80:
        return False
    if label.lower() in short_labels and re.match(
        r"(?i)^(of|for|to|the|and|in|on|at|with|from)\b", v
    ):
        return False
    # DOB / dates must look like dates when label is DOB.
    if label.lower() == "date of birth" and not _DATE_VALUE_RE.match(v):
        return False
    if label.lower() == "nationality":
        # Reject Sex / DOB bleed and unknown OCR soup; allow known demonyms / ISO codes.
        from app.services.scanx_passport import is_plausible_nationality

        if not is_plausible_nationality(v):
            return False
    if label.lower() in {"tmr code no", "mr code no", "issue date"} and re.fullmatch(
        r"(?i)(?:no\.?\s*)?date|no\.?", v
    ):
        return False
    if label.lower() == "issue date" and not _DATE_VALUE_RE.match(v):
        return False
    if label.lower() == "maximum marks" and not re.fullmatch(r"\d{1,4}(?:\.\d{1,2})?", v):
        return False
    if label.lower() == "permanent register no" and re.fullmatch(r"(?i)no\.?", v):
        return False
    if label.lower() == "board" and (
        len(v) < 12 or not re.search(r"(?i)board|examin", v)
    ):
        return False
    return True


def _looks_like_generic_label(label: str) -> bool:
    lab = _clean(label)
    if len(lab) < 2 or len(lab) > 50:
        return False
    if not _LABELISH_RE.match(lab):
        return False
    # Reject value-like tokens mistaken as headings (G52, 6345, A12…).
    if re.fullmatch(r"[A-Za-z]?\d{2,12}", lab):
        return False
    if re.fullmatch(r"\d{2,}", lab):
        return False
    if sum(ch.isdigit() for ch in lab) > max(2, len(lab) // 4):
        return False
    lower = lab.lower()
    if lower in {"subject", "marks", "score", "grade", "total", "s.no", "s no", "sl no"}:
        return False
    # Reject prose / marksheet narrative lines mistaken as headings.
    if re.match(r"(?i)^(and|or|the|with|obtained|following)\b", lower):
        return False
    if "obtained the following" in lower:
        return False
    if _HEADING_BANNER_RE.match(lab):
        return False
    return True


def is_heading_or_label_line(line: str) -> bool:
    """True for known OCR headings/banners that must never become field values."""
    cleaned = _clean(line)
    if not cleaned:
        return False
    if _HEADING_BANNER_RE.match(cleaned) or _MARKSHEET_HEADER_RE.match(cleaned):
        return True
    if _MAX_MARKS_BANNER_RE.match(cleaned):
        return True
    if _line_is_label_only(cleaned):
        return True
    # Bilingual school heading with OCR noise prefix (GU /NAME OF THE SCHOOL).
    if re.search(r"(?i)name\s+of\s+the\s+school", cleaned) and len(cleaned) < 48:
        if not re.search(
            r"(?i)\b(?:infant|jesus|hr|higher|secondary|vidyalaya|matriculation)\b",
            cleaned,
        ):
            return True
    return False


def merge_code_fragments(values: list[str]) -> list[str]:
    """Merge OCR-split codes like ``G52`` + ``6345`` → ``G526345``."""
    out: list[str] = []
    i = 0
    while i < len(values):
        cur = _clean(values[i])
        if i + 1 < len(values):
            nxt = _clean(values[i + 1])
            if _MR_CODE_FRAGMENT_RE.match(cur) and _MR_CODE_DIGITS_RE.match(nxt):
                out.append(cur + nxt)
                i += 2
                continue
        out.append(cur)
        i += 1
    return out


def _prefer_field_value(label: str, current: str, candidate: str) -> str:
    """Prefer longer / more complete values for the same canonical label."""
    cur = _clean(current)
    cand = _clean(candidate)
    if not cand:
        return cur
    if not cur:
        return cand
    if not _value_ok(cand, label=label):
        return cur
    lab = label.lower()
    if lab in {"tmr code no", "mr code no", "code number"}:
        if _MR_CODE_FULL_RE.match(cand) and not _MR_CODE_FULL_RE.match(cur):
            return cand
        if len(cand) > len(cur) and re.search(r"[A-Za-z]", cand):
            return cand
    if len(cand) > len(cur) + 2:
        return cand
    return cur


def _add_field(
    out: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    label: str,
    value: str,
    category: str,
    occupied: list[tuple[int, int]] | None = None,
    start: int | None = None,
    end: int | None = None,
    prefer_label: bool = False,
) -> None:
    lab = _clean(label)
    val = _clean(value)
    if not lab or not _value_ok(val, label=lab):
        return
    # Never store heading banners as values.
    if is_heading_or_label_line(val) or _HEADING_BANNER_RE.match(val):
        return
    label_key = lab.lower()
    # Upgrade existing shorter value for the same canonical label.
    for idx, existing in enumerate(out):
        if (existing.get("label") or "").lower() != label_key:
            continue
        if category != "other" and (existing.get("category") or "") != "other":
            better = _prefer_field_value(lab, existing.get("value") or "", val)
            if better != _clean(existing.get("value") or ""):
                old_pair = (label_key, _clean(existing.get("value") or "").lower())
                seen.discard(old_pair)
                existing["value"] = better[:500]
                seen.add((label_key, better.lower()))
            return
        break
    known_label_taken = any(existing_lab == label_key for existing_lab, _ in seen)
    if known_label_taken and (not prefer_label or category != "other"):
        return
    key = (lab.lower(), val.lower())
    if key in seen:
        return
    seen.add(key)
    out.append({"label": lab[:120], "value": val[:500], "category": category})
    if occupied is not None and start is not None and end is not None and end > start:
        occupied.append((start, end))


def _english_fragments(line: str) -> list[str]:
    """Pull likely English heading fragments from bilingual OCR lines."""
    cleaned = _clean(line)
    if not cleaned:
        return []
    # Prefer English fragments after ``/`` first so bilingual noise does not
    # shadow the real heading (``LD. & /MR CODE NO. DATE``).
    parts = re.split(r"[/／]", cleaned)
    out: list[str] = []
    for part in reversed(parts):  # last segment is usually the English label
        frag = _clean(re.sub(r"^[^A-Za-z]+", "", part))
        frag = frag.rstrip(".:#")
        frag = re.sub(r"^[.&]+\s*", "", frag)
        if frag and re.search(r"[A-Za-z]{2,}", frag) and frag not in out:
            out.append(frag)
    for part in parts:
        frag = _clean(re.sub(r"^[^A-Za-z]+", "", part))
        frag = frag.rstrip(".:#")
        frag = re.sub(r"^[.&]+\s*", "", frag)
        if frag and re.search(r"[A-Za-z]{2,}", frag) and frag not in out:
            out.append(frag)
    return out


def _labels_from_line(line: str) -> list[tuple[str, str]]:
    """Return zero or more (canonical, category) labels detected on a line."""
    found: list[tuple[str, str]] = []
    seen_canon: set[str] = set()

    def _push(resolved: tuple[str, str] | None) -> None:
        if resolved and resolved[0] not in seen_canon:
            seen_canon.add(resolved[0])
            found.append(resolved)

    def _resolve_noisy(piece: str) -> tuple[str, str] | None:
        resolved = _resolve_alias(piece)
        if resolved:
            return resolved
        # ``LD. & /MR CODE NO`` → try after last slash / trailing english.
        for frag in _english_fragments(piece):
            resolved = _resolve_alias(frag)
            if resolved:
                return resolved
        for sm in _SLASH_LABEL_RE.finditer(piece):
            resolved = _resolve_alias(sm.group(1))
            if resolved:
                return resolved
        return None

    for frag in _english_fragments(line):
        # "TMR CODE NO. DATE" / "MR CODE NO. DATE" / "LD. & /TMR CODE NO. DATE"
        m = re.match(r"(?i)^(.+?\bcode\s*no\.?)\s+date$", frag)
        if m:
            _push(_resolve_noisy(m.group(1)))
            _push(("Issue Date", "academic"))
            continue
        _push(_resolve_alias(frag))
        # Slash-anchored known phrases even inside noisy fragments.
        for sm in _SLASH_LABEL_RE.finditer(frag if "/" not in (line or "") else (line or "")):
            _push(_resolve_alias(sm.group(1)))
    # Direct slash search on full line when fragments missed.
    if not found:
        for sm in _SLASH_LABEL_RE.finditer(line or ""):
            _push(_resolve_alias(sm.group(1)))
    return found


def _line_is_label_only(line: str) -> bool:
    return bool(_labels_from_line(line)) and not _looks_like_stacked_value(line)


def _looks_like_stacked_value(line: str) -> bool:
    v = _clean(line)
    if not v or len(v) > 120:
        return False
    if _MARKSHEET_HEADER_RE.match(v) or _NUMBER_WORDS_RE.match(v):
        return False
    if _labels_from_line(v) and not _DATE_VALUE_RE.match(v) and not _MEDIUM_VALUE_RE.match(v):
        # Pure label lines are not values.
        if not re.search(r"\d", v) and len(v) < 60:
            return False
    if _DATE_VALUE_RE.match(v) or _SESSION_VALUE_RE.match(v):
        return True
    if _MEDIUM_VALUE_RE.match(v):
        return True
    # TMR/MR OCR fragments (G52) and full codes (G526345).
    if _MR_CODE_FRAGMENT_RE.match(v) or _MR_CODE_FULL_RE.match(v):
        return True
    if re.fullmatch(r"[A-Z]?\d{3,12}", v):
        return True
    if re.fullmatch(r"\d{2,4}", v):
        return True
    if re.fullmatch(r"[A-Za-z]\d{4,10}", v):
        return True
    # School / institution lines (value before "NAME OF THE SCHOOL").
    if len(v) >= 12 and re.search(r"(?i)\b(?:school|college|vidyalaya|higher\s+secondary)\b", v):
        return True
    # Candidate-like ALLCAPS name (2–4 tokens, no digits).
    if (
        re.fullmatch(r"[A-Z][A-Z .']{1,40}", v)
        and 1 <= len(v.split()) <= 4
        and not _SUBJECT_NAME_RE.match(v)
        and not re.search(r"(?i)\b(?:BOARD|DEPARTMENT|GOVERNMENT|CERTIFICATE|SECRETARY)\b", v)
    ):
        return True
    return False


def _skip_stacked_line(line: str) -> bool:
    v = _clean(line)
    if not v:
        return True
    if _MARKSHEET_HEADER_RE.match(v) or _NUMBER_WORDS_RE.match(v):
        return True
    if re.fullmatch(r"\(?[A-Za-z][A-Za-z+\-]{0,12}\)?", v) and len(v) <= 6:
        return True
    if _SUBJECT_NAME_RE.match(v):
        return True
    if re.fullmatch(r"\d{1,3}", v):  # theory/practical mark alone inside block
        # Still usable as group code — keep if not inside subject stack.
        return False
    return False


def parse_stacked_labeled_fields(text: str | None) -> list[dict[str, str]]:
    """Pair stacked OCR label rows with following value rows (TN HSC style).

    Typical layout::

        /DATE OF BIRTH
        G/ ROLL NO.
        .LD. & /TMR CODE NO. DATE
        06.06.1999
        478100
        G526345
        17.05.2016
        U/ PERMANENT REGISTER NO.
        ug Q/MEDIUM OF INSTRUCTION
        Lm_ e / GROUP CODE
        1610468100
        TAMIL
        103
        INFANT JESUS HR SEC SCHOOL …
        GU /NAME OF THE SCHOOL
    """
    raw = (text or "").strip()
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    i = 0
    while i < len(lines):
        labels = _labels_from_line(lines[i])
        if not labels:
            # Value-before-label: school name then NAME OF THE SCHOOL.
            if _looks_like_stacked_value(lines[i]) and i + 1 < len(lines):
                next_labels = _labels_from_line(lines[i + 1])
                if len(next_labels) == 1 and next_labels[0][0] in {
                    "School",
                    "College",
                    "University",
                    "Candidate Name",
                }:
                    _add_field(
                        out,
                        seen,
                        label=next_labels[0][0],
                        value=lines[i],
                        category=next_labels[0][1],
                    )
                    i += 2
                    continue
            # Certificate serial: digits then CERTIFICATE SL. NO.
            if re.fullmatch(r"\d{6,12}", _clean(lines[i])) and i + 1 < len(lines):
                next_labels = _labels_from_line(lines[i + 1])
                if next_labels and next_labels[0][0] == "Certificate No":
                    _add_field(
                        out,
                        seen,
                        label="Certificate No",
                        value=lines[i],
                        category="academic",
                    )
                    # Optional type token on the label line (HSG).
                    cert_line = _clean(lines[i + 1])
                    m_type = re.search(r"(?i)\b(HSG|HSE|SSLC|CBSE|ICSE)\b", cert_line)
                    if m_type:
                        _add_field(
                            out,
                            seen,
                            label="Certificate Type",
                            value=m_type.group(1),
                            category="academic",
                            prefer_label=True,
                        )
                    i += 2
                    continue
            # Candidate name + session (MAR 2016) near top of certificate.
            if (
                _looks_like_stacked_value(lines[i])
                and re.fullmatch(r"[A-Z][A-Z .']{1,40}", _clean(lines[i]))
                and i + 1 < len(lines)
                and _SESSION_VALUE_RE.match(_clean(lines[i + 1]))
            ):
                _add_field(
                    out,
                    seen,
                    label="Candidate Name",
                    value=lines[i],
                    category="identity",
                )
                _add_field(
                    out,
                    seen,
                    label="Session",
                    value=lines[i + 1],
                    category="academic",
                )
                i += 2
                continue
            i += 1
            continue

        # Collect consecutive label lines (multi-column header row OCR'd vertically).
        label_run: list[tuple[str, str]] = []
        j = i
        while j < len(lines):
            labs = _labels_from_line(lines[j])
            if not labs:
                break
            # Skip pure marksheet headers mistaken as labels.
            if _MARKSHEET_HEADER_RE.match(_clean(lines[j])):
                break
            label_run.extend(labs)
            j += 1
        if not label_run:
            i += 1
            continue

        # Collect following value lines.
        values: list[str] = []
        k = j
        # Allow a couple of extra raw tokens so OCR-split codes (G52+6345)
        # can merge and still leave room for Issue Date / etc.
        max_raw = len(label_run) + 2
        while k < len(lines) and len(values) < max_raw:
            if _labels_from_line(lines[k]):
                break
            if _skip_stacked_line(lines[k]) and not _looks_like_stacked_value(lines[k]):
                k += 1
                continue
            if _looks_like_stacked_value(lines[k]):
                candidate = _clean(lines[k])
                # Don't swallow the school-name line into the DOB/Roll block.
                if (
                    len(values) >= len(label_run)
                    and len(candidate) >= 12
                    and re.search(
                        r"(?i)\b(?:school|college|vidyalaya|higher\s+secondary)\b",
                        candidate,
                    )
                ):
                    break
                values.append(candidate)
                k += 1
                continue
            break

        # Merge OCR-split TMR/MR codes (G52 + 6345 → G526345) before zip.
        values = merge_code_fragments(values)
        # Keep only as many values as labels (extras may be school name).
        if len(values) > len(label_run):
            # Prefer dropping trailing school-like values, not dates/codes.
            trimmed: list[str] = []
            for val in values:
                if len(trimmed) >= len(label_run):
                    break
                trimmed.append(val)
            values = trimmed

        # Zip labels to values in order (TN HSC footer block).
        for idx, (canon, cat) in enumerate(label_run):
            if idx >= len(values):
                break
            val = values[idx]
            # Medium prefers language tokens; skip if mismatched later.
            if canon == "Medium of Instruction" and not _MEDIUM_VALUE_RE.match(val):
                # Try to find a medium token among remaining values.
                for alt in values[idx:]:
                    if _MEDIUM_VALUE_RE.match(alt):
                        val = alt
                        break
            if canon == "Date of Birth" and not _DATE_VALUE_RE.match(val):
                for alt in values:
                    if _DATE_VALUE_RE.match(alt):
                        val = alt
                        break
            if canon == "Issue Date" and not _DATE_VALUE_RE.match(val):
                for alt in values[idx:]:
                    if _DATE_VALUE_RE.match(alt):
                        val = alt
                        break
            if canon == "Group Code" and not re.fullmatch(r"\d{2,4}", val):
                for alt in values[idx:]:
                    if re.fullmatch(r"\d{2,4}", alt):
                        val = alt
                        break
            if canon in {"TMR Code No", "MR Code No"}:
                # Prefer a full merged code among remaining values.
                if not _MR_CODE_FULL_RE.match(val) or _MR_CODE_FRAGMENT_RE.match(val):
                    for alt in values[idx:]:
                        if _MR_CODE_FULL_RE.match(alt) and len(alt) >= 6:
                            val = alt
                            break
            _add_field(out, seen, label=canon, value=val, category=cat)

        i = k if k > i else i + 1

    # Maximum marks banner: "MARKS OBTAINED FOR 200"
    for line in lines:
        m_max = _MAX_MARKS_BANNER_RE.match(_clean(line))
        if m_max:
            _add_field(
                out,
                seen,
                label="Maximum Marks",
                value=m_max.group(1),
                category="academic",
            )
            break

    # Board line heuristic from early certificate text.
    for line in lines[:12]:
        if re.search(r"(?i)state\s+board\s+of\s+school\s+examinations", line):
            _add_field(
                out,
                seen,
                label="Board",
                value=_clean(line),
                category="academic",
            )
            break
    for line in lines[:16]:
        if re.search(r"(?i)higher\s+secondary\s+course\s+certificate", line):
            _add_field(
                out,
                seen,
                label="Exam",
                value=_clean(line),
                category="academic",
            )
            break
    for line in lines[:16]:
        if re.search(r"(?i)general\s+education", line):
            m = re.search(r"(?i)general\s+education", line)
            if m:
                _add_field(
                    out,
                    seen,
                    label="Stream",
                    value="GENERAL EDUCATION",
                    category="academic",
                )
            break

    return out


def merge_fields(
    *batches: list[dict[str, str]],
    limit: int = 80,
) -> list[dict[str, str]]:
    """Dedupe field rows by normalized label; prefer longer/more complete values."""
    out: list[dict[str, str]] = []
    seen_pair: set[tuple[str, str]] = set()
    index_by_label: dict[str, int] = {}
    for batch in batches:
        for item in batch or []:
            if not isinstance(item, dict):
                continue
            lab = _clean(item.get("label") or "")
            val = _clean(item.get("value") or "")
            cat = _clean(item.get("category") or "other") or "other"
            if not lab or not val:
                continue
            if is_heading_or_label_line(val) or not _value_ok(val, label=lab):
                continue
            # Collapse OCR-split TMR fragments only when a fuller sibling exists later.
            if lab.lower() in {"tmr code no", "mr code no"} and _MR_CODE_FRAGMENT_RE.match(val):
                # Keep for now; a later longer value will upgrade via prefer.
                pass
            # Normalize legacy "MR Code No" / "Total Scores" labels onto current canons.
            if lab.lower() == "mr code no":
                lab = "TMR Code No"
            if lab.lower() == "total scores":
                lab = "Total Marks"
            pair = (lab.lower(), val.lower())
            if pair in seen_pair:
                continue
            label_key = lab.lower()
            if label_key != "other" and cat != "other" and label_key in index_by_label:
                idx = index_by_label[label_key]
                better = _prefer_field_value(lab, out[idx]["value"], val)
                if better != out[idx]["value"]:
                    old_pair = (label_key, out[idx]["value"].lower())
                    seen_pair.discard(old_pair)
                    out[idx]["value"] = better[:500]
                    seen_pair.add((label_key, better.lower()))
                continue
            seen_pair.add(pair)
            if label_key != "other" and cat != "other":
                index_by_label[label_key] = len(out)
            out.append({"label": lab[:120], "value": val[:500], "category": cat})
            if len(out) >= limit:
                return out
    return out


def extract_labeled_fields(
    text: str | None,
    *,
    occupied: list[tuple[int, int]] | None = None,
) -> list[dict[str, str]]:
    """Parse heading→value pairs from free text, tables, and stacked OCR.

    Returns items shaped as::
        {"label": "Date of Birth", "value": "…", "category": "identity"|"academic"|"contact"|"other"}
    """
    raw = text or ""
    if not raw.strip():
        return []

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    span_sink = occupied if occupied is not None else []

    # 1) Known dictionary aliases (same line only).
    for pattern in (_KNOWN_LONG_RE, _KNOWN_SHORT_RE):
        for m in pattern.finditer(raw):
            resolved = _resolve_alias(m.group(1))
            if not resolved:
                continue
            canon, cat = resolved
            value = m.group(2)
            value = re.split(r"[^\S\n]{2,}|[^\S\n]+\|[^\S\n]+", value, maxsplit=1)[0]
            # Reject when the "value" is actually the next stacked label.
            if _line_is_label_only(value) or _labels_from_line(value):
                continue
            # Reject truncated OCR tails like "NO. DATE" / bare "DATE".
            if re.fullmatch(r"(?i)(?:no\.?\s*)?date|no\.?", _clean(value)):
                continue
            _add_field(
                out,
                seen,
                label=canon,
                value=value,
                category=cat,
                occupied=span_sink,
                start=m.start(),
                end=m.end(),
            )

    # 2) Generic Label: value lines (unknown headings → other / resolved if alias).
    for m in _GENERIC_LABELED_RE.finditer(raw):
        raw_label = m.group("label")
        value = m.group("value")
        resolved = _resolve_alias(raw_label)
        if not resolved:
            line_labels = _labels_from_line(raw_label)
            if len(line_labels) == 1:
                resolved = line_labels[0]
        if resolved:
            canon, cat = resolved
        else:
            if not _looks_like_generic_label(raw_label):
                continue
            canon, cat = _clean(raw_label).rstrip(".:"), "other"
        key = (canon.lower(), _clean(value).lower())
        if key in seen:
            continue
        if _labels_from_line(value):
            continue
        _add_field(
            out,
            seen,
            label=canon,
            value=value,
            category=cat,
            occupied=span_sink,
            start=m.start(),
            end=m.end(),
            prefer_label=True,
        )

    # 3) Two-cell table rows: Label | Value or Label \t Value
    for line in raw.splitlines():
        cells = _split_table_cells(line)
        if len(cells) != 2:
            if len(cells) >= 2 and _looks_like_generic_label(cells[0]):
                left, right = cells[0], cells[1]
            else:
                continue
        else:
            left, right = cells[0], cells[1]
        resolved = _resolve_alias(left)
        if resolved:
            canon, cat = resolved
        elif _looks_like_generic_label(left) and not re.fullmatch(r"[\d./\-]+", right):
            if left.lower() in {"subject", "subjects", "marks", "score", "grade"}:
                continue
            if right.lower() in {"marks", "score", "grade", "subject", "obtained"}:
                continue
            canon, cat = left, "other"
        else:
            continue
        idx = raw.find(line)
        start = idx if idx >= 0 else None
        end = (idx + len(line)) if idx >= 0 else None
        _add_field(
            out,
            seen,
            label=canon,
            value=right,
            category=cat,
            occupied=span_sink,
            start=start,
            end=end,
            prefer_label=True,
        )

    # 4) Stacked bilingual OCR (label lines → value lines).
    stacked = parse_stacked_labeled_fields(raw)
    for item in stacked:
        _add_field(
            out,
            seen,
            label=item["label"],
            value=item["value"],
            category=item.get("category") or "other",
            prefer_label=True,
        )

    # 5) Certificate Total Marks only (Theory/Practical stay on subject rows).
    for item in extract_mark_column_fields(raw):
        _add_field(
            out,
            seen,
            label=item["label"],
            value=item["value"],
            category=item.get("category") or "academic",
            prefer_label=True,
        )

    return out


def fields_by_category(fields: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group extract results into identity / academic / contact / other item lists."""
    buckets: dict[str, list[dict[str, str]]] = {
        "identity": [],
        "academic": [],
        "contact": [],
        "other": [],
    }
    for item in fields:
        cat = (item.get("category") or "other").lower()
        if cat not in buckets:
            cat = "other"
        buckets[cat].append(
            {
                "label": item.get("label") or "Field",
                "value": item.get("value") or "",
            }
        )
    return buckets


def extract_fields_payload(text: str | None) -> list[dict[str, Any]]:
    """Public helper returning the structured field list for storage / tests."""
    return extract_labeled_fields(text)


def resolve_fields_from_text(
    text: str | None,
    *,
    use_llm: bool = True,
    prior_fields: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Heuristic field extract, optionally merged with Ollama key-value JSON.

    LLM runs when heuristics miss key transcript fields (DOB / Roll / Group Code)
    on marksheet-like text. Prefer recall: merge LLM into heuristic.
    """
    from app.config import settings
    from app.services.scanx_academic_parse import looks_like_marksheet

    heuristic = extract_labeled_fields(text)
    labels = {(f.get("label") or "").lower() for f in heuristic}
    key_missing = not (
        {"date of birth", "roll number", "group code"} <= labels
        or (
            "date of birth" in labels
            and "roll number" in labels
            and "permanent register no" in labels
        )
    )

    llm_rows: list[dict[str, str]] = []
    if use_llm and looks_like_marksheet(text) and key_missing:
        if getattr(settings, "SCANX_LLM_FIELDS_ENABLED", True):
            try:
                from app.services.scanx_llm_fields import extract_fields_via_llm

                llm_rows = extract_fields_via_llm(text)
            except Exception:
                llm_rows = []
    return merge_fields(prior_fields or [], heuristic, llm_rows)
