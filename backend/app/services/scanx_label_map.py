"""Universal ScanX OCR label matching, ROI fallback, and non-destructive keeps.

Shared by passport + document field extractors so every mapped field uses the
same rules: fuzzy label anchors (rapidfuzz), coordinate ROI when labels are
garbled, and value-shape gates that never wipe a valid captured entity solely
because its label failed to match.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from rapidfuzz import fuzz

# Fuzzy label threshold (0-100). Short labels need a higher bar so
# "Spouse" does not match "Father" and "Pita No." does not match "File No.".
# Longer multi-word anchors (e.g. "Name of Spouse") use the base threshold.
LABEL_FUZZY_THRESHOLD = 82
LABEL_FUZZY_THRESHOLD_SHORT = 88  # for canonical aliases shorter than 10 chars

# Confusable pairs: never accept a fuzzy hit across these token groups.
_LABEL_CONFUSABLES: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (frozenset({"spouse", "spouce", "sp0use"}), frozenset({"father", "foter", "fother", "guardian"})),
    (frozenset({"spouse", "spouce", "sp0use"}), frozenset({"mother", "mather", "mothor"})),
    (frozenset({"father", "foter", "fother", "guardian"}), frozenset({"mother", "mather", "mothor"})),
    (frozenset({"file", "fileno", "fke", "fle"}), frozenset({"pita", "pilta", "pila", "father", "foter"})),
    (frozenset({"passport", "document"}), frozenset({"pita", "pilta", "pila"})),
    (frozenset({"birth"}), frozenset({"issue", "lssue", "issu", "expiry", "expir"})),
)

# Family-role fields need a distinctive OCR token. Bare "of"/"name" overlap must
# not let cover-note lines ("BY ORDER OF", "Place of Birth") anchor Father.
_FIELD_LABEL_SIGNAL_TOKENS: dict[str, frozenset[str]] = {
    "father_name": frozenset(
        {"father", "foter", "fother", "guardian", "guardlan", "curdian", "lepai"}
    ),
    "mother_name": frozenset({"mother", "mather", "mothor", "maches"}),
    "spouse_name": frozenset({"spouse", "spouce", "sp0use"}),
}

# Cover-page note / officer lines — never treat as field labels.
_PASSPORT_NOTE_LABEL_RE = re.compile(
    r"(?i)\b(?:by\s+order|president|request\s+and\s+require|stand\s+in\s+need|"
    r"whom\s+it\s+may\s+concern|bearer\s+to\s+pass|let\s+or\s+hindrance|"
    r"every\s+assistance|republic\s+of\s+india)\b"
)

# Canonical label phrases per passport schema key (exact + fuzzy targets).
PASSPORT_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "surname": ("surname", "family name", "last name", "nom"),
    "given_names": ("given names", "given name", "given name(s)", "first name", "prenom", "prenoms"),
    "date_of_birth": ("date of birth", "dob", "birth date", "date ofbirth"),
    "sex": ("sex", "gender", "sexe"),
    "nationality": ("nationality", "citizenship", "nationalite"),
    "place_of_birth": ("place of birth", "birth place"),
    "document_number": ("passport number", "passport no", "passport no.", "document number"),
    "document_type": ("document type", "type"),
    "country_code": ("country code", "code"),
    "place_of_issue": ("place of issue", "place of lssue", "place of issuc"),
    "date_of_issue": ("date of issue", "date of lssue", "date of issuc", "issue date"),
    "date_of_expiry": ("date of expiry", "date of expiration", "expiry date", "expiry"),
    "father_name": (
        "name of father",
        "father name",
        "father's name",
        "name of father / legal guardian",
        "father / legal guardian",
        "legal guardian",
        "name of guardian",
    ),
    "mother_name": ("name of mother", "mother name", "mother's name"),
    "spouse_name": (
        "name of spouse",
        "spouse name",
        "spouse's name",
        "name of spouce",
        "spouse",
    ),
    "address": ("address", "residential address", "denl / address", "qa / address"),
    "file_number": (
        "file number",
        "file no",
        "file no.",
        "fileno",
        "a3 / f no",
        "a3/f no",
        "fke no",
        "fle no",
    ),
}

# Relative Y bands (0-1 of page height) for Indian passport layouts when the
# printed label is missing/garbled. Bio ~= page-1; address ~= page-2 family page.
# Values are only accepted when an OCR block sits in-band and passes shape checks.
FIELD_ROI_Y: dict[str, tuple[float, float]] = {
    "surname": (0.08, 0.28),
    "given_names": (0.18, 0.38),
    "nationality": (0.28, 0.48),
    "date_of_birth": (0.28, 0.52),
    "place_of_birth": (0.40, 0.62),
    "place_of_issue": (0.48, 0.70),
    "date_of_issue": (0.55, 0.78),
    "date_of_expiry": (0.55, 0.82),
    "document_number": (0.12, 0.40),
    "father_name": (0.05, 0.42),
    "mother_name": (0.15, 0.55),
    "spouse_name": (0.25, 0.65),
    "address": (0.40, 0.92),
    "file_number": (0.65, 1.0),
}

_DIGIT_LOOKALIKES = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b"})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


def normalize_label_text(text: str | None) -> str:
    """Lowercase, collapse space, map common OCR digit-to-letter lookalikes."""
    raw = _WS.sub(" ", (text or "").strip().lower())
    raw = raw.replace("_", " ").rstrip(".:/-")
    if not raw:
        return ""
    return raw.translate(_DIGIT_LOOKALIKES)


def _token_set(text: str) -> frozenset[str]:
    return frozenset(t for t in _NON_ALNUM.split(normalize_label_text(text)) if t)


def _confusable_collision(a: str, b: str) -> bool:
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return False
    for left, right in _LABEL_CONFUSABLES:
        if (ta & left and tb & right) or (ta & right and tb & left):
            return True
    return False


def _threshold_for(alias: str) -> int:
    # Documented: short labels use 88; multi-word anchors use 82.
    return LABEL_FUZZY_THRESHOLD_SHORT if len(alias) < 10 else LABEL_FUZZY_THRESHOLD


def fuzzy_label_score(ocr_text: str | None, canonical: str) -> float:
    """rapidfuzz similarity after OCR digit lookalike normalization."""
    a = normalize_label_text(ocr_text)
    b = normalize_label_text(canonical)
    if not a or not b:
        return 0.0
    if _confusable_collision(a, b):
        return 0.0
    return float(max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)))


def best_fuzzy_alias(
    ocr_text: str | None,
    aliases: tuple[str, ...] | list[str],
    *,
    threshold: int | None = None,
) -> tuple[str, float] | None:
    """Return (best_alias, score) when score meets the per-alias threshold."""
    best: tuple[str, float] | None = None
    for alias in aliases:
        need = threshold if threshold is not None else _threshold_for(alias)
        score = fuzzy_label_score(ocr_text, alias)
        if score < need:
            continue
        if best is None or score > best[1]:
            best = (alias, score)
    return best


def match_passport_field_label(ocr_text: str | None) -> str | None:
    """Map OCR label text to passport schema key via exact then fuzzy match."""
    raw = normalize_label_text(ocr_text)
    if not raw:
        return None
    # Hard reject: "Pita No." must not map to File No. or Passport No.
    if re.fullmatch(r"pita\s*no\.?", raw) or re.fullmatch(r"pil?ta\s*no\.?", raw):
        return None
    if _PASSPORT_NOTE_LABEL_RE.search(raw):
        return None

    alnum_len = len(re.sub(r"[^a-z0-9]", "", raw))

    for key, aliases in PASSPORT_FIELD_LABELS.items():
        for alias in aliases:
            a = normalize_label_text(alias)
            if raw == a or raw.rstrip(".") == a.rstrip("."):
                return key
            if len(a) >= 8 and (raw.startswith(a) or a in raw):
                if _confusable_collision(raw, a):
                    continue
                if key in _FIELD_LABEL_SIGNAL_TOKENS and not _ocr_has_field_label_signal(
                    raw, key
                ):
                    continue
                return key

    # Tiny OCR crumbs ("IA/", "5") must not fuzzy-match "legal guardian".
    if alnum_len < 4:
        return None

    scored: list[tuple[str, float]] = []
    for key, aliases in PASSPORT_FIELD_LABELS.items():
        if key in _FIELD_LABEL_SIGNAL_TOKENS and not _ocr_has_field_label_signal(
            raw, key
        ):
            continue
        hit = best_fuzzy_alias(raw, aliases)
        if hit:
            scored.append((key, hit[1]))
    if not scored:
        return None
    scored.sort(key=lambda t: t[1], reverse=True)
    top_key, top_score = scored[0]
    if len(scored) > 1 and scored[1][1] >= top_score - 3:
        if {scored[0][0], scored[1][0]} & {
            "spouse_name",
            "father_name",
            "mother_name",
            "file_number",
        }:
            return None
    return top_key


def _ocr_has_field_label_signal(text: str | None, field_key: str) -> bool:
    """True when OCR carries a distinctive token for family-role fields."""
    signals = _FIELD_LABEL_SIGNAL_TOKENS.get(field_key)
    if not signals:
        return True
    raw = normalize_label_text(text)
    if not raw or _PASSPORT_NOTE_LABEL_RE.search(raw):
        return False
    tokens = _token_set(raw)
    if tokens & signals:
        return True
    # Mild OCR garble: allow compact substring for signals len >= 4.
    return any(sig in raw for sig in signals if len(sig) >= 4)


def block_is_field_label(text: str | None, field_key: str) -> bool:
    """True when this OCR block is an anchor label for field_key."""
    aliases = PASSPORT_FIELD_LABELS.get(field_key)
    if not aliases:
        return False
    raw = normalize_label_text(text)
    if not raw:
        return False
    # "Pita No." is OCR noise near dates -- never File No. or Passport No.
    if field_key in {"file_number", "document_number"} and re.search(
        r"\bpita\b|\bpil?ta\b", raw
    ):
        return False
    if _PASSPORT_NOTE_LABEL_RE.search(raw):
        return False
    matched = match_passport_field_label(raw)
    if matched is not None:
        # Never let Place/Date of Birth also count as Father via loose fuzzy.
        return matched == field_key
    if not _ocr_has_field_label_signal(raw, field_key):
        return False
    return best_fuzzy_alias(raw, aliases) is not None


def find_label_anchor_index(
    items: list[tuple[float, float, float, float, float, str]],
    field_key: str,
) -> int | None:
    """Index of the best OCR box matching field_key label (fuzzy)."""
    best_i: int | None = None
    best_score = -1.0
    aliases = PASSPORT_FIELD_LABELS.get(field_key) or ()
    for i, (_page, _cy, _cx, _w, _h, text) in enumerate(items):
        if field_key == "file_number" and re.search(
            r"(?i)\bpita\b|\bpil?ta\b", text or ""
        ):
            continue
        if not block_is_field_label(text, field_key):
            continue
        hit = (
            best_fuzzy_alias(text, aliases)
            if _ocr_has_field_label_signal(text, field_key)
            else None
        )
        score = hit[1] if hit else float(LABEL_FUZZY_THRESHOLD)
        if score > best_score:
            best_score = score
            best_i = i
    return best_i


def page_extents(
    items: list[tuple[float, float, float, float, float, str]],
    page: float,
) -> tuple[float, float] | None:
    ys = [cy for p, cy, *_rest in items if p == page]
    if not ys:
        return None
    return min(ys), max(ys)


def values_in_field_roi(
    items: list[tuple[float, float, float, float, float, str]],
    field_key: str,
    *,
    is_value: Callable[[str], bool],
    page: float | None = None,
) -> list[str]:
    """OCR texts in the template band for field_key that pass is_value."""
    band = FIELD_ROI_Y.get(field_key)
    if not band or not items:
        return []
    y0_f, y1_f = band
    pages = {page} if page is not None else {p for p, *_ in items}
    out: list[str] = []
    seen: set[str] = set()
    for pg in sorted(pages):
        ext = page_extents(items, pg)
        if not ext:
            continue
        ymin, ymax = ext
        span = max(ymax - ymin, 1.0)
        lo = ymin + y0_f * span
        hi = ymin + y1_f * span
        for p, cy, _cx, _w, _h, text in items:
            if p != pg or cy < lo or cy > hi:
                continue
            if block_is_field_label(text, field_key):
                continue
            other = match_passport_field_label(text)
            if other and other != field_key and len(normalize_label_text(text).split()) <= 6:
                continue
            if not is_value(text):
                continue
            key = re.sub(r"\s+", " ", text.strip()).upper()
            if key in seen:
                continue
            seen.add(key)
            out.append(text.strip())
    return out


def retain_if_valid_value(
    field_key: str,
    value: Any,
    *,
    shape_ok: Callable[[str], bool],
) -> str | None:
    """Keep value iff shape_ok. Label failure never clears a valid value."""
    s = str(value or "").strip()
    if not s:
        return None
    if not shape_ok(s):
        return None
    return s
