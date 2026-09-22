"""Shared academic / marksheet subject+marks parsing for ScanX.

Used by DOCX table extract, PDF (pdfplumber) table extract, OCR text, and the
categorizer so all paths produce the same shape::

    {"name", "marks", "grade?", "theory?", "practical?", "total?"}

``marks`` is the consolidated obtained score (prefer ``total`` when theory and
practical columns both exist). Theory and Practical are **per-subject score
columns**, never separate subject lists or document-field categories.
"""

from __future__ import annotations

import re
from typing import Any

_WS_RE = re.compile(r"\s+")
_PIPE_SPLIT_RE = re.compile(r"\s*\|\s*")
# Two-or-more spaces / tabs → loose column split (layout PDF / OCR).
_MULTI_SPACE_SPLIT_RE = re.compile(r"[ \t]{2,}")
# Leading serial / S.No on marksheet rows: "1 English 72", "1. Physics … 85".
_SERIAL_PREFIX_RE = re.compile(r"^(?:\d{1,4}[.)]|#?\d{1,4})\s+")
# Scores may exceed 100 (e.g. Tamil 169 / 200). Allow up to 4 integer digits.
_MARKS_NUM_RE = r"\d{1,4}(?:\.\d{1,2})?(?:\s*/\s*\d{1,4}(?:\.\d{1,2})?)?"
_MARKS_TOKEN_RE = re.compile(rf"^{_MARKS_NUM_RE}$")
_GRADE_TOKEN_RE = re.compile(
    r"(?i)^(?:[A-F][+-]?|Pass|Fail|Distinction|First|Second|Third)$"
)
# Labeled OCR pairs: "Subject: Tamil" then "Marks: 169" (or same line).
_SUBJECT_LABEL_LINE_RE = re.compile(
    r"(?i)^(?:subject|paper|course|module)(?:\s*name)?\s*[:\-–—|]?\s*(.+)$"
)
_MARKS_LABEL_LINE_RE = re.compile(
    rf"(?i)^(?:marks?|score|marks?\s*obtained|obtained(?:\s*marks?)?|scored)"
    rf"(?:\s*obtained)?\s*[:\-–—|]?\s*({_MARKS_NUM_RE})\s*$"
)
_SUBJECT_MARKS_SAME_LINE_RE = re.compile(
    rf"(?iu)(?:subject|paper|course)\s*[:\-–—|]?\s*"
    rf"(?P<name>[^\W\d_](?:[^\W\d_]|[\s.,&'/\-]){{1,60}}?)\s+"
    rf"(?:marks?|score)\s*[:\-–—|]?\s*(?P<marks>{_MARKS_NUM_RE})\b"
)

_SUBJECT_HEADER_RE = re.compile(
    r"(?i)^(subject|subjects|course(?:\s*name)?|paper(?:\s*name)?|module|unit|"
    r"subject\s*/?\s*paper|course\s*title)$"
)
# Generic marks headers — Theory/Practical/Total handled as dedicated roles.
_MARKS_HEADER_RE = re.compile(
    r"(?i)^(marks?|score|obtained|max(?:imum)?|total|percent(?:age)?|%|"
    r"marks?\s*obtained|marks?\s*obt)$"
)
_GRADE_HEADER_RE = re.compile(
    r"(?i)^(grade|result|division|class|letter\s*grade)$"
)
_SERIAL_HEADER_RE = re.compile(
    r"(?i)^(s\.?\s*no\.?|sl\.?\s*no\.?|serial|no\.?|#)$"
)

# Prefer obtained/scored marks over maximum/out-of columns.
_MARKS_HEADER_PRIORITY: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"(?i)obtained|scored|secured|marks?\s*obt"), 100),
    (re.compile(r"(?i)^total(?:\s*marks?)?$"), 90),
    (re.compile(r"(?i)^(marks?|score)$"), 80),
    (re.compile(r"(?i)\bmarks?\b|\bscore\b"), 70),
    (re.compile(r"(?i)^total$"), 65),
    (re.compile(r"(?i)percent|%"), 40),
    (re.compile(r"(?i)^max(?:imum)?|out\s*of"), 10),
]

_THEORY_HEADER_RE = re.compile(
    r"(?i)^(?:theory|thory|theo\.?|th\.?)$"
)
_PRACTICAL_HEADER_RE = re.compile(
    # Prac / Pract / Pracal (common OCR) / Practical
    r"(?i)^(?:practical|pracal|prac\.?|pract\.?|pr\.?)$"
)
_TOTAL_MARKS_HEADER_RE = re.compile(
    r"(?i)^(?:total(?:\s*marks?)?|tot\.?|marks?\s*obtained|grand\s*total)$"
)

# Labels that must never be treated as subject names.
_SUBJECT_NAME_DENY = frozenset(
    {
        "subject",
        "subjects",
        "course",
        "course name",
        "paper",
        "module",
        "unit",
        "marks",
        "mark",
        "score",
        "obtained",
        "marks obtained",
        "marks obtained for",
        "grade",
        "total",
        "grand total",
        "aggregate",
        "percentage",
        "percent",
        "cgpa",
        "gpa",
        "result",
        "roll",
        "roll no",
        "roll number",
        "registration",
        "registration no",
        "name",
        "candidate name",
        "student name",
        "father's name",
        "mother's name",
        "date of birth",
        "dob",
        "board",
        "school",
        "college",
        "university",
        "session",
        "year",
        "exam",
        "examination",
        "s.no",
        "s no",
        "sl no",
        "sl.no",
        "serial",
        "code",
        "maximum",
        "max marks",
        "out of",
        "theory",
        "thory",  # common OCR typo for THEORY
        "practical",
        "prac",
        "prac.",
        "pracal",
        "certificate",
        "department",
        "government",
        "examinations",
        "higher secondary",
        "general education",
        "medium of instruction",
        "group code",
        "permanent register no",
        "member secretary",
        "name of the school",
        "mar",
        "jan",
        "feb",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    }
)

# Number-words line after a score: "ONE SIX NINE"
_NUMBER_WORDS_RE = re.compile(
    r"(?i)^(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|"
    r"ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|"
    r"EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|SIXTY|SEVENTY|"
    r"EIGHTY|NINETY|HUNDRED)(?:\s+(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|"
    r"SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|THIRTEEN|FOURTEEN|FIFTEEN|"
    r"SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|TWENTY|THIRTY|FORTY|FIFTY|"
    r"SIXTY|SEVENTY|EIGHTY|NINETY|HUNDRED)){0,8}$"
)
_PAREN_GRADE_RE = re.compile(
    r"(?i)^(?:\(([A-Za-z][A-Za-z+\-]{0,12})\)|([A-F][+-]?|Pass|Fail|Distinction))$"
)
_MARKSHEET_SIGNAL_RE = re.compile(
    r"(?i)\b(?:subject|subjects|marks?\s*obtained|grade\s*sheet|mark\s*sheet|"
    r"marksheet|transcript|higher\s+secondary|obtained\s+the\s+following\s+marks)\b"
)
_STACKED_HEADER_SKIP_RE = re.compile(
    r"(?i)^(?:subject|subjects|theory|thory|practical|pracal|prac\.?|marks?\s*obtained(?:\s*for)?|"
    r"max(?:imum)?|total|score|paper|course|s\.?\s*no\.?|serial|#)$"
)
_STACKED_BLOCK_END_RE = re.compile(
    r"(?i)(?:date\s*of\s*birth|roll\s*no|permanent\s*register|medium\s*of\s*instruction|group\s*code|"
    r"name\s*of\s*the\s*school|member\s*secretary|result|remarks)\b"
)
# Soft boundary: total/aggregate may appear mid-block when OCR reading order
# puts TOTAL MARKS before a trailing subject (e.g. Mathematics on DOCX scans).
_STACKED_TOTAL_LINE_RE = re.compile(
    r"(?i)(?:total\s*marks|grand\s*total|aggregate|percentage)\b"
)

# Line: SubjectName 85  or  SubjectName: 169  or  SubjectName – 169
# Names may be Latin or local-script (Tamil, etc.).
_LINE_SUBJECT_MARKS_RE = re.compile(
    rf"(?xu)"
    rf"^(?P<name>[^\W\d_](?:[^\W\d_]|[\s.,&'/\-]){{1,60}}?)"
    rf"(?:\s*[\|:\-–—]\s*|\s{{1,}})"
    rf"(?P<marks>{_MARKS_NUM_RE})"
    rf"(?:\s*[\|,]?\s*(?P<grade>[A-F][+-]?|Pass|Fail|Distinction|First|Second|Third))?"
    rf"\s*$",
    re.IGNORECASE,
)

# Dot / ellipsis leaders: "1. Physics .................... 85"
_DOT_LEADER_RE = re.compile(
    rf"(?xu)"
    rf"^(?P<name>[^\W\d_](?:[^\W\d_]|[\s.,&'/\-]){{1,60}}?)"
    rf"\s*[\.·•…]{{2,}}\s*"
    rf"(?P<marks>{_MARKS_NUM_RE})"
    rf"(?:\s+(?P<grade>[A-F][+-]?|Pass|Fail|Distinction))?"
    rf"\s*$",
    re.IGNORECASE,
)

# Name + several trailing numbers (Theory / Practical / Total) → last is marks.
_MULTI_NUM_TAIL_RE = re.compile(
    r"(?xu)"
    r"^(?P<name>[^\W\d_](?:[^\W\d_]|[\s.,&'/\-]){1,60}?)"
    r"(?P<nums>(?:\s+\d{1,4}(?:\.\d{1,2})?){2,4})"
    r"(?:\s+(?P<grade>[A-F][+-]?|Pass|Fail|Distinction))?"
    r"\s*$",
    re.IGNORECASE,
)

# Pipe row without header: Name | 85 | A
_PIPE_SUBJECT_RE = re.compile(
    rf"(?xu)"
    rf"^(?P<name>[^\W\d_](?:[^\W\d_]|[\s.,&'/\-]){{1,60}}?)"
    rf"\s*\|\s*"
    rf"(?P<marks>{_MARKS_NUM_RE})"
    rf"(?:\s*\|\s*(?P<grade>[A-Za-z][A-Za-z+\-]{{0,20}}))?"
    rf"\s*$",
)


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def _strip_serial_prefix(line: str) -> str:
    return _SERIAL_PREFIX_RE.sub("", _clean(line)).strip()


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


def _split_loose_columns(line: str) -> list[str]:
    """Split layout-style rows on 2+ spaces when pipe/tab split is empty."""
    raw = (line or "").strip()
    if not raw:
        return []
    cells = _split_table_cells(raw)
    if len(cells) >= 2:
        return cells
    parts = [_clean(p) for p in _MULTI_SPACE_SPLIT_RE.split(raw) if _clean(p)]
    return parts if len(parts) >= 2 else []


def _whitespace_tokens(line: str) -> list[str]:
    return [_clean(t) for t in (line or "").split() if _clean(t)]


def _marks_header_score(token: str) -> int:
    best = 0
    for pattern, score in _MARKS_HEADER_PRIORITY:
        if pattern.search(token):
            best = max(best, score)
    return best


def header_column_map(cells: list[str]) -> dict[str, int] | None:
    """Map subject/marks/grade roles from a header row. Requires a subject column.

    Also records ``theory``, ``practical``, and ``total`` column indexes when
    present so each subject row can carry per-column scores. Theory/Practical
    are never treated as separate subject lists.
    """
    roles: dict[str, int] = {}
    marks_candidates: list[tuple[int, int]] = []  # (priority, idx)
    for idx, cell in enumerate(cells):
        token = _clean(cell)
        if not token:
            continue
        lower = token.lower()
        if _SERIAL_HEADER_RE.match(token):
            roles.setdefault("serial", idx)
            continue
        if "subject" not in roles and (
            _SUBJECT_HEADER_RE.match(token) or lower in {"subjects", "course title"}
        ):
            roles["subject"] = idx
            continue
        if "theory" not in roles and _THEORY_HEADER_RE.match(token):
            roles["theory"] = idx
            continue
        if "practical" not in roles and _PRACTICAL_HEADER_RE.match(token):
            roles["practical"] = idx
            continue
        if "total" not in roles and _TOTAL_MARKS_HEADER_RE.match(token):
            roles["total"] = idx
            marks_candidates.append((_marks_header_score(token) or 90, idx))
            continue
        score = _marks_header_score(token)
        if score > 0 and (
            _MARKS_HEADER_RE.match(token)
            or re.search(r"(?i)marks?|score|percent|obtained|total|max", token)
        ):
            marks_candidates.append((score, idx))
            continue
        if "grade" not in roles and (
            _GRADE_HEADER_RE.match(token) or re.search(r"(?i)^grade\b|letter\s*grade", token)
        ):
            roles["grade"] = idx
    if marks_candidates:
        marks_candidates.sort(key=lambda t: (-t[0], t[1]))
        # Prefer an explicit Total column when Theory/Practical/Total all exist.
        if "total" in roles:
            roles["marks"] = roles["total"]
        else:
            roles["marks"] = marks_candidates[0][1]
    elif "total" in roles:
        roles["marks"] = roles["total"]
    elif "theory" in roles or "practical" in roles:
        # Subject | Theory | Practical (no Total) — marks = last available score.
        roles["marks"] = roles.get("total") or roles.get("practical") or roles.get("theory")  # type: ignore[assignment]
    if "subject" not in roles:
        return None
    if "marks" not in roles and "grade" not in roles and "theory" not in roles and "practical" not in roles:
        return None
    if "marks" not in roles and ("theory" in roles or "practical" in roles):
        roles["marks"] = roles.get("total") or roles.get("practical") or roles["theory"]
    return roles


# Backward-compatible private alias.
_header_column_map = header_column_map


def _name_ok(name: str) -> bool:
    n = _clean(name)
    if not n or len(n) < 2 or len(n) > 200:
        return False
    if _SUBJECT_HEADER_RE.match(n):
        return False
    if re.fullmatch(r"[\d./\-]+", n):
        return False
    if n.lower() in _SUBJECT_NAME_DENY:
        return False
    # Must contain a letter (Latin or local script — Tamil, etc.).
    if not any(ch.isalpha() for ch in n):
        return False
    # Reject OCR fragment tokens like "Gu LG" / "C L" (short Latin crumbs).
    if re.fullmatch(r"(?i)[A-Za-z]{1,2}(?:\s+[A-Za-z]{1,2})+", n):
        return False
    # Require a real word: Unicode letter run OR Latin token length >= 3.
    has_local_script = any(ord(ch) > 127 and ch.isalpha() for ch in n)
    has_latin_word = any(
        len(tok) >= 3 and re.search(r"[A-Za-z]", tok) for tok in n.split()
    )
    if not has_local_script and not has_latin_word:
        return False
    # Reject labeled identity/academic fields mistaken as subjects.
    if re.match(
        r"(?i)^(date\s+of\s+birth|roll\s*(no|number)|registration|candidate|"
        r"student\s*name|father|mother|total|grand\s*total|percentage|cgpa|gpa|"
        r"department|government|examination|certificate|higher\s+secondary|"
        r"marks?\s*obtained|state\s+board|medium\s+of|group\s+code|name\s+of\s+the)\b",
        n,
    ):
        return False
    # Org / address fragments from OCR noise.
    if re.search(
        r"(?i)\b(?:department|examinations?|government|chennai|tamilnadu|"
        r"certificate|board\s+of\s+school|member\s+secretary)\b",
        n,
    ):
        return False
    # Postal / address OCR mistaken as a subject ("C6i , 6m6 -600" + marks 006).
    digit_n = sum(ch.isdigit() for ch in n)
    if digit_n >= 3 and not has_latin_word:
        return False
    if digit_n >= 4 and len(n) <= 28:
        return False
    return True


def _marks_ok(marks: str) -> bool:
    m = _clean(marks)
    if not m or len(m) > 80:
        return False
    if _MARKS_HEADER_RE.match(m):
        return False
    # Require a digit so titles like "HIGHER SECONDARY CERTIFICATE" are rejected.
    if not re.search(r"\d", m):
        return False
    return True


def _marks_looks_like_year(marks: str) -> bool:
    """True for bare 19xx/20xx tokens often mistaken as marks (MAR 2016)."""
    m = _clean(marks)
    return bool(re.fullmatch(r"(?:19|20)\d{2}", m))


def _grade_ok(grade: str) -> bool:
    g = _clean(grade)
    if not g or len(g) > 40:
        return False
    if _GRADE_HEADER_RE.match(g):
        return False
    if g.lower() in {"marks", "score", "obtained", "subject", "certificate"}:
        return False
    if len(g) > 24:
        return False
    # Accept standard letter / word grades only — reject OCR crumbs like "d".
    # Important: do NOT use IGNORECASE on [A-F] (that would allow a–f).
    if re.fullmatch(r"[A-F][+-]?", g):
        return True
    if re.fullmatch(
        r"(?i)pass|fail|distinction|first|second|third|honou?rs?|merit|p",
        g,
    ):
        return True
    return False


def _subject_from_parts(
    name: str,
    marks: str = "",
    grade: str = "",
    *,
    theory: str = "",
    practical: str = "",
    total: str = "",
    words: str = "",
) -> dict[str, str] | None:
    name = _clean(name)
    # Strip trailing separators left by "Tamil - 169" / "Tamil –" splits.
    name = re.sub(r"[\s:\-–—|]+$", "", name).strip()
    # Drop leading "Subject"/"Paper" noise: "Subject Tamil Marks" → keep via later strip.
    name = re.sub(r"(?i)^(subject|paper|course|module)\s+", "", name).strip()
    name = re.sub(r"(?i)\s+(marks?|score|obtained)$", "", name).strip()
    marks = _clean(marks)
    grade = _clean(grade)
    theory = _clean(theory)
    practical = _clean(practical)
    total = _clean(total)
    words = _clean(words)
    if not _name_ok(name):
        return None
    if re.fullmatch(r"(?i)(class|year|form|std|standard|grade|level)", name):
        return None
    # Reject theory/practical/total section banners mistaken as subject names.
    if re.fullmatch(
        r"(?i)(?:theory|thory|practical|pracal|prac\.?|total(?:\s*marks?)?)",
        name,
    ):
        return None
    for key, val in (
        ("theory", theory),
        ("practical", practical),
        ("total", total),
        ("marks", marks),
    ):
        if val and not _marks_ok(val):
            if key == "theory":
                theory = ""
            elif key == "practical":
                practical = ""
            elif key == "total":
                total = ""
            else:
                marks = ""
    # Consolidate: prefer explicit total, else theory+practical sum when both ints,
    # else last available component as marks.
    if total and _marks_ok(total):
        marks = total
    elif not marks:
        if theory and practical:
            try:
                t_n = float(re.split(r"[/\s]", theory)[0])
                p_n = float(re.split(r"[/\s]", practical)[0])
                marks = str(int(t_n + p_n) if t_n == int(t_n) and p_n == int(p_n) else t_n + p_n)
                total = marks
            except ValueError:
                marks = practical or theory
        else:
            marks = practical or theory
    if not total and marks:
        total = marks
    # Month + year false positives (MAR 2016, Qui LGT 2006).
    if marks and _marks_looks_like_year(marks) and len(name) <= 12:
        return None
    if grade and not _grade_ok(grade):
        grade = ""
    if not marks and not grade and not theory and not practical:
        return None
    out: dict[str, str] = {"name": name[:200], "marks": (marks or "")[:80]}
    if grade:
        out["grade"] = grade[:40]
    if theory:
        out["theory"] = theory[:80]
    if practical:
        out["practical"] = practical[:80]
        out["prac"] = practical[:80]  # alias for FE / LLM schema
    if total:
        out["total"] = total[:80]
    if words and _NUMBER_WORDS_RE.match(words):
        out["words"] = words[:120]
    return out


def _row_to_subject(cells: list[str], roles: dict[str, int]) -> dict[str, str] | None:
    si = roles.get("subject")
    if si is None or si >= len(cells):
        return None
    name = _clean(cells[si])
    # If subject cell accidentally includes a leading serial, strip it.
    name = _strip_serial_prefix(name) or name
    theory = ""
    practical = ""
    total = ""
    marks = ""
    grade = ""
    ti = roles.get("theory")
    if ti is not None and ti < len(cells):
        cand = _clean(cells[ti])
        if cand and _marks_ok(cand):
            theory = cand
    pi = roles.get("practical")
    if pi is not None and pi < len(cells):
        cand = _clean(cells[pi])
        if cand and _marks_ok(cand):
            practical = cand
    # Prefer Total → marks role → last numeric (skip Theory/Practical when Total exists).
    for key in ("total", "marks"):
        idx = roles.get(key)
        if idx is not None and idx < len(cells):
            cand = _clean(cells[idx])
            if cand and _marks_ok(cand):
                if key == "total":
                    total = cand
                marks = cand
                break
    gi = roles.get("grade")
    if gi is not None and gi < len(cells):
        grade = _clean(cells[gi])
    if not marks and not grade and not theory and not practical and len(cells) >= 2:
        # Prefer the last numeric cell (Total) over earlier Theory/Practical.
        skip = {si}
        for key in ("theory", "practical"):
            idx = roles.get(key)
            if idx is not None:
                skip.add(idx)
        numeric_cells = [
            _clean(cell)
            for j, cell in enumerate(cells)
            if j not in skip and _marks_ok(_clean(cell))
        ]
        if not numeric_cells:
            numeric_cells = [
                _clean(cell)
                for j, cell in enumerate(cells)
                if j != si and _marks_ok(_clean(cell))
            ]
        if numeric_cells:
            marks = numeric_cells[-1]
            total = marks
    return _subject_from_parts(
        name,
        marks,
        grade,
        theory=theory,
        practical=practical,
        total=total,
    )


def _subject_key(subj: dict[str, str]) -> str:
    """Dedupe key: subject name only (marks/grade variants of the same paper collapse)."""
    return _clean(subj.get("name") or "").lower()


def _prefer_subject_row(
    existing: dict[str, str], incoming: dict[str, str]
) -> dict[str, str]:
    """Keep one row per subject name; prefer stronger marks and a valid grade."""
    out = dict(existing)
    in_marks = _clean(incoming.get("marks") or "")
    ex_marks = _clean(existing.get("marks") or "")
    if in_marks and _marks_ok(in_marks):
        if not ex_marks or not _marks_ok(ex_marks):
            out["marks"] = in_marks[:80]
        elif len(in_marks) >= len(ex_marks):
            # Prefer totals that look like obtained marks (often last / longer token).
            out["marks"] = in_marks[:80]
    in_grade = _clean(incoming.get("grade") or "")
    if in_grade and _grade_ok(in_grade) and not _clean(out.get("grade") or ""):
        out["grade"] = in_grade[:40]
    elif in_grade and _grade_ok(in_grade) and _grade_ok(_clean(out.get("grade") or "")):
        # Prefer Pass / letter over single-char OCR when both present.
        if len(in_grade) >= len(_clean(out.get("grade") or "")):
            out["grade"] = in_grade[:40]
    for col in ("theory", "practical", "total"):
        if col == "practical":
            in_val = _clean(incoming.get("practical") or incoming.get("prac") or "")
        else:
            in_val = _clean(incoming.get(col) or "")
        if in_val and _marks_ok(in_val) and not _clean(out.get(col) or ""):
            out[col] = in_val[:80]
            if col == "practical":
                out["prac"] = in_val[:80]
    in_words = _clean(incoming.get("words") or "")
    if in_words and _NUMBER_WORDS_RE.match(in_words) and not _clean(out.get("words") or ""):
        out["words"] = in_words[:120]
    # Keep marks in sync with total when total is filled later.
    if _clean(out.get("total") or "") and (
        not _clean(out.get("marks") or "")
        or out.get("marks") == existing.get("marks")
    ):
        out["marks"] = _clean(out["total"])[:80]
    return out


def merge_subjects(*batches: list[dict[str, str]], limit: int = 60) -> list[dict[str, str]]:
    """Dedupe subject rows across extract paths (tables, heuristics, OCR).

    Same subject name appears at most once — earlier paths (table / stacked) win
    base marks; later paths only fill missing fields. Prevents TAMIL×2 when one
    row has a junk OCR grade and another does not. Also collapses duplicate
    ``Total Marks`` / Theory-section / Practical-section false subject rows.
    """
    by_name: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for batch in batches:
        for subj in batch or []:
            if not isinstance(subj, dict):
                continue
            name = _clean(subj.get("name") or "")
            if not _name_ok(name):
                continue
            if re.fullmatch(
                r"(?i)(?:theory|thory|practical|pracal|prac\.?|total(?:\s*marks?)?|"
                r"grand\s*total|marks?\s*obtained)",
                name,
            ):
                continue
            normalized: dict[str, str] = {
                "name": name[:200],
                "marks": _clean(subj.get("marks") or "")[:80],
            }
            grade = _clean(subj.get("grade") or "")
            if grade and _grade_ok(grade):
                normalized["grade"] = grade[:40]
            for col in ("theory", "practical", "total"):
                if col == "practical":
                    val = _clean(subj.get("practical") or subj.get("prac") or "")
                else:
                    val = _clean(subj.get(col) or "")
                if val and _marks_ok(val):
                    normalized[col] = val[:80]
                    if col == "practical":
                        normalized["prac"] = val[:80]
            words = _clean(subj.get("words") or "")
            if words and _NUMBER_WORDS_RE.match(words):
                normalized["words"] = words[:120]
            if normalized.get("total") and not normalized["marks"]:
                normalized["marks"] = normalized["total"]
            if (
                not normalized["marks"]
                and not normalized.get("grade")
                and not normalized.get("theory")
                and not normalized.get("practical")
            ):
                continue
            if normalized["marks"] and not _marks_ok(normalized["marks"]):
                if not normalized.get("theory") and not normalized.get("practical"):
                    continue
            key = name.lower()
            if key in by_name:
                by_name[key] = _prefer_subject_row(by_name[key], normalized)
                continue
            by_name[key] = normalized
            order.append(key)
            if len(order) >= limit:
                return [by_name[k] for k in order]
    return [by_name[k] for k in order]


def _align_tokens_to_roles(tokens: list[str], roles: dict[str, int]) -> list[str] | None:
    """Map whitespace tokens onto a known header role layout.

    Never assumes one token per column — subject names are often multi-word
    (\"Social Studies\"), so we peel trailing marks/grade and treat the rest as name.
    """
    if not tokens or "subject" not in roles:
        return None
    max_idx = max(roles.values())
    work = [t for t in tokens if t not in {"|", "/", "·"}]
    # Drop leading serial token when header had an S.No column or token is numeric.
    if work and re.fullmatch(r"\d{1,3}[.)]?", work[0]):
        work = work[1:]
    if len(work) < 2:
        return None

    grade_tok = ""
    if work and _GRADE_TOKEN_RE.match(work[-1]) and not _MARKS_TOKEN_RE.match(work[-1]):
        grade_tok = work[-1]
        work = work[:-1]
    nums: list[str] = []
    while work and _MARKS_TOKEN_RE.match(work[-1]):
        nums.insert(0, work.pop())
    name = _clean(" ".join(work))
    if not _name_ok(name) or not nums:
        return None
    cells = [""] * (max_idx + 1)
    cells[roles["subject"]] = name
    # Map trailing numerics onto theory / practical / total / marks roles.
    role_order = [
        k
        for k in ("theory", "practical", "total", "marks")
        if k in roles and roles[k] is not None
    ]
    # Deduplicate when marks aliases total.
    seen_idx: set[int] = set()
    ordered_idxs: list[tuple[str, int]] = []
    for k in role_order:
        idx = roles[k]
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        ordered_idxs.append((k, idx))
    if ordered_idxs and nums:
        if len(nums) >= len(ordered_idxs):
            for (_k, idx), num in zip(ordered_idxs, nums[-len(ordered_idxs) :]):
                cells[idx] = num
        elif len(nums) == 1:
            mi = roles.get("marks") or roles.get("total") or ordered_idxs[-1][1]
            cells[mi] = nums[-1]
        else:
            # Assign from the right (total last).
            for (_k, idx), num in zip(reversed(ordered_idxs), reversed(nums)):
                cells[idx] = num
    else:
        mi = roles.get("marks") or roles.get("total")
        if mi is not None and nums:
            cells[mi] = nums[-1]
    gi = roles.get("grade")
    if gi is not None and grade_tok:
        cells[gi] = grade_tok
    return cells


def parse_subjects_from_table_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    """Parse subject/marks/grade rows from a 2D table (header + data)."""
    if not rows or len(rows) < 2:
        return []
    header_idx = -1
    roles: dict[str, int] | None = None
    for i, row in enumerate(rows[:8]):
        mapped = header_column_map([_clean(c) for c in row if _clean(str(c))])
        if mapped:
            header_idx = i
            roles = mapped
            break
    if roles is None or header_idx < 0:
        return []
    subjects: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows[header_idx + 1 :]:
        if not row:
            continue
        cells = [_clean(str(c)) for c in row]
        if header_column_map(cells):
            continue
        subj = _row_to_subject(cells, roles)
        if not subj:
            continue
        key = _subject_key(subj)
        if key in seen:
            continue
        seen.add(key)
        subjects.append(subj)
        if len(subjects) >= 60:
            break
    return subjects


def _parse_pipe_subject_row(cleaned: str) -> dict[str, str] | None:
    """Parse ``Name | 85 | A`` or ``Name | 100 | 85`` (max + obtained)."""
    cells = [_clean(c) for c in _PIPE_SPLIT_RE.split(cleaned) if _clean(c)]
    if len(cells) < 2:
        return None
    if header_column_map(cells):
        return None
    name = _strip_serial_prefix(cells[0]) or cells[0]
    grade = ""
    numeric = [c for c in cells[1:] if _MARKS_TOKEN_RE.match(c)]
    for c in cells[1:]:
        if _GRADE_TOKEN_RE.match(c) and not _MARKS_TOKEN_RE.match(c):
            grade = c
            break
    if not numeric:
        return None
    # When Max + Obtained both present, prefer the last numeric cell.
    marks = numeric[-1]
    return _subject_from_parts(name, marks, grade)


def _parse_line_heuristic(line: str) -> dict[str, str] | None:
    """Match SubjectName 85 / SubjectName | 85 | A when no formal header table."""
    cleaned = _clean(line)
    if not cleaned or len(cleaned) > 140:
        return None
    cleaned = _strip_serial_prefix(cleaned)
    if not cleaned:
        return None
    if ":" in cleaned and re.match(
        r"(?i)^(date|roll|reg|name|father|mother|board|school|total|percentage|cgpa|gpa)\b",
        cleaned,
    ):
        return None

    # Pipe rows: do not fall through to whitespace tokenization (\"|\" becomes a token).
    if "|" in cleaned:
        return _parse_pipe_subject_row(cleaned)

    m_dot = _DOT_LEADER_RE.match(cleaned)
    if m_dot:
        return _subject_from_parts(
            m_dot.group("name"),
            m_dot.group("marks") or "",
            m_dot.group("grade") or "",
        )

    m_multi = _MULTI_NUM_TAIL_RE.match(cleaned)
    if m_multi:
        nums = re.findall(r"\d{1,4}(?:\.\d{1,2})?", m_multi.group("nums") or "")
        if nums:
            theory = nums[0] if len(nums) >= 2 else ""
            practical = nums[1] if len(nums) >= 3 else ("" if len(nums) == 2 else "")
            # 2 nums → theory + total (or theory + practical); 3+ → th/pr/total
            if len(nums) == 2:
                return _subject_from_parts(
                    m_multi.group("name"),
                    nums[-1],
                    m_multi.group("grade") or "",
                    theory=nums[0],
                    total=nums[-1],
                )
            if len(nums) >= 3:
                return _subject_from_parts(
                    m_multi.group("name"),
                    nums[-1],
                    m_multi.group("grade") or "",
                    theory=nums[0],
                    practical=nums[1],
                    total=nums[-1],
                )
            return _subject_from_parts(
                m_multi.group("name"),
                nums[-1],
                m_multi.group("grade") or "",
            )

    m = _LINE_SUBJECT_MARKS_RE.match(cleaned)
    if m:
        return _subject_from_parts(
            m.group("name"),
            m.group("marks") or "",
            m.group("grade") or "",
        )

    # Loose multi-space columns without a prior header (name + numeric).
    cells = _split_loose_columns(cleaned)
    if len(cells) >= 2 and _name_ok(_strip_serial_prefix(cells[0]) or cells[0]):
        name = _strip_serial_prefix(cells[0]) or cells[0]
        marks = ""
        grade = ""
        numeric = [tok for tok in cells[1:] if _MARKS_TOKEN_RE.match(tok)]
        for tok in cells[1:]:
            if _GRADE_TOKEN_RE.match(tok) and not grade:
                grade = tok
        if numeric:
            marks = numeric[-1]
        return _subject_from_parts(name, marks, grade)

    # Single-space: "English 72" / "Social Studies 74 A"
    tokens = [t for t in _whitespace_tokens(cleaned) if t not in {"|", "/", "·"}]
    if len(tokens) >= 2:
        grade = ""
        if _GRADE_TOKEN_RE.match(tokens[-1]) and not _MARKS_TOKEN_RE.match(tokens[-1]):
            grade = tokens[-1]
            tokens = tokens[:-1]
        # Peel all trailing numerics; last is marks (Theory/Practical/Total).
        nums: list[str] = []
        while tokens and _MARKS_TOKEN_RE.match(tokens[-1]):
            nums.insert(0, tokens.pop())
        if nums:
            name = _clean(" ".join(tokens))
            return _subject_from_parts(name, nums[-1], grade)
    return None


def _row_cells_for_grouping(line: str) -> list[str]:
    """Best-effort cell split for grouping consecutive marksheet rows."""
    cells = _split_loose_columns(line) or _split_table_cells(line)
    if len(cells) >= 2:
        return cells
    tokens = _whitespace_tokens(line)
    if len(tokens) >= 2 and header_column_map(tokens):
        return tokens
    # Numbered subject row: "1 English 72" / "01 Physics 85 A"
    if len(tokens) >= 3 and re.fullmatch(r"\d{1,3}[.)]?", tokens[0]):
        rest = tokens[1:]
        if (rest and _MARKS_TOKEN_RE.match(rest[-1])) or (
            len(rest) >= 2
            and _GRADE_TOKEN_RE.match(rest[-1])
            and _MARKS_TOKEN_RE.match(rest[-2])
        ):
            return tokens
    # Subject + marks (+ optional grade) with single spaces.
    if len(tokens) >= 2:
        tail = tokens[-1]
        if _MARKS_TOKEN_RE.match(tail) or (
            len(tokens) >= 3
            and _GRADE_TOKEN_RE.match(tail)
            and _MARKS_TOKEN_RE.match(tokens[-2])
        ):
            name = _clean(" ".join(tokens[:-1]))
            if _name_ok(name) or (
                len(tokens) >= 3
                and _GRADE_TOKEN_RE.match(tail)
                and _name_ok(_clean(" ".join(tokens[:-2])))
            ):
                return tokens
    return []


def looks_like_marksheet(text: str | None) -> bool:
    """True when OCR/text likely contains a subject+marks table or block."""
    raw = (text or "").strip()
    if len(raw) < 12:
        return False
    if _MARKSHEET_SIGNAL_RE.search(raw):
        return True
    # Stacked OCR: SUBJECT header then ALLCAPS subject names.
    if re.search(r"(?im)^SUBJECTS?\s*$", raw) and re.search(
        r"(?im)^(?:TAMIL|ENGLISH|PHYSICS|CHEMISTRY|BIOLOGY|MATHEMATICS|MATHS?)\s*$",
        raw,
    ):
        return True
    return False


def is_quality_subject(subj: dict[str, str] | None) -> bool:
    """Heuristic quality gate — filters org/address false positives."""
    if not isinstance(subj, dict):
        return False
    name = _clean(subj.get("name") or "")
    marks = _clean(subj.get("marks") or subj.get("total") or "")
    grade = _clean(subj.get("grade") or "")
    theory = _clean(subj.get("theory") or "")
    practical = _clean(subj.get("practical") or "")
    if not _name_ok(name):
        return False
    if re.fullmatch(r"(?i)(?:theory|thory|practical|prac\.?|total(?:\s*marks?)?)", name):
        return False
    if marks and not _marks_ok(marks):
        return False
    if marks and _marks_looks_like_year(marks) and len(name) <= 12:
        return False
    if not marks and not grade and not theory and not practical:
        return False
    # Real school subjects are rarely 40+ char prose fragments.
    if len(name) > 48:
        return False
    # Reject OCR fragment tokens like "Gu LG" / "C L".
    if re.fullmatch(r"(?i)[A-Za-z]{1,2}(?:\s+[A-Za-z]{1,2})+", name):
        return False
    return True


def quality_subjects(subjects: list[dict[str, str]] | None) -> list[dict[str, str]]:
    return [s for s in (subjects or []) if is_quality_subject(s)]


def parse_stacked_marksheet_subjects(text: str | None) -> list[dict[str, str]]:
    """Parse OCR layouts where subject name and marks sit on consecutive lines.

    Typical Tamil Nadu HSC RapidOCR output::

        SUBJECT
        THORY
        160
        PRAC.
        50
        MARKS OBTAINED FOR 200
        TAMIL
        169
        ONE SIX NINE
        (P)
        ENGLISH
        137
        ...
        PHYSICS
        097
        050
        147
    """
    raw = (text or "").strip()
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 3:
        return []

    start = -1
    for i, line in enumerate(lines):
        if re.fullmatch(r"(?i)subjects?", line) or re.search(
            r"(?i)obtained\s+the\s+following\s+marks", line
        ):
            start = i + 1
            break
        if re.fullmatch(r"(?i)marks?\s*obtained(?:\s*for)?(?:\s+\d{1,4})?", line):
            start = i + 1
            break
    if start < 0:
        # Fallback: first ALLCAPS academic subject name.
        for i, line in enumerate(lines):
            if re.fullmatch(
                r"(?i)(?:tamil|english|physics|chemistry|biology|mathematics|maths?|"
                r"history|geography|commerce|accountancy|economics|computer\s*science)",
                line,
            ):
                start = i
                break
    if start < 0:
        return []

    out: list[dict[str, str]] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if _STACKED_BLOCK_END_RE.search(line):
            break
        # Soft-skip TOTAL MARKS (+ following numeric / number-words) so a
        # misplaced total line does not drop later subjects (Mathematics).
        if _STACKED_TOTAL_LINE_RE.search(line):
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if _STACKED_BLOCK_END_RE.search(nxt) or _STACKED_TOTAL_LINE_RE.search(nxt):
                    break
                if _MARKS_TOKEN_RE.match(nxt) or _NUMBER_WORDS_RE.match(nxt):
                    i += 1
                    continue
                break
            continue
        # Skip column headers / max marks banners.
        if _STACKED_HEADER_SKIP_RE.match(line) or re.fullmatch(
            r"(?i)marks?\s*obtained(?:\s*for)?(?:\s+\d{1,4})?", line
        ):
            i += 1
            continue
        if _MARKS_TOKEN_RE.match(line) or _NUMBER_WORDS_RE.match(line):
            i += 1
            continue
        if _PAREN_GRADE_RE.match(line):
            i += 1
            continue

        name_candidate = _strip_serial_prefix(line) or line
        # Subject names on stacked sheets are short words / titles — reject long prose.
        if len(name_candidate) > 48 or not _name_ok(name_candidate):
            i += 1
            continue
        # Accept Latin or local-script names (Tamil etc.); reject digit-only.
        if not any(ch.isalpha() for ch in name_candidate):
            i += 1
            continue

        nums: list[str] = []
        grade = ""
        words = ""
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if _STACKED_BLOCK_END_RE.search(nxt) or _STACKED_TOTAL_LINE_RE.search(nxt):
                break
            if _NUMBER_WORDS_RE.match(nxt):
                words = _clean(nxt)
                j += 1
                # Optional paren grade after number-words.
                if j < len(lines):
                    gm = _PAREN_GRADE_RE.match(lines[j])
                    if gm:
                        grade = gm.group(1) or gm.group(2) or ""
                        j += 1
                break
            if _MARKS_TOKEN_RE.match(nxt):
                nums.append(_clean(nxt))
                j += 1
                continue
            gm = _PAREN_GRADE_RE.match(nxt)
            if gm and nums:
                grade = gm.group(1) or gm.group(2) or ""
                j += 1
                break
            # Next subject name (or unrelated text) — stop collecting.
            break

        if nums:
            # Theory / Practical / Total → capture columns; prefer last as total.
            theory = nums[0] if len(nums) >= 2 else ""
            practical = nums[1] if len(nums) >= 3 else ""
            total = nums[-1]
            hit = _subject_from_parts(
                name_candidate,
                total,
                grade,
                theory=theory if len(nums) >= 2 else "",
                practical=practical if len(nums) >= 3 else "",
                total=total,
                words=words,
            )
            if hit:
                out.append(hit)
            i = j
            continue
        i += 1

    return merge_subjects(out)


def parse_labeled_subject_mark_pairs(text: str | None) -> list[dict[str, str]]:
    """Parse OCR layouts where subject and marks are labeled on separate lines.

    Examples::
        Subject: Tamil
        Marks: 169

        Subject Tamil    Marks 169
    """
    raw = (text or "").strip()
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    out: list[dict[str, str]] = []
    pending_name: str | None = None

    for line in lines:
        same = _SUBJECT_MARKS_SAME_LINE_RE.search(line)
        if same:
            hit = _subject_from_parts(same.group("name"), same.group("marks") or "")
            if hit:
                out.append(hit)
            pending_name = None
            continue

        subj_m = _SUBJECT_LABEL_LINE_RE.match(line)
        if subj_m:
            rest = _clean(subj_m.group(1))
            # "Subject: Tamil 169" or "Subject Tamil Marks 169"
            inline = _parse_line_heuristic(rest)
            if inline:
                out.append(inline)
                pending_name = None
                continue
            # Rest may still include a trailing marks token after a dash.
            inline2 = _parse_line_heuristic(
                re.sub(r"(?i)\bmarks?\b|\bscore\b", " ", rest)
            )
            if inline2:
                out.append(inline2)
                pending_name = None
                continue
            if _name_ok(rest) or _name_ok(
                re.sub(r"(?i)^(subject|paper)\s+", "", rest)
            ):
                pending_name = rest
            continue

        marks_m = _MARKS_LABEL_LINE_RE.match(line)
        if marks_m and pending_name:
            hit = _subject_from_parts(pending_name, marks_m.group(1))
            if hit:
                out.append(hit)
            pending_name = None
            continue

        # Alternate: bare subject name line then bare score line.
        if pending_name and _MARKS_TOKEN_RE.match(_clean(line)):
            hit = _subject_from_parts(pending_name, _clean(line))
            if hit:
                out.append(hit)
            pending_name = None
            continue

        if marks_m:
            # Marks without a pending subject — ignore.
            pending_name = None
            continue

    return merge_subjects(out)


def parse_subjects_from_text(text: str | None) -> list[dict[str, str]]:
    """Detect marksheet-style tables and loose subject/marks lines in free text."""
    raw = (text or "").strip()
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return []
    if len(lines) == 1:
        hit = _parse_line_heuristic(lines[0])
        labeled = parse_labeled_subject_mark_pairs(raw)
        return merge_subjects([hit] if hit else [], labeled)

    groups: list[list[list[str]]] = []
    current: list[list[str]] = []
    active_roles: dict[str, int] | None = None
    for line in lines:
        cells = _row_cells_for_grouping(line)
        if len(cells) >= 2:
            mapped = header_column_map(cells)
            if mapped:
                active_roles = mapped
                current.append(cells)
                continue
            if active_roles:
                aligned = _align_tokens_to_roles(_whitespace_tokens(line), active_roles)
                if aligned:
                    current.append(aligned)
                    continue
            current.append(cells)
            continue
        if current:
            groups.append(current)
            current = []
            active_roles = None
    if current:
        groups.append(current)

    table_subjects: list[dict[str, str]] = []
    for group in groups:
        table_subjects.extend(parse_subjects_from_table_rows(group))

    # Always run line heuristics and merge — catch rows tables missed.
    heuristic: list[dict[str, str]] = []
    in_block = False
    for line in lines:
        lower = line.lower()
        row_cells = _row_cells_for_grouping(line)
        if re.search(r"(?i)\bsubjects?\b.*\b(marks?|score|grade)\b", lower) or (
            row_cells and header_column_map(row_cells)
        ):
            in_block = True
            continue
        if re.match(
            r"(?i)^(total|grand\s*total|aggregate|percentage|result|remarks)\b", lower
        ):
            in_block = False
            continue
        # Skip pure label lines handled by labeled-pair pass.
        if _SUBJECT_LABEL_LINE_RE.match(line) or _MARKS_LABEL_LINE_RE.match(line):
            continue
        hit = _parse_line_heuristic(line)
        if hit:
            if in_block or _name_ok(hit.get("name") or ""):
                heuristic.append(hit)

    labeled = parse_labeled_subject_mark_pairs(raw)
    stacked = parse_stacked_marksheet_subjects(raw)
    return merge_subjects(table_subjects, heuristic, labeled, stacked)


def resolve_subjects_from_text(
    text: str | None,
    *,
    use_llm: bool = True,
    prior_subjects: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Heuristic parse, optionally merged with Ollama LLM structured extract.

    LLM runs when the text looks like a marksheet and quality heuristic rows
    are below ``SCANX_LLM_SUBJECTS_MIN_HEURISTIC`` (default 2). Always merges
    prior + heuristic + LLM results.
    """
    from app.config import settings

    heuristic = parse_subjects_from_text(text)
    quality = quality_subjects(heuristic)
    # On marksheet OCR, drop low-quality false positives (address/year noise).
    if quality:
        base = quality
    elif looks_like_marksheet(text):
        base = []
    else:
        base = heuristic

    llm_rows: list[dict[str, str]] = []
    min_needed = int(getattr(settings, "SCANX_LLM_SUBJECTS_MIN_HEURISTIC", 2) or 2)
    if use_llm and looks_like_marksheet(text) and len(quality) < min_needed:
        try:
            from app.services.scanx_llm_subjects import extract_subjects_via_llm

            llm_rows = extract_subjects_via_llm(text)
        except Exception:
            llm_rows = []
    return merge_subjects(prior_subjects or [], base, llm_rows)


def format_subject_item(subj: dict[str, str]) -> dict[str, str]:
    """Academic category list item: ``Subject`` → ``Name — Marks X · Grade Y``."""
    name = _clean(subj.get("name") or "")
    marks = _clean(subj.get("marks") or subj.get("total") or "")
    grade = _clean(subj.get("grade") or "")
    theory = _clean(subj.get("theory") or "")
    practical = _clean(subj.get("practical") or "")
    parts: list[str] = []
    if theory:
        parts.append(f"Theory {theory}")
    if practical:
        parts.append(f"Practical {practical}")
    if marks:
        parts.append(f"Total {marks}" if (theory or practical) else f"Marks {marks}")
    if grade:
        parts.append(f"Grade {grade}")
    if name and parts:
        value = f"{name} — " + " · ".join(parts)
    elif name:
        value = name
    else:
        value = " · ".join(parts) if parts else ""
    return {"label": "Subject", "value": value[:500]}


def subjects_payload(subjects: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Normalize for JSON storage / API."""
    return merge_subjects(subjects)


def subjects_missing_or_empty(fields: dict[str, Any] | None) -> bool:
    """True when structured subjects are absent or lack usable name+marks rows."""
    if not isinstance(fields, dict):
        return True
    subjects = fields.get("subjects")
    if isinstance(subjects, list):
        quality = quality_subjects(
            [s for s in subjects if isinstance(s, dict)]  # type: ignore[list-item]
        )
        if quality:
            return False
    marks = fields.get("marks")
    if isinstance(marks, list) and quality_subjects(
        [marks_row_to_subject(m) for m in marks if isinstance(m, dict)]
    ):
        return False
    # Academic "Subject" items with embedded marks still count as present.
    for cat in fields.get("categories") or []:
        if not isinstance(cat, dict) or cat.get("id") != "academic":
            continue
        for item in cat.get("items") or []:
            if not isinstance(item, dict):
                continue
            if (item.get("label") or "").strip().lower() != "subject":
                continue
            value = _clean(item.get("value") or "")
            if re.search(r"(?i)\bmarks?\b|\d{1,3}", value) and "—" in value:
                # Reject known garbage patterns from older parsers.
                if re.search(
                    r"(?i)department|examinations?|marks?\s*obtained\s+for|chennai",
                    value,
                ):
                    continue
                return False
    return True


def subject_to_marks_row(subj: dict[str, Any] | None) -> dict[str, str] | None:
    """Map internal subject dict → review ``marks`` schema row.

    Schema::
        {subject, theory, prac, total, words?}
    """
    if not isinstance(subj, dict):
        return None
    name = _clean(subj.get("name") or subj.get("subject") or "")
    if not name or not _name_ok(name):
        return None
    if re.fullmatch(
        r"(?i)(?:theory|thory|practical|pracal|prac\.?|total(?:\s*marks?)?)",
        name,
    ):
        return None
    theory = _clean(subj.get("theory") or "")
    prac = _clean(subj.get("prac") or subj.get("practical") or "")
    total = _clean(subj.get("total") or subj.get("marks") or "")
    words = _clean(subj.get("words") or "")
    if theory and not _marks_ok(theory):
        theory = ""
    if prac and not _marks_ok(prac):
        prac = ""
    if total and not _marks_ok(total):
        total = ""
    if not theory and not prac and not total and not _clean(subj.get("grade") or ""):
        return None
    row: dict[str, str] = {"subject": name[:200]}
    if theory:
        row["theory"] = theory[:80]
    if prac:
        row["prac"] = prac[:80]
    if total:
        row["total"] = total[:80]
    if words and _NUMBER_WORDS_RE.match(words):
        row["words"] = words[:120]
    grade = _clean(subj.get("grade") or "")
    if grade and _grade_ok(grade):
        row["grade"] = grade[:40]
    # Confidence flags when present (from OCR block mapping).
    if subj.get("is_low_confidence") is True:
        row["is_low_confidence"] = "true"
    conf = subj.get("confidence")
    if conf is not None:
        try:
            row["confidence"] = str(round(float(conf), 4))
        except (TypeError, ValueError):
            pass
    return row


def marks_row_to_subject(row: dict[str, Any] | None) -> dict[str, str]:
    """Inverse of ``subject_to_marks_row`` for merge / quality helpers."""
    if not isinstance(row, dict):
        return {}
    name = _clean(row.get("subject") or row.get("name") or "")
    theory = _clean(row.get("theory") or "")
    prac = _clean(row.get("prac") or row.get("practical") or "")
    total = _clean(row.get("total") or row.get("marks") or "")
    words = _clean(row.get("words") or "")
    grade = _clean(row.get("grade") or "")
    out: dict[str, str] = {"name": name}
    if theory:
        out["theory"] = theory
    if prac:
        out["practical"] = prac
        out["prac"] = prac
    if total:
        out["total"] = total
        out["marks"] = total
    if words:
        out["words"] = words
    if grade:
        out["grade"] = grade
    if str(row.get("is_low_confidence") or "").lower() in {"1", "true", "yes"}:
        out["is_low_confidence"] = "true"
    conf = row.get("confidence")
    if conf is not None and str(conf).strip():
        out["confidence"] = str(conf).strip()
    return out


def subjects_to_marks(subjects: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Build counsellor Dynamic Table ``marks`` array from subject rows."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for subj in subjects or []:
        row = subject_to_marks_row(subj)
        if not row:
            continue
        key = row["subject"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= 60:
            break
    return out


def attach_marks_schema(
    fields: dict[str, Any] | None,
    subjects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ensure ``extracted_fields`` carries both ``subjects`` and ``marks`` arrays."""
    base: dict[str, Any] = dict(fields) if isinstance(fields, dict) else {"version": 1}
    rows = list(subjects or [])
    if not rows and isinstance(base.get("subjects"), list):
        rows = [s for s in base["subjects"] if isinstance(s, dict)]
    if not rows and isinstance(base.get("marks"), list):
        rows = [
            marks_row_to_subject(m)
            for m in base["marks"]
            if isinstance(m, dict)
        ]
    merged = merge_subjects(rows)
    base["subjects"] = merged
    base["marks"] = subjects_to_marks(merged)
    return base


def annotate_subjects_with_ocr_confidence(
    subjects: list[dict[str, Any]] | None,
    blocks: list[Any] | None,
    *,
    threshold: float = 0.80,
) -> list[dict[str, str]]:
    """Flag subject rows whose name/scores overlap low-confidence OCR blocks."""
    rows = merge_subjects(
        [s for s in (subjects or []) if isinstance(s, dict)]  # type: ignore[list-item]
    )
    if not rows or not blocks:
        return rows
    low_texts: list[tuple[str, float]] = []
    for blk in blocks:
        try:
            conf = float(getattr(blk, "confidence", 1.0))
            text = str(getattr(blk, "text", "") or "").strip().lower()
            is_low = bool(getattr(blk, "is_low_confidence", conf < threshold))
        except Exception:
            continue
        if not text:
            continue
        if is_low or conf < threshold:
            low_texts.append((text, conf))
    if not low_texts:
        return rows
    out: list[dict[str, str]] = []
    for subj in rows:
        row = dict(subj)
        name = _clean(row.get("name") or "").lower()
        tokens = {
            _clean(row.get(k) or "").lower()
            for k in ("theory", "practical", "prac", "total", "marks")
            if _clean(row.get(k) or "")
        }
        tokens.discard("")
        matched_conf: list[float] = []
        for text, conf in low_texts:
            if name and (name in text or text in name):
                matched_conf.append(conf)
                continue
            if any(tok and tok == text for tok in tokens):
                matched_conf.append(conf)
        if matched_conf:
            row["is_low_confidence"] = "true"
            row["confidence"] = str(round(min(matched_conf), 4))
        out.append(row)
    return out
