"""Passport OCR extraction: MRZ (TD3) + visual-zone labeled fields.

Produces the counsellor-facing passport schema persisted on
``extracted_document_data`` / ``extracted_fields_json.passport``.

Supports Indian multi-page scans (Page 1 biodata + Page 2 family/address).
"""

from __future__ import annotations

import logging
import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from app.services.scanx_ocr_blocks import OCR_CONFIDENCE_THRESHOLD
from app.services.scanx_dates import (
    apply_scanx_date_format_to_fields,
    format_scanx_date,
    normalize_scanx_date,
)
from app.services.scanx_label_map import (
    LABEL_FUZZY_THRESHOLD,
    LABEL_FUZZY_THRESHOLD_SHORT,
    block_is_field_label,
    find_label_anchor_index,
    match_passport_field_label,
    retain_if_valid_value,
    values_in_field_roi,
)

# Documented fuzzy thresholds (multi-word=82, short labels=88) — see scanx_label_map.
_LABEL_FUZZY_THRESHOLDS = (LABEL_FUZZY_THRESHOLD, LABEL_FUZZY_THRESHOLD_SHORT)

logger = logging.getLogger(__name__)

PASSPORT_FIELD_KEYS: tuple[str, ...] = (
    # Page 1 — personal
    "surname",
    "given_names",
    "date_of_birth",
    "sex",
    "nationality",
    "place_of_birth",
    # Page 1 — document
    "document_number",
    "document_type",
    "country_code",
    "place_of_issue",
    "date_of_issue",
    "date_of_expiry",
    # Page 1 — MRZ
    "mrz_string",
    # Page 2
    "father_name",
    "mother_name",
    "spouse_name",
    "address",
    "file_number",
)

# Counsellor-facing groups (anything else → Other Details).
PASSPORT_GROUP_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "personal_info",
        "Personal Info",
        (
            "surname",
            "given_names",
            "date_of_birth",
            "sex",
            "nationality",
            "country_code",
            "place_of_birth",
            "father_name",
            "mother_name",
            "spouse_name",
        ),
    ),
    (
        "document_details",
        "Document Details",
        (
            "document_number",
            "document_type",
            "place_of_issue",
            "date_of_issue",
            "date_of_expiry",
            "file_number",
            "address",
        ),
    ),
    (
        "mrz_data",
        "MRZ Data",
        ("mrz_string",),
    ),
    (
        "audit_ui",
        "Audit & UI",
        ("bounding_boxes", "confidence_scores", "is_low_confidence"),
    ),
)

_PASSPORT_FIELD_LABELS: dict[str, str] = {
    "surname": "Surname",
    "given_names": "Given names",
    "date_of_birth": "Date of birth",
    "sex": "Sex",
    "nationality": "Nationality",
    "place_of_birth": "Place of birth",
    "document_number": "Passport number",
    "document_type": "Document type",
    "country_code": "Country code",
    "place_of_issue": "Place of issue",
    "date_of_issue": "Date of issue",
    "date_of_expiry": "Date of expiry",
    "mrz_string": "MRZ string",
    "father_name": "Father / guardian name",
    "mother_name": "Mother name",
    "spouse_name": "Spouse name",
    "address": "Address",
    "file_number": "File number",
    "bounding_boxes": "Bounding boxes",
    "confidence_scores": "Confidence scores",
    "is_low_confidence": "Is low confidence",
}

_PASSPORT_KNOWN_LABELS: frozenset[str] = frozenset(
    lab.lower() for lab in _PASSPORT_FIELD_LABELS.values()
) | frozenset(
    {
        "passport number",
        "mrz",
        "dob",
        "gender",
        "expiry",
        "expiration",
        "issue date",
        "expiry date",
        "name of father",
        "name of mother",
        "name of spouse",
        "spouse name",
        "legal guardian",
    }
)

# Flat OCR / category labels → canonical passport keys (UI binding).
_PASSPORT_LABEL_ALIASES: dict[str, str] = {
    "surname": "surname",
    "family name": "surname",
    "last name": "surname",
    "given names": "given_names",
    "given name": "given_names",
    "given name(s)": "given_names",
    "first name": "given_names",
    "first names": "given_names",
    "forenames": "given_names",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "sex": "sex",
    "gender": "sex",
    "nationality": "nationality",
    "citizenship": "nationality",
    "place of birth": "place_of_birth",
    "birth place": "place_of_birth",
    "document number": "document_number",
    "passport number": "document_number",
    "passport no": "document_number",
    "passport no.": "document_number",
    "document type": "document_type",
    "country code": "country_code",
    "country_code": "country_code",
    "place of issue": "place_of_issue",
    "date of issue": "date_of_issue",
    "date of lssue": "date_of_issue",
    "date of issuc": "date_of_issue",
    "issue date": "date_of_issue",
    "date of expiry": "date_of_expiry",
    "expiry date": "date_of_expiry",
    "expiry": "date_of_expiry",
    "mrz string": "mrz_string",
    "mrz": "mrz_string",
    "father / guardian name": "father_name",
    "father name": "father_name",
    "father's name": "father_name",
    "name of father": "father_name",
    "name of guardian": "father_name",
    "legal guardian": "father_name",
    "mother name": "mother_name",
    "mother's name": "mother_name",
    "name of mother": "mother_name",
    "spouse name": "spouse_name",
    "spouse's name": "spouse_name",
    "name of spouse": "spouse_name",
    "name of spouse /": "spouse_name",
    "address": "address",
    "residential address": "address",
    "file number": "file_number",
    "file no": "file_number",
    "file no.": "file_number",
    "fileno": "file_number",
    "a3 / f no": "file_number",
    "a3/f no": "file_number",
    "name of father / legal guardian": "father_name",
    "name of father/legal guardian": "father_name",
    "father / legal guardian": "father_name",
}


def _canonical_key_from_ocr_label(lab: str) -> str | None:
    """Map a printed / OCR field label to a passport schema key.

    Matching is canonical + rapidfuzz (see ``scanx_label_map``, thresholds
    ``LABEL_FUZZY_THRESHOLD`` / ``LABEL_FUZZY_THRESHOLD_SHORT``) — not the
    counsellor UI string (e.g. UI \"Father / guardian name\" ↔ key
    ``father_name`` ↔ OCR \"Name of Father / Legal Guardian\").
    """
    raw = re.sub(r"\s+", " ", (lab or "").strip().lower())
    raw = raw.replace("_", " ").rstrip(".:/")
    if not raw:
        return None
    hit = _PASSPORT_LABEL_ALIASES.get(raw)
    if hit:
        return hit
    # Shared fuzzy / exact map (Sp0use, Name of Spouce, Foter, …).
    fuzzy_hit = match_passport_field_label(lab)
    if fuzzy_hit:
        return fuzzy_hit
    # Containment / Indian bilingual passport page-2 labels.
    if re.search(r"\b(father|foter|fother|guardian|curdian)\b", raw) and not re.search(
        r"\b(mother|mather|spouse|spouce)\b", raw
    ):
        return "father_name"
    if re.search(r"\b(mother|mather|mothor|maches)\b", raw):
        return "mother_name"
    if re.search(r"\b(spouse|spouce|sp0use)\b", raw):
        return "spouse_name"
    if re.search(
        r"\b(file\s*(no\.?|number|#)|fileno|a3\s*/\s*f|fke\s*no|f\.?\s*no\.?)\b",
        raw,
    ) and not re.search(r"\bpita\b|\bpil?ta\b", raw):
        return "file_number"
    if re.search(r"\baddress\b", raw) and "email" not in raw:
        return "address"
    return None


def hydrate_passport_from_label_items(
    passport: dict[str, Any],
    items: list[dict[str, str]] | None,
) -> dict[str, Any]:
    """Fill blank passport schema keys from Field|Value rows (label aliases)."""
    out = dict(passport) if isinstance(passport, dict) else {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        lab = re.sub(r"\s+", " ", str(item.get("label") or "").strip().lower())
        lab = lab.replace("_", " ").rstrip(".:")
        val = str(item.get("value") or "").strip()
        if not lab or not val:
            continue
        key = _canonical_key_from_ocr_label(lab)
        if not key:
            continue
        existing = out.get(key)
        if existing is not None and str(existing).strip():
            # Allow correcting junk nationality from Field|Value rows.
            if not (key == "nationality" and not is_plausible_nationality(str(existing))):
                continue
        if key == "address":
            out[key] = normalize_multiline_address(val)
        elif key == "nationality":
            demonym, nat_code = resolve_nationality(val)
            if not demonym:
                continue
            out[key] = demonym
            if nat_code and not (out.get("country_code") and str(out["country_code"]).strip()):
                out["country_code"] = nat_code
        elif key in {"father_name", "mother_name", "spouse_name"}:
            cleaned = _clean_person_name(val)
            if cleaned and _is_plausible_person_name(cleaned):
                out[key] = cleaned
        elif key == "file_number":
            if _is_garbage_file_number(val):
                continue
            tok = re.sub(r"\s+", "", val).upper()
            if _looks_like_file_number_token(tok):
                out[key] = tok
                continue
            compact = re.sub(r"[\s\-/]+", "", val).upper()
            m = re.search(r"([A-Z]{1,5}\d{6,14}[A-Z0-9]{0,4})", compact)
            if (
                m
                and not _PASSPORT_NO_SHAPE_RE.match(m.group(1))
                and _looks_like_file_number_token(m.group(1))
            ):
                out[key] = m.group(1)
        else:
            out[key] = val
    if out.get("address"):
        out["address"] = normalize_multiline_address(str(out["address"]))
    # Final nationality gate for anything already on the payload.
    if out.get("nationality") and not is_plausible_nationality(str(out["nationality"])):
        out["nationality"] = demonym_for_country_code(
            str(out.get("country_code") or "")
        )
    return _post_validate_passport_fields(out)


# Values that must never be accepted as place_of_birth / place_of_issue / names.
_FIELD_LABEL_NOISE: frozenset[str] = frozenset(
    {
        "place of birth",
        "place of issue",
        "date of birth",
        "date of issue",
        "date of expiry",
        "nationality",
        "surname",
        "given names",
        "sex",
        "gender",
        "passport no",
        "passport number",
        "code",
        "type",
        "republic of india",
        "name of mother",
        "name of father",
        "name of spouse",
        "address",
        "file no",
        "file number",
        "nom",
        "prenom",
        "prenoms",
    }
)

_CRITICAL_KEYS: frozenset[str] = frozenset(
    {
        "surname",
        "given_names",
        "date_of_birth",
        "document_number",
        "date_of_expiry",
        "nationality",
    }
)

# TD3 lines are 44 chars; OCR often truncates — accept shorter and pad/stitch.
_MRZ_LINE_RE = re.compile(r"^[A-Z0-9<]{20,44}$")
_MRZ_P_LINE_RE = re.compile(r"^P[A-Z<][A-Z]{3}[A-Z0-9<]+$")
# Real TD3 line 1 always has the name separator << (or several fillers).
_MRZ_L1_BAD_WORDS_RE = re.compile(
    r"(PLACE|BIRTH|REPUBLIC|ADDRESS|FATHER|MOTHER|PASSPORT|SURNAME|GIVEN|"
    r"NATIONAL|SEX|INDIA|CHENNAI|MUMBAI|DELHI)"
)
# TD3 line 2 shape (doc no + check + nationality + DOB[+check] + sex + expiry).
# Optional DOB check digit; OCR may drop fillers. Doc number may start with P/A.
_MRZ_L2_SHAPE_RE = re.compile(
    r"^[A-Z0-9]{6,9}[<0-9A-Z]{1,3}[A-Z]{3}\d{6}\d?[MFX<]\d{6}[A-Z0-9<]*$"
)
_NEXT_FIELD_LABEL_RE = re.compile(
    r"(?i)^(place of|date of|name of|name ot|sex|gender|nationality|surname|"
    r"given|passport|code|type|file|address|old passport|mother|mather|"
    r"father|foter|spouse|legal guardian|lepai|curdian)\b"
)
_NAME_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z.'-]{0,30}$")
# OCR-tolerant page-2 labels (CamScanner often mangles Father/Mother/File/Spouse).
# "Nere of Pathvet / Legas Gusrdian" must still anchor Father / Legal Guardian.
_FATHER_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bf[ao]ther\b|\bfoter\b|\bfother\b|\bpathvet\b|"
    r"\bguardian\b|\bguardlan\b|\buardian\b|\bquardian\b|\bcurdian\b|\bgusrdian\b|\bgurdian\b|"
    r"n(?:ame|ane|eme|ere)\s*(?:of|ot|ol)\s*"
    r"(?:f[ao]ther|foter|fother|pathvet|guardian|guardlan|gusrdian|gurdian)"
    r"(?:\s*/\s*lega[ls]?\s*(?:guardian|guardlan|gusrdian|gurdian|curdian))?|"
    r"lega[ls]?\s*(?:guardian|guardlan|gusrdian|gurdian|curdian))"
)
_MOTHER_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bmother\b|\bmather\b|\bmothor\b|"
    r"n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:mother|mather|mothor|mathe|maches))"
)
_SPOUSE_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bspouse\b|\bspouce\b|\bspov(?:e|se)?\b|"
    r"n?ame\s*(?:of|ot|ol)\s*spov\w*|"
    r"n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:spouse|spouce|spov\w*))"
)
# Stricter evidence that the booklet actually prints a Spouse field (vs absent).
_SPOUSE_LABEL_EVIDENCE_RE = re.compile(
    r"(?i)(?:n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:spouse|spouce)|"
    r"spouse(?:'s)?\s*name|"
    r"\bspouse\b|\bspouce\b)"
)
_SPOUSE_BLANK_VALUE_RE = re.compile(
    r"(?i)^(n/?a|na|n\.a\.|nil|none|not\s*applicable|-|/|—|–|\.|x+|went)(?:\s*/.*)?$"
)
_FILE_LABEL_FUZZY_RE = re.compile(
    # Do not include "Pita No." — must not fuzzy-anchor File No. (value-shape rejects date pairs).
    r"(?i)(?:\bfile\s*(?:no\.?|number|#)\b|\bfileno\b|\bfke\s*no\.?\b|\bfle\s*no\.?\b|"
    r"\ba3\s*/\s*f(?:ile|ke)?\s*no|\bma\s*3\s*/\s*fke|"
    r"\bf\.?\s*no\.?\b)"
)
_PASSPORT_NO_SHAPE_RE = re.compile(r"^[A-Z]\d{7}$")
_FILE_NO_SHAPE_RE = re.compile(r"^[A-Z]{1,5}\d{6,14}[A-Z0-9]{0,4}$")
_FILE_OFFICE_CODE_RE = re.compile(
    r"^[A-Z]{1,8}\d{0,8}[A-Z]{0,4}/\d{1,8}/\d{1,8}$|"
    r"^[A-Z]{2,8}\d{3,10}/\d{2,4}$"
)
_FILE_DATE_IN_TEXT_RE = re.compile(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}")
_FILE_VALUE_JUNK_RE = re.compile(
    r"(?i)\b(?:pita|father|foter|fother|guardian|issue|lssue|expiry|expir|date of)\b"
)
# Parent-name blobs that swallowed page-1 OCR / labels / bilingual crumbs.
# Indian cover-note boilerplate ("BY ORDER OF THE PRESIDENT…") must never win.
_PARENT_NAME_JUNK_RE = re.compile(
    r"\b(?:republic|nationality|passport|type|code|sex|"
    r"place of|date of|name of|name ot|foter|lepai|curdian|mather|mothor|"
    r"guardian|guardlan|legal|uimeer|enpe|spouse|address|went|"
    r"father|fother|mother|"
    r"by\s+order|president|request\s+and\s+require|"
    r"stand in need|whom it may|assistance and protection|bearer to pass|"
    r"freely without|let or hindrance|every assistance|"
    r"onof|sptry|lssue|exptry|expiny)\b|"
    r"(?:^|[\s/])(?:fn|afy|faf|lssue|mothor)(?:[\s/]|$)|"
    r"^by\s+order(?:\s+of)?$",
    re.IGNORECASE,
)

# OCR crumbs that are never a real person name by themselves.
_NAME_OCR_CRUMB_RE = re.compile(
    r"(?i)^(fn|afy|faf|went|name|legal|guardlan|guardian|curdian|lepai|"
    r"address|den|room|nil|none|n/?a|mothor|foter|spouce)$"
)

_DATE_CAPTURE = (
    r"(?<!\d)(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}[./\-]\d{1,2}[./\-]\d{1,2})(?!\d)"
)

# Common nationality / country names → ISO 3166-1 alpha-3 (subset).
_NATIONALITY_ALPHA3: dict[str, str] = {
    "IND": "IND",
    "INDIAN": "IND",
    "INDIA": "IND",
    "USA": "USA",
    "UNITED STATES": "USA",
    "AMERICAN": "USA",
    "GBR": "GBR",
    "BRITISH": "GBR",
    "UNITED KINGDOM": "GBR",
    "AUS": "AUS",
    "AUSTRALIAN": "AUS",
    "AUSTRALIA": "AUS",
    "CAN": "CAN",
    "CANADIAN": "CAN",
    "CANADA": "CAN",
    "NZL": "NZL",
    "NEW ZEALAND": "NZL",
    "PAK": "PAK",
    "PAKISTANI": "PAK",
    "PAKISTAN": "PAK",
    "BGD": "BGD",
    "BANGLADESHI": "BGD",
    "BANGLADESH": "BGD",
    "NPL": "NPL",
    "NEPALI": "NPL",
    "NEPAL": "NPL",
    "LKA": "LKA",
    "SRI LANKAN": "LKA",
    "SRI LANKA": "LKA",
    "CHN": "CHN",
    "CHINESE": "CHN",
    "CHINA": "CHN",
    "JPN": "JPN",
    "JAPANESE": "JPN",
    "JAPAN": "JPN",
    "KOR": "KOR",
    "KOREAN": "KOR",
    "DEU": "DEU",
    "GERMAN": "DEU",
    "GERMANY": "DEU",
    "FRA": "FRA",
    "FRENCH": "FRA",
    "FRANCE": "FRA",
    "ARE": "ARE",
    "UAE": "ARE",
    "EMIRATI": "ARE",
}

_VALID_ALPHA3: frozenset[str] = frozenset(_NATIONALITY_ALPHA3.values())

# ISO alpha-3 → printed nationality (visual zone), not the country code.
_ALPHA3_DEMONYM: dict[str, str] = {
    "IND": "INDIAN",
    "USA": "AMERICAN",
    "GBR": "BRITISH",
    "AUS": "AUSTRALIAN",
    "CAN": "CANADIAN",
    "NZL": "NEW ZEALANDER",
    "PAK": "PAKISTANI",
    "BGD": "BANGLADESHI",
    "NPL": "NEPALI",
    "LKA": "SRI LANKAN",
    "CHN": "CHINESE",
    "JPN": "JAPANESE",
    "KOR": "KOREAN",
    "DEU": "GERMAN",
    "FRA": "FRENCH",
    "ARE": "EMIRATI",
}

# OCR confusions often seen in nationality / MRZ country codes.
_ALPHA3_OCR_FIXES: dict[str, str] = {
    "MRW": "IND",  # IND → MRW (I→M, N→R, D→W) on Indian passports
    "1ND": "IND",
    "IN0": "IND",
    "lND": "IND",
    "lN0": "IND",
}

# Adjacent biodata labels / OCR mash tokens that must never become nationality.
_NATIONALITY_BLEED_RE = re.compile(
    r"(?i)\b(?:"
    r"sex|sexe|gender|male|female|"
    r"date|dale|birth|birthdate|dob|"
    r"place|issue|expiry|expir|valid|"
    r"surname|given|forename|prenom|"
    r"passport|type|code|file|"
    r"father|mother|guardian|address|spouse|"
    r"croufuft|faiq"
    r")\b"
)

_NATIONALITY_LABEL_FUZZY_RE = re.compile(
    r"(?i)\b(?:nationality|nationalit[eé]|citizenship|citoyennet[eé])\b"
)

_KNOWN_DEMONYMS: frozenset[str] = frozenset(
    {d.upper() for d in _ALPHA3_DEMONYM.values()}
    | {
        k
        for k, v in _NATIONALITY_ALPHA3.items()
        if len(k) > 3 and v in _ALPHA3_DEMONYM
    }
)


def _norm_sex(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().upper()
    if s in {"M", "MALE"}:
        return "M"
    if s in {"F", "FEMALE"}:
        return "F"
    if s in {"X", "OTHER", "UNSPECIFIED"}:
        return "X"
    return None


def _to_alpha3(raw: str | None, *, allow_unknown: bool = False) -> str | None:
    """Map nationality/country text to ISO alpha-3; reject OCR garbage like MRW."""
    if not raw:
        return None
    key = re.sub(r"\s+", " ", raw.strip().upper())
    key = re.sub(r"[^A-Z0-9 ]", "", key)
    if not key:
        return None
    # Long OCR soup (label bleed) must not substring-match country names.
    if len(key.split()) > 3 or len(key) > 28:
        if key in _NATIONALITY_ALPHA3:
            return _NATIONALITY_ALPHA3[key]
        if key in _ALPHA3_OCR_FIXES:
            return _ALPHA3_OCR_FIXES[key]
        return None
    if key in _ALPHA3_OCR_FIXES:
        return _ALPHA3_OCR_FIXES[key]
    if len(key) == 3 and key.isalpha():
        if key in _VALID_ALPHA3:
            return key
        # Do not trust arbitrary 3-letter OCR tokens (e.g. MRW from "mrwrt").
        return key if allow_unknown else None
    mapped = _NATIONALITY_ALPHA3.get(key)
    if mapped:
        return mapped
    # Prefer whole-token containment over loose substring matches.
    tokens = set(key.split())
    for name, code in _NATIONALITY_ALPHA3.items():
        if len(name) <= 3:
            continue
        name_tokens = name.split()
        if len(name_tokens) == 1:
            if name in tokens:
                return code
        elif name in key and all(t in tokens for t in name_tokens):
            return code
    return None


def _is_noise_value(val: str | None) -> bool:
    if not val:
        return True
    cleaned = re.sub(r"\s+", " ", val.strip().lower())
    if cleaned in _FIELD_LABEL_NOISE:
        return True
    if cleaned.startswith("place of ") or cleaned.startswith("date of "):
        return True
    if cleaned.startswith("name of "):
        return True
    return False


def _is_ocr_junk_text_value(val: str | None) -> bool:
    """True when a passport text field is not plausible human text.

    Structural gate (not a ban-list): reject values that are mostly symbols,
    backslashes, braces, or letter soup with too few real letter runs. Real
    cities, person names, and addresses with letter words must still pass.
    File-number shape checks remain separate via ``_is_garbage_file_number``.
    """
    raw = str(val or "").strip()
    if not raw:
        return True
    letters = sum(1 for ch in raw if ch.isalpha())
    if letters < 3:
        return True
    if not re.search(r"[A-Za-z]{3,}", raw):
        return True
    junk_chars = sum(1 for ch in raw if ch in r"*{}[]\\|<>~`$^#@!?;+=")
    if junk_chars >= 2 and junk_chars / max(len(raw), 1) >= 0.12:
        return True
    if junk_chars >= 1 and letters / max(len(raw), 1) < 0.55:
        return True
    # Mixed-case keyboard smash with almost no word-like runs (e.g. fi*t{qf…).
    letter_runs = re.findall(r"[A-Za-z]{3,}", raw)
    if junk_chars >= 1 and (not letter_runs or max(len(r) for r in letter_runs) < 4):
        return True
    return False


def native_pdf_text_needs_ocr(text: str | None) -> bool:
    """True when a PDF text layer is symbol soup and must not replace page OCR.

    Born-digital classification can still see enough characters in a broken
    text layer. Those characters are not passport fields.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return False
    junkish = 0
    for ln in lines:
        symbols = sum(1 for ch in ln if ch in r"*{}[]\\|<>~`$^#")
        if _is_ocr_junk_text_value(ln) or symbols >= 2:
            junkish += 1
    if junkish / len(lines) >= 0.4:
        return True
    junk_chars = sum(1 for ch in raw if ch in r"*{}[]\\|<>~`$^#")
    letters = sum(1 for ch in raw if ch.isalpha())
    if junk_chars >= 6 and letters > 0 and junk_chars >= letters * 0.08:
        return True
    if junk_chars >= 12:
        return True
    return False


# Indian passport OCR often glues Sex/Nationality as "HA/INDIAN", "HR/INDIAN",
# "M/INDIAN" on the row above Place of Birth — never accept those as a city.
_NATIONALITY_AS_PLACE_RE = re.compile(
    r"(?i)^(?:[A-Z]{1,3}\s*/\s*)?(?:INDIAN|IND|INDIA)$"
)
_SEX_NATIONALITY_GLUE_RE = re.compile(
    r"(?i)^[MFX]\s*[/\s]\s*(?:INDIAN|IND|INDIA)$"
)


def _is_nationality_as_place(val: str | None) -> bool:
    """True when ``val`` is a nationality/header token, not a birth/issue city."""
    if not val:
        return False
    t = re.sub(r"\s+", " ", str(val).strip()).upper()
    if not t:
        return False
    if _NATIONALITY_AS_PLACE_RE.fullmatch(t) or _SEX_NATIONALITY_GLUE_RE.fullmatch(t):
        return True
    if re.fullmatch(r"[A-Z]{1,3}/INDIAN", t):
        return True
    bare = re.sub(r"^[A-Z]{1,3}/", "", t).strip()
    if bare in {"INDIAN", "IND", "INDIA"}:
        return True
    if t in _KNOWN_DEMONYMS or bare in _KNOWN_DEMONYMS:
        return True
    demonym, _code = resolve_nationality(bare if bare else t)
    if demonym and demonym.upper() in {t, bare} and "," not in t:
        return True
    return False


# Known CamScanner / OCR garbage blobs that must never become Other Details rows.
_OCR_JUNK_OTHER_EXACT: frozenset[str] = frozenset(
    {
        "tiwaruorontoeletdmod",
    }
)


def _is_ocr_junk_other_detail_token(raw: str | None) -> bool:
    """True for MRZ-like / long ALL-CAPS / no-vowel OCR blobs (not real field names)."""
    text = (raw or "").strip()
    if not text:
        return False
    compact = re.sub(r"[\s_\-./]+", "", text)
    if not compact:
        return False
    if compact.lower() in _OCR_JUNK_OTHER_EXACT:
        return True
    # MRZ-style: long A–Z / < run with no spaces
    if len(compact) >= 20 and re.fullmatch(r"[A-Za-z<]+", compact) and " " not in text:
        return True
    if " " in text:
        return False
    if len(compact) <= 12 or re.search(r"\d", compact):
        return False
    if not re.fullmatch(r"[A-Za-z]+", compact):
        return False
    letters = compact.lower()
    vowels = sum(1 for ch in letters if ch in "aeiou")
    if vowels == 0:
        return True
    # Long ALL-CAPS OCR blob (e.g. TIWARUORONTOELETDMOD)
    if len(compact) >= 14 and compact == compact.upper():
        return True
    if len(letters) >= 14 and vowels / len(letters) <= 0.22:
        return True
    return False


def is_plausible_nationality(raw: str | None) -> bool:
    """True when ``raw`` is a known demonym / ISO code (not OCR bleed garbage)."""
    demonym, code = resolve_nationality(raw)
    return bool(demonym or code)


def resolve_nationality(raw: str | None) -> tuple[str | None, str | None]:
    """Return ``(printed_demonym, alpha3)`` or ``(None, None)`` for junk/unknown.

    Rejects cross-row bleed like ``FAIQ SEX CROUFUFT DALE OF BIRTH``.
    """
    if not raw:
        return None, None
    cleaned = re.sub(r"[^A-Za-z ]", " ", str(raw))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None, None
    if _is_noise_value(cleaned) or _NEXT_FIELD_LABEL_RE.match(cleaned):
        return None, None
    if _NATIONALITY_BLEED_RE.search(cleaned):
        return None, None
    if _NATIONALITY_LABEL_FUZZY_RE.search(cleaned) and len(cleaned.split()) > 1:
        cleaned = _NATIONALITY_LABEL_FUZZY_RE.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return None, None
        if _NATIONALITY_BLEED_RE.search(cleaned):
            return None, None
    tokens = cleaned.split()
    if len(tokens) > 4 or len(cleaned) > 32:
        return None, None

    alpha = _to_alpha3(cleaned)
    if alpha and alpha in _VALID_ALPHA3:
        return _ALPHA3_DEMONYM.get(alpha, alpha), alpha

    upper = cleaned.upper()
    if upper in _KNOWN_DEMONYMS:
        alpha2 = _to_alpha3(upper)
        return upper, alpha2 if alpha2 in _VALID_ALPHA3 else None

    if len(tokens) == 1 and len(tokens[0]) <= 2:
        return None, None
    return None, None


def demonym_for_country_code(code: str | None) -> str | None:
    if not code:
        return None
    alpha = _to_alpha3(code) or str(code).strip().upper()
    if alpha in _VALID_ALPHA3:
        return _ALPHA3_DEMONYM.get(alpha, alpha)
    return None


def _has_trailing_name_crumb(val: str | None) -> bool:
    if not val:
        return False
    last = val.strip().split()[-1].upper().rstrip(".")
    return last in {
        "ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "NAME", "NO", "MQ", "O", "N",
    }


def _strip_trailing_name_crumbs(val: str | None) -> str | None:
    if not val:
        return None
    parts = val.strip().split()
    while parts and parts[-1].upper().rstrip(".") in {
        "ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "NAME", "NO", "MQ", "O", "N",
    }:
        parts.pop()
    return _clean_person_name(" ".join(parts)) if parts else None


def _clean_person_name(val: str | None) -> str | None:
    if not val or _is_noise_value(val):
        return None
    s = re.sub(r"\s+", " ", val.strip())
    # Drop leading OCR junk like "34-414/" or stray "P "
    s = re.sub(r"^[\d\-./]+", "", s).strip(" /|-")
    s = re.sub(r"(?i)^P\s+(?=[A-Z]{2,})", "", s).strip()
    # Country-code bleed from Type/Code column into Father name ("IND RAVI…").
    s = re.sub(
        r"(?i)^(ind|indian|usa|gbr|aus|can|nzl|sgp|are|sa|uae)\s+(?=[A-Z])",
        "",
        s,
    ).strip()
    # Bilingual Indian passport labels: "Nom", "Prenoms", "Sexe", …
    s = re.sub(
        r"(?i)^(nom|prenoms?|prenom|surname|given names?|name)\s+",
        "",
        s,
    ).strip()
    s = re.sub(
        r"(?i)\s+(nom|prenoms?|prenom)\s*$",
        "",
        s,
    ).strip()
    # Drop bilingual / Legal Guardian remnants glued onto the value.
    s = re.sub(
        r"(?i)\b(?:legal\s*)?(?:guardian|guardlan|curdian|lepai)\b",
        " ",
        s,
    )
    s = re.sub(r"(?i)\b(?:name\s*(?:of|ot)\s*(?:father|mother|spouse|spov\w*))\b", " ", s)
    s = re.sub(r"(?i)\s+n?ame\s+of\s+spov\w*", " ", s)
    s = re.sub(r"(?i)\s+nama\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" /|,-")
    # Drop trailing address / spouse / door-number fragments glued onto names.
    s = re.split(
        r"(?i)\b(?:n?ame\s*(?:of|ot)\s*(?:spouse|spov\w*)|spouse|d\.?\s*no\.?|door\s*no|"
        r"h\.?\s*no|lane|address|pin\b)\b",
        s,
        maxsplit=1,
    )[0].strip(" /|,-")
    s = re.sub(r"(?i)\s+nama\s*$", "", s).strip(" /|,-")
    # Passport number tokens (e.g. N4981701) and bare digit runs are not a name.
    s = re.sub(r"\b[A-Z]\d{7}\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d{6,}\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" /|,-")
    if len(s) < 2 or not re.search(r"[A-Za-z]", s):
        return None
    if _is_noise_value(s):
        return None
    # Reject blobs that still contain field-label / page-1 OCR junk.
    if _PARENT_NAME_JUNK_RE.search(s):
        return None
    # Reject leftover bilingual OCR crumbs ("fn afy").
    tokens = [t for t in s.split() if t]
    if tokens and all(_NAME_OCR_CRUMB_RE.match(t) or len(t) <= 2 for t in tokens):
        return None
    if len(s) > 60 and len(s.split()) > 6:
        return None
    if _PASSPORT_NO_SHAPE_RE.match(s.replace(" ", "").upper()):
        return None
    return s[:120]


def _looks_like_td3_line1(cleaned: str) -> bool:
    """True for a real TD3 line 1 (P<ISSUE<<NAMES…), not 'PLACEOFBIRTH…'."""
    if not cleaned or not cleaned.startswith("P") or len(cleaned) < 20:
        return False
    # Visual-zone digits sometimes glue onto the MRZ — evaluate the first 44 chars.
    core = cleaned[:44]
    if _MRZ_L1_BAD_WORDS_RE.search(core):
        return False
    # ICAO: P + type + 3-letter issuer; names separated by <<.
    if not (core.startswith("P<") or _MRZ_P_LINE_RE.match(core)):
        return False
    if "<<" not in core and core.count("<") < 4:
        return False
    return True


def _looks_like_td3_line2(cleaned: str) -> bool:
    """True when a normalized OCR line is TD3 line 2 (not the P<… name line).

    Classify by shape, not by leading letter. Passport numbers may start with
    ``P`` / ``A`` / etc.; those lines are still line 2 when they carry doc-no +
    nationality + DOB/sex/expiry runs. True line 1 (``P<`` / ``P``+type+issuer
    + ``<<`` names) is never treated as line 2.
    """
    if not cleaned or len(cleaned) < 20:
        return False
    # Shape-first: real TD3 line 1 is never line 2, even when both start with P.
    if _looks_like_td3_line1(cleaned):
        return False
    # Reject visual-zone label mashups that happen to look alphanumeric.
    if re.search(
        r"(DATE|EXPIR|PASSPORT|FATHER|MOTHER|ADDRESS|NAMEOF|PLACEOF|REPUBLIC|"
        r"SURNAME|GIVEN|NATIONAL|GUARDIAN)",
        cleaned,
    ):
        return False
    core = cleaned[:44]
    if _MRZ_L2_SHAPE_RE.match(core):
        return True
    # OCR often turns fillers into I/1 — still has digit date runs.
    digit_runs = re.findall(r"\d{6}", core)
    if len(digit_runs) >= 2 and re.match(r"^[A-Z0-9]", core) and core.count("<") >= 1:
        return True
    return False


def _is_name_continuation_line(line: str) -> bool:
    """True for an ALL-CAPS / Title-Case name fragment (no next-field label)."""
    t = (line or "").strip()
    if not t or _is_noise_value(t) or _NEXT_FIELD_LABEL_RE.match(t):
        return False
    if _ADDRESS_LABEL_RE.search(t) or _SPOUSE_LABEL_FUZZY_RE.search(t):
        return False
    if re.search(r"\d", t):
        return False
    if len(t) > 60:
        return False
    # Slash-heavy OCR crumbs ("qm / Addiese") are the next field, not a name.
    if "/" in t and not re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{4,}", t):
        return False
    tokens = t.replace("/", " ").split()
    if not tokens or len(tokens) > 6:
        return False
    stop = {"ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "NAME", "NO", "QM"}
    if len(tokens) == 1 and tokens[0].upper().rstrip(".") in stop:
        return False
    # Short non-initial crumbs mixed into a multi-token line → OCR soup.
    for tok in tokens:
        up = tok.upper().rstrip(".")
        if up in stop:
            continue
        if len(up) <= 2 and not re.fullmatch(r"[A-Za-z]\.?", tok):
            return False
    return all(_NAME_TOKEN_RE.match(tok) for tok in tokens)


def _person_name_before_label_on_line(text: str, label_re: str) -> str | None:
    """Person name printed on the same OCR line *before* a family field label.

    Last-page Indian layouts often OCR as ``BHUPAL SINGH MANRAL … /Name of
    Father/Legal Guardian 26356517`` — the name sits left of the label while
    the right side is a passport/file number.
    """
    pattern = re.compile(
        rf"(?im)^(?P<before>[^\n]*?)\b(?:{label_re})\b(?P<after>[^\n]*)$"
    )
    for m in pattern.finditer(text or ""):
        before = (m.group("before") or "").strip(" /|-")
        if not before:
            continue
        # Prefer the rightmost multi-token Latin name run in the prefix.
        runs = re.findall(
            r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,5})\b",
            before,
        )
        for cand in reversed(runs):
            if any(
                tok.upper()
                in {
                    "COUNTRY",
                    "CODE",
                    "PASSPORT",
                    "TYPE",
                    "REPUBLIC",
                    "INDIA",
                    "INDIAN",
                    "NATIONALITY",
                }
                for tok in cand.split()
            ):
                continue
            cleaned = _clean_person_name(cand)
            if not cleaned:
                continue
            # Drop trailing OCR crumbs glued to the label slash ("Rre/", "Re/").
            # Keep a real all-caps token such as RAJ.
            parts = cleaned.split()
            while parts and not re.fullmatch(r"[A-Za-z]\.", parts[-1]):
                tail = parts[-1]
                if len(tail) <= 2 or (len(tail) <= 3 and tail.upper() != tail):
                    parts.pop()
                    continue
                break
            cleaned = " ".join(parts) if parts else None
            if cleaned and _is_plausible_person_name(cleaned):
                return cleaned
    return None


def _person_name_after_label(text: str, label_re: str) -> str | None:
    """Read a person name after a label, including wrapped continuation lines.

    Indian passport page-2 names often span two OCR lines (four name parts with
    the last token alone on the next line).
    """
    # Do not let \\s cross newlines — otherwise the "same-line" group swallows
    # the first name line and a leading blank in the tail aborts continuation.
    # Allow OCR junk prefixes on the label line ("on o mq. Name ot Mather").
    pattern = re.compile(
        rf"(?im)(?:^|\n)[^\n]*?\b(?:{label_re})[ \t]*[:\-–—/]?[ \t]*(.*)$"
    )
    m = pattern.search(text or "")
    if not m:
        return None
    parts: list[str] = []
    same = (m.group(1) or "").strip()
    same_cmp = same.lstrip(" /|-")
    # If the label line includes "/ Legal Guardian" or a passport number, ignore.
    if (
        same
        and not _is_noise_value(same)
        and not re.match(
            r"(?i)^(place|date|name|sex|nationality|code|type|father|mother|"
            r"guardian|guardlan|legal|spouse|address|den)\b",
            same_cmp,
        )
        and not re.search(r"\b[A-Z]\d{7}\b", same, re.IGNORECASE)
        and not re.search(r"\b\d{6,}\b", same)
        and not _NEXT_FIELD_LABEL_RE.match(same)
        and not _NEXT_FIELD_LABEL_RE.match(same_cmp)
    ):
        parts.append(same)
    for raw in (text or "")[m.end() :].splitlines()[:8]:
        line = raw.strip()
        if not line:
            # Skip blank OCR gaps; do not abort — last name token is often next.
            continue
        if _NEXT_FIELD_LABEL_RE.match(line) or _is_noise_value(line):
            break
        if _SPOUSE_LABEL_FUZZY_RE.search(line):
            break
        if re.match(
            r"(?i)^(den|address|room|name\s*(?:of|ot)\s*spouse|spouse|went\s*/)\b",
            line,
        ):
            break
        if _ADDRESS_LABEL_RE.search(line):
            break
        if parts:
            if not _is_name_continuation_line(line):
                break
            parts.append(line)
            if len(" ".join(parts).split()) >= 6:
                break
            continue
        if not _is_name_continuation_line(line) and not re.search(r"[A-Za-z]{2,}", line):
            continue
        # Never treat an address-label OCR mash ("went / Address") as a name.
        if _ADDRESS_LABEL_RE.search(line) or re.search(r"(?i)\baddress\b", line):
            continue
        parts.append(line)
    after = _clean_person_name(" ".join(parts) if parts else None)
    # Same-line name left of the label wins for last-page Father layouts
    # ("BHUPAL SINGH MANRAL … Name of Father/Legal Guardian 26356517").
    before = _person_name_before_label_on_line(text or "", label_re)
    if before and _is_plausible_person_name(before):
        return before
    if after and _is_plausible_person_name(after):
        return after
    return after


def _parse_flexible_date(raw: str | None) -> str | None:
    """Parse OCR date text and return SCANX_DATE_FORMAT (default DD-MM-YYYY)."""
    return normalize_scanx_date(raw)


def _date_evidenced_in_text(text: str, iso_date: str | None) -> bool:
    """True when ``iso_date`` appears in OCR under a common date spelling."""
    if not iso_date or not text:
        return False
    parts = re.split(r"[-/.]", str(iso_date).strip())
    if len(parts) != 3:
        return False
    d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
    variants = {
        f"{d}/{m}/{y}",
        f"{d}-{m}-{y}",
        f"{d}.{m}.{y}",
        f"{int(d)}/{int(m)}/{y}",
        f"{int(d)}-{int(m)}-{y}",
        f"{y}-{m}-{d}",
    }
    up = (text or "").upper()
    return any(var.upper() in up for var in variants)


def _date_only_in_old_passport_context(text: str, iso_date: str | None) -> bool:
    """True when ``iso_date`` only appears on Old-Passport stamp lines (not DOB)."""
    if not iso_date or not text:
        return False
    # Rebuild likely OCR spellings of this ISO date (DD-MM-YYYY → DD/MM/YYYY etc.).
    parts = re.split(r"[-/.]", str(iso_date).strip())
    if len(parts) != 3:
        return False
    d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
    variants = {
        f"{d}/{m}/{y}",
        f"{d}-{m}-{y}",
        f"{d}.{m}.{y}",
        f"{int(d)}/{int(m)}/{y}",
        f"{int(d)}-{int(m)}-{y}",
    }
    hits = 0
    old_hits = 0
    for ln in (text or "").splitlines():
        up = ln.upper()
        for var in variants:
            if var.upper() in up or var in ln:
                hits += 1
                if re.search(r"(?i)old\s*pass", ln):
                    old_hits += 1
                break
    return hits > 0 and old_hits == hits


def _ordered_issue_expiry(d1: str | None, d2: str | None) -> tuple[str | None, str | None]:
    """Earlier full date is issue; the later one is expiry."""
    if not d1 or not d2 or d1 == d2:
        return None, None
    from datetime import datetime as _dt

    def _pd(s: str):
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                return _dt.strptime(s[:10], fmt)
            except ValueError:
                continue
        return None

    a, b = _pd(d1), _pd(d2)
    if not a or not b or a == b:
        return None, None
    if a <= b:
        return d1, d2
    return d2, d1


def _issue_expiry_from_paired_date_line(text: str | None) -> tuple[str | None, str | None]:
    """Two full dates on the line after a Date-of-Issue / Expiry label.

    Indian biodata prints ``22/11/2018 21/11/2028`` on one row. OCR often keeps
    only ``Date of lssue`` or ``Dete of Cepiry``, so the second date was dropped.
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]
    label_re = re.compile(
        r"(?i)(?:date|oate|dnte|dete|cato|cate|pafe)\s+\w{0,8}.{0,48}?"
        r"(?:issu|lssu|lesu|lasu|isss|expir|cepir|eapir|iaptr|capir)"
    )
    for i, line in enumerate(lines):
        found = re.findall(r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})\b", line)
        if len(found) < 2:
            continue
        prev = ""
        for j in range(i - 1, -1, -1):
            if lines[j]:
                prev = lines[j]
                break
        if re.search(r"(?i)old\s*pass", f"{prev} {line}"):
            continue
        if not label_re.search(prev):
            continue
        d1 = _parse_flexible_date(found[0])
        d2 = _parse_flexible_date(found[1])
        issue, expiry = _ordered_issue_expiry(d1, d2)
        if issue and expiry:
            return issue, expiry
    return None, None


def _date_before_issue_label(text: str | None) -> str | None:
    """Reversed column OCR: ``15/03/2021 … Date of issue``."""
    match = re.search(
        r"(?i)\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})\b"
        r"[^\n]{0,48}?\bdate\s*of\s*(?:issu|lssu|isss)",
        text or "",
    )
    if not match:
        return None
    if re.search(r"(?i)old\s*pass", match.group(0)):
        return None
    return _parse_flexible_date(match.group(1))


def _parse_month_year_date(raw: str | None) -> str | None:
    """Parse truncated OCR dates like ``05/2018`` as the 1st of that month."""
    if not raw:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})[./\-](\d{4})\s*", str(raw))
    if not m:
        return None
    month, year = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and 1990 <= year <= 2100):
        return None
    try:
        return format_scanx_date(date(year, month, 1))
    except ValueError:
        return None


def _mrz_date_yyMMdd(raw: str, *, expiry: bool = False) -> str | None:
    if not raw or len(raw) != 6 or not raw.isdigit():
        return None
    yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    if expiry:
        century = 2000 if yy < 50 else 1900
    else:
        century = 1900 if yy > 30 else 2000
    try:
        return format_scanx_date(date(century + yy, mm, dd))
    except ValueError:
        return None


def _mrz_check_digit(data: str) -> int:
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(data):
        if ch.isdigit():
            v = int(ch)
        elif "A" <= ch <= "Z":
            v = ord(ch) - 55
        elif ch == "<":
            v = 0
        else:
            v = 0
        total += v * weights[i % 3]
    return total % 10


# Passport number, DOB, expiry, sex, and nationality come only from a
# check-digit-valid TD3 line 2. A failed digit makes the whole line unusable.
_MRZ_LINE2_AUTHORITY_KEYS: tuple[str, ...] = (
    "document_number",
    "date_of_birth",
    "date_of_expiry",
    "sex",
    "nationality",
)


def _td3_check_matches(line: str, index: int, data: str) -> bool:
    if index >= len(line) or not line[index].isdigit():
        return False
    return int(line[index]) == _mrz_check_digit(data)


def _td3_line2_checks_pass(line: str) -> bool:
    """ICAO 9303 TD3 line 2: doc, birth, expiry, and composite check digits."""
    if not line or len(line) < 28:
        return False
    padded = (line + ("<" * 44))[:44]
    if not _td3_check_matches(padded, 9, padded[0:9]):
        return False
    if not _td3_check_matches(padded, 19, padded[13:19]):
        return False
    if not _td3_check_matches(padded, 27, padded[21:27]):
        return False
    composite = padded[0:10] + padded[13:20] + padded[21:43]
    if not _td3_check_matches(padded, 43, composite):
        return False
    if not _mrz_date_yyMMdd(padded[13:19]):
        return False
    if not _mrz_date_yyMMdd(padded[21:27], expiry=True):
        return False
    return True


def _authority_fields_from_line2(raw_line: str) -> dict[str, Any] | None:
    """Five identity fields from one TD3 line 2, or None when checks fail."""
    line = (_normalize_mrz_candidate(raw_line) + ("<" * 44))[:44]
    if not _looks_like_td3_line2(line):
        return None
    if not _td3_line2_checks_pass(line):
        return None
    doc_no = line[0:9].replace("<", "").strip()
    nat_raw = line[10:13].replace("<", "").strip()
    code = _to_alpha3(nat_raw) if nat_raw else None
    if nat_raw and nat_raw in _VALID_ALPHA3 and not code:
        code = nat_raw
    if code and code not in _VALID_ALPHA3:
        code = None
    dob = _mrz_date_yyMMdd(line[13:19])
    exp = _mrz_date_yyMMdd(line[21:27], expiry=True)
    if not doc_no or not dob or not exp:
        return None
    return {
        "document_number": doc_no,
        "date_of_birth": dob,
        "date_of_expiry": exp,
        "sex": _norm_sex(line[20]),
        "nationality": demonym_for_country_code(code) if code else None,
        "country_code": code,
    }


def _normalize_mrz_candidate(raw: str) -> str:
    s = raw.strip().upper()
    s = s.replace(" ", "").replace("«", "<").replace("‹", "<").replace(">", "<")
    # Common OCR substitutions in MRZ.
    trans = str.maketrans(
        {
            "O": "0",  # only inside digit runs — applied selectively below
        }
    )
    _ = trans
    s = s.replace("«", "<")
    # Letter O in country/doc positions is usually O; leave as-is for names.
    return re.sub(r"[^A-Z0-9<]", "", s)


def extract_mrz_lines(text: str) -> list[str]:
    """Collect TD3-like lines; stitch adjacent truncated fragments."""
    candidates: list[str] = []
    raw_lines = (text or "").splitlines()

    def _add(cand: str) -> None:
        c = (cand or "")[:44]
        if len(c) < 20:
            return
        # Shape first: line-2 doc numbers may start with P/A — do not drop them.
        if _looks_like_td3_line2(c):
            candidates.append(c)
            return
        if _looks_like_td3_line1(c):
            candidates.append(c)

    i_raw = 0
    while i_raw < len(raw_lines):
        cleaned = _normalize_mrz_candidate(raw_lines[i_raw])
        # Pull embedded MRZ tokens out of long OCR lines that also hold dates.
        for m in re.finditer(r"P<[A-Z0-9<]{30,44}", cleaned):
            _add(m.group(0))
        for m in re.finditer(r"[A-Z0-9]{6,9}<[A-Z0-9<]{20,44}", cleaned):
            _add(m.group(0))
        # Stitch short MRZ-like fragments on consecutive OCR lines only when
        # both sides look like MRZ (avoid gluing "REPUBLICOFINDIA" onto P<…).
        if 8 <= len(cleaned) < 28 and i_raw + 1 < len(raw_lines):
            looks_mrzish = (
                cleaned.startswith("P")
                or cleaned.count("<") >= 1
                or _looks_like_td3_line2(cleaned)
                or bool(re.match(r"^[A-Z0-9]{6,9}<", cleaned))
            )
            if looks_mrzish:
                nxt = _normalize_mrz_candidate(raw_lines[i_raw + 1])
                merged = (cleaned + nxt)[:44]
                if len(merged) >= 20 and (
                    _MRZ_LINE_RE.match(merged)
                    or _MRZ_P_LINE_RE.match(merged)
                    or _looks_like_td3_line2(merged)
                ):
                    cleaned = merged
                    i_raw += 1
        i_raw += 1
        if len(cleaned) < 20:
            continue
        if (
            cleaned.count("<") < 2
            and not cleaned.startswith("P")
            and not _looks_like_td3_line2(cleaned)
        ):
            continue
        if re.search(r"(ROOM|PIN|UNIVERSITY|ADDRESS|STREET|SADAN|REPUBLIC)", cleaned):
            continue
        _add(cleaned)

    # Prefer real TD3 lines (with << or dual date runs) over weak matches.
    candidates.sort(
        key=lambda c: (
            0 if _looks_like_td3_line1(c) else 1,
            0 if _looks_like_td3_line2(c) else 1,
            -c.count("<"),
            -len(re.findall(r"\d{6}", c)),
        )
    )

    # Stitch: short P-line + following name fragment → 44 chars.
    # Never consume a TD3 line-2 candidate as a name-line continuation.
    stitched: list[str] = []
    i = 0
    while i < len(candidates):
        cur = candidates[i]
        if _looks_like_td3_line1(cur) and len(cur) < 44 and i + 1 < len(candidates):
            nxt = candidates[i + 1]
            if (
                not _looks_like_td3_line1(nxt)
                and not _looks_like_td3_line2(nxt)
                and nxt.count("<") >= 2
            ):
                merged = (cur + nxt)[:44]
                if _looks_like_td3_line1(merged):
                    stitched.append(merged)
                    i += 2
                    continue
        # Stitch truncated line-2 halves.
        if (
            not _looks_like_td3_line1(cur)
            and len(cur) < 44
            and i + 1 < len(candidates)
            and not _looks_like_td3_line1(candidates[i + 1])
        ):
            nxt = candidates[i + 1]
            merged = (cur + nxt)[:44]
            if _looks_like_td3_line2(merged) or len(merged) >= 40:
                stitched.append(merged)
                i += 2
                continue
        stitched.append(cur)
        i += 1

    out: list[str] = []
    seen: set[str] = set()
    for ln in stitched:
        if ln in seen:
            continue
        seen.add(ln)
        out.append(ln)
    return out


def _parse_td3_line1(l1: str) -> dict[str, Any]:
    """Parse TD3 line 1 (names + issuing state) even when line 2 is missing."""
    out: dict[str, Any] = {}
    line = (l1 + ("<" * 44))[:44]
    out["document_type"] = (line[0] or "P").replace("<", "") or "P"
    issuing = line[2:5].replace("<", "")
    if issuing:
        fixed = _to_alpha3(issuing) or (_ALPHA3_OCR_FIXES.get(issuing))
        # Never keep OCR junk like "ACE" from a corrupted P-line.
        if fixed and fixed in _VALID_ALPHA3:
            out["country_code"] = fixed
        elif issuing in _VALID_ALPHA3:
            out["country_code"] = issuing
    names = line[5:44]
    if "<<" in names:
        family, _, rest = names.partition("<<")
        given = rest.replace("<", " ").strip()
    else:
        family, given = names, ""
    surname = family.replace("<", " ").strip()
    given_names = re.sub(r"\s+", " ", given).strip()
    # MRZ OCR often reads letter O as digit 0 inside names (VENU G0PAL).
    surname = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "O", surname)
    given_names = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "O", given_names)
    if surname:
        out["surname"] = surname
    if given_names:
        out["given_names"] = given_names
    return out


def _parse_td3_line2(l2: str, *, doc_number_hint: str | None = None) -> dict[str, Any]:
    """Parse a TD3 line 2 as printed. A visual passport number is not spliced in."""
    del doc_number_hint
    out: dict[str, Any] = {}
    raw = (l2 or "").upper()
    # Align when OCR prefixes junk before the passport number (e.g. "7U9663905<…").
    aligned = raw
    m = re.search(r"([A-Z]\d{7}<[A-Z0-9<]{20,})", raw)
    if m:
        aligned = m.group(1)
    else:
        m2 = re.search(r"([A-Z0-9]{6,9}<[A-Z0-9<]{20,})", raw)
        if m2:
            aligned = m2.group(1)
    line = (aligned + ("<" * 44))[:44]
    doc_no = line[0:9].replace("<", "")
    if doc_no:
        # Prefer Indian letter+7digits when present inside the token.
        ind = re.search(r"([A-Z]\d{7})", doc_no)
        out["document_number"] = ind.group(1) if ind else doc_no
    nat_raw = line[10:13].replace("<", "")
    nat = _to_alpha3(nat_raw) or _ALPHA3_OCR_FIXES.get(nat_raw)
    if nat:
        out["country_code"] = nat
    elif nat_raw and nat_raw in _VALID_ALPHA3:
        out["country_code"] = nat_raw
    dob = _mrz_date_yyMMdd(line[13:19])
    if dob:
        out["date_of_birth"] = dob
    sex = _norm_sex(line[20])
    if sex:
        out["sex"] = sex
    exp = _mrz_date_yyMMdd(line[21:27], expiry=True)
    if exp:
        out["date_of_expiry"] = exp
    # Reject clearly misaligned MRZ (expiry before birth, or 1980s expiry with 1990s+ DOB).
    if out.get("date_of_birth") and out.get("date_of_expiry"):
        from datetime import datetime as _dt

        def _pd(s: str):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return _dt.strptime(s[:10], fmt)
                except ValueError:
                    continue
            return None

        d_b, d_e = _pd(str(out["date_of_birth"])), _pd(str(out["date_of_expiry"]))
        if d_b and d_e and d_e <= d_b:
            out.pop("date_of_expiry", None)
            out["_mrz_misaligned"] = True
    try:
        check_src = line[0:9]
        if line[9].isdigit() and int(line[9]) != _mrz_check_digit(check_src):
            out["_mrz_doc_check_ok"] = False
        else:
            out["_mrz_doc_check_ok"] = True
    except Exception:
        pass
    return out


def parse_td3_mrz(
    lines: list[str],
    *,
    doc_number_hint: str | None = None,
) -> dict[str, Any]:
    """Parse ICAO 9303 TD3; tolerate missing/truncated line 2."""
    out: dict[str, Any] = {}
    if not lines:
        return out

    # Line 1 must be a real P<…<<NAMES line — never PLACEOFBIRTH… / ACE junk.
    line1 = next((ln for ln in lines if _looks_like_td3_line1(ln)), None)
    if not line1:
        # Still surface a plausible line-2 alone as incomplete MRZ.
        line2_only = next((ln for ln in lines if _looks_like_td3_line2(ln)), None)
        if line2_only:
            out.update(_parse_td3_line2(line2_only, doc_number_hint=doc_number_hint))
            out["mrz_string"] = (line2_only + ("<" * 44))[:44]
            out["_mrz_incomplete"] = True
        return out

    out.update(_parse_td3_line1(line1))
    idx = lines.index(line1)
    line2 = None
    for cand in lines[idx + 1 :]:
        if _looks_like_td3_line2(cand) or (
            len(cand) >= 28
            and not _looks_like_td3_line1(cand)
            and cand.count("<") >= 1
            and len(re.findall(r"\d{6}", cand)) >= 2
        ):
            line2 = cand
            break
    if not line2:
        for cand in lines:
            if cand is line1:
                continue
            if _looks_like_td3_line2(cand) or (
                len(cand) >= 28
                and not _looks_like_td3_line1(cand)
                and cand.count("<") >= 2
                and len(re.findall(r"\d{6}", cand)) >= 2
            ):
                line2 = cand
                break

    if line2:
        out.update(_parse_td3_line2(line2, doc_number_hint=doc_number_hint))
        l1 = (line1 + ("<" * 44))[:44]
        l2 = (line2 + ("<" * 44))[:44]
        # Prefer storing both lines whenever line 2 parses; checksum flags stay
        # on the payload (_mrz_doc_check_ok) and must not drop the pair.
        out["mrz_string"] = f"{l1}\n{l2}"
    else:
        # Keep partial MRZ so counsellors see what OCR captured; pad for display.
        out["mrz_string"] = (line1 + ("<" * 44))[:44]
        out["_mrz_incomplete"] = True
    return out


def normalize_multiline_address(raw: str | None) -> str | None:
    """Collapse OCR address newlines into one readable comma-separated line."""
    if raw is None:
        return None
    text = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    parts = [re.sub(r"\s+", " ", p).strip(" ,;") for p in text.split("\n")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    joined = ", ".join(parts)
    joined = re.sub(r"\s*,\s*", ", ", joined)
    joined = re.sub(r"(,\s*){2,}", ", ", joined).strip(" ,")
    return _sanitize_passport_address(joined)


# Document headers and barcode dumps are not a street. Close OCR spellings
# (l/I, 0/O) count. "INDIA" at the end of a PIN line does not.
_ADDRESS_ADMIN_HEADER_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"REPUB[LI1|]{1,2}C[\s.\-]*[O0]F[\s.\-]*[I1L|]ND[I1L|]A",
        re.IGNORECASE,
    ),
    re.compile(
        r"M[I1L|]SCELLANEOUS[\s.\-]*SERV[I1L|]CE",
        re.IGNORECASE,
    ),
    re.compile(r"पत[िी]\s*(?:या|[/|])\s*पत्नी"),
)


def _address_is_administrative_noise(raw: str | None) -> bool:
    """True when an assembled address is a header, translation, or barcode dump.

    The whole value is dropped. A street that only ends with the country name
    (``TELANGANA, INDIA``) is not this kind of header.
    """
    text = str(raw or "").strip()
    if not text:
        return False
    if any(rx.search(text) for rx in _ADDRESS_ADMIN_HEADER_RES):
        return True
    # A PIN is six digits, often ``PIN:506164``. A 10+ digit or symbol run is
    # a barcode, not that PIN. Door numbers stay because they are not one run.
    if re.search(r"\d{10,}", text):
        return True
    compact = re.sub(r"\s+", "", text)
    if re.search(r"[\d*#|]{10,}", compact):
        return True
    digits = re.sub(r"\D", "", text)
    words = re.findall(r"[A-Za-z\u0900-\u097F]{3,}", text)
    if len(digits) >= 12 and not words:
        return True
    return False


def _sanitize_passport_address(raw: str | None) -> str | None:
    """Drop old-passport / file / PIN-label OCR tails glued onto the address."""
    if raw is None:
        return None
    s = _strip_address_header_prefix(str(raw))
    if not s:
        return None
    # Bilingual crumbs between street and locality (e.g. "ROAD ddy / ZAMEEN…").
    s = re.sub(r"(?i)\s+\b(?:ddy|den|qa)\s*/\s*", ", ", s)
    # Keep a real "PIN:######" segment; cut garbage "PIN PDIA … old passport …".
    pin_keep = re.search(r"(?i)\bPIN\s*:?\s*\d{6}\b.*$", s)
    pin_tail = pin_keep.group(0) if pin_keep else None
    s = re.split(
        r"(?i)\b(?:old\s*passport|file\s*no\.?|"
        r"pin\s+pdia\b|pin\b(?!\s*:?\s*\d{6})|\bpdia\b|"
        r"\b[A-Z]\d{7}\b|\b[A-Z]{2}\d{10,}\b|"
        r"\d{1,2}\s+\d{1,2}\s+\d{4}\b)",
        s,
        maxsplit=1,
    )[0]
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"(,\s*){2,}", ", ", s).strip(" ,/")
    if pin_tail and not re.search(r"(?i)\bPIN\s*:?\s*\d{6}\b", s):
        s = f"{s}, {pin_tail.strip()}" if s else pin_tail.strip()
        s = re.sub(r"\s*,\s*", ", ", s).strip(" ,")
    kept = [
        part.strip()
        for part in s.split(",")
        if part.strip() and not _address_comma_part_is_label_fragment(part)
    ]
    s = ", ".join(kept)
    cleaned = s[:400] or None
    if cleaned and _address_is_administrative_noise(cleaned):
        return None
    return cleaned


def _address_comma_part_is_label_fragment(part: str) -> bool:
    """A comma piece that is only a place or expiry label, not a street."""
    text = re.sub(r"\s+", " ", str(part or "")).strip(" ,")
    if not text:
        return False
    if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b|\d{1,5}\s*[-/]\s*\d", text):
        return False
    if re.search(r"(?i)\b(?:nagar|road|street|lane|colony|school)\b", text):
        return False
    return bool(
        re.search(
            r"(?i)\b(?:"
            r"expir\w*|cepir\w*|e\s*xpiry|"
            r"cato\s+of|cate\s+of|oate\s+af|date\s+of|"
            r"place\s+(?:gf|of|ot|af)\s+birt"
            r")\b",
            text,
        )
    )


def _value_after_label(text: str, label_re: str) -> str | None:
    """Return the next non-empty line (or same-line value) after a field label.

    Uses ``[ \\t]*`` (not ``\\s*``) so the same-line group cannot swallow the
    next label line (e.g. Surname → Place of Birth → city).
    """
    pattern = re.compile(
        rf"(?im)(?:^|\n)[ \t]*(?:{label_re})[ \t]*[:\-–—/]?[ \t]*(.*)$"
    )
    m = pattern.search(text or "")
    if not m:
        return None
    same = (m.group(1) or "").strip()
    # Label remnants like Given Name(s) → "(s)" are not values.
    if same and re.fullmatch(r"\(\s*s\s*\)|/|[-–—:]+", same, flags=re.I):
        same = ""
    if same and not _is_noise_value(same) and not re.match(
        r"(?i)^(place|date|name|sex|nationality|code|type|father|mother|"
        r"guardian|legal)\b",
        same,
    ):
        return same
    # Walk following lines for the first real value.
    tail = (text or "")[m.end() :]
    for raw in tail.splitlines()[:8]:
        line = raw.strip()
        if not line:
            continue
        if _is_noise_value(line):
            continue
        if re.fullmatch(r"\(\s*s\s*\)|/|[-–—:]+", line, flags=re.I):
            continue
        if _NEXT_FIELD_LABEL_RE.match(line) or re.match(
            r"(?i)^(place of|date of|name of|sex|gender|nationality|surname|"
            r"given|passport|code|type|file|address|old passport)\b",
            line,
        ):
            # Hit the next label without a value — stop.
            break
        return line
    return None


def _slice_between_labels(
    text: str,
    start_label_re: str,
    end_label_re: str | None,
) -> str:
    """Return text after ``start`` label until ``end`` label (or EOF)."""
    start_pat = re.compile(
        rf"(?im)(?:^|\n)[ \t]*(?:{start_label_re})[ \t]*[:\-–—/]?[ \t]*(.*)$"
    )
    m = start_pat.search(text or "")
    if not m:
        return ""
    tail = (text or "")[m.end() :]
    same = (m.group(1) or "").strip()
    chunks: list[str] = []
    if (
        same
        and not _is_noise_value(same)
        and not _NEXT_FIELD_LABEL_RE.match(same)
        and not re.match(
            r"(?i)^(place|date|name|sex|nationality|code|type|father|mother|"
            r"guardian|legal)\b",
            same,
        )
    ):
        chunks.append(same)
    if end_label_re:
        end_pat = re.compile(
            rf"(?im)(?:^|\n)[ \t]*(?:{end_label_re})\b"
        )
        end_m = end_pat.search(tail)
        if end_m:
            tail = tail[: end_m.start()]
    if chunks:
        return "\n".join(chunks) + "\n" + tail
    return tail


def _name_from_block(block: str) -> str | None:
    """Collect name tokens from a label-bounded OCR block (multi-line OK)."""
    parts: list[str] = []
    for raw in (block or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _NEXT_FIELD_LABEL_RE.match(line) or _is_noise_value(line):
            # Soft-stop only when we already have name tokens.
            if parts:
                break
            continue
        # Address / file lines mean the name cell was blank — stop, do not
        # skip past them into street/city lines (spouse bleed). Bilingual
        # crumbs ("qa / Address") do not start with the word address.
        if re.search(
            r"(?i)\b(?:address|addrese|addiese|adrhess|adress|addres)\b",
            line,
        ) or _spouse_value_is_address_like(line):
            break
        if re.match(
            r"(?i)^(den|address|room|pin\b|file|old\s*passport|h\.?\s*no|door)\b",
            line,
        ):
            break
        if re.search(r"\d{3,}", line):
            break
        if "," in line and re.search(r"(?i)\b(?:urban|pin|university|pradesh|nadu|state)\b", line):
            break
        # Drop glued next-field words occasionally OCR'd onto the name line.
        cleaned = re.split(
            r"(?i)\b(?:name of|place of|date of|address|file\s*no|old passport|den/)\b",
            line,
            maxsplit=1,
        )[0].strip(" /|-")
        if not cleaned or cleaned.upper() in {"DEN", "RT", "RAN"}:
            continue
        if "," in cleaned:
            break
        if _is_name_continuation_line(cleaned) or (
            re.search(r"[A-Za-z]{2,}", cleaned) and len(cleaned) <= 80
        ):
            # Allow a trailing single token even when the line has punctuation.
            parts.append(cleaned)
            if len(" ".join(parts).split()) >= 8:
                break
            continue
        if parts:
            break
    return _clean_person_name(" ".join(parts) if parts else None)


def _box_center(box: Any) -> tuple[float, float] | None:
    if not isinstance(box, list) or len(box) < 4:
        return None
    try:
        xs = [float(p[0]) for p in box[:4]]
        ys = [float(p[1]) for p in box[:4]]
        return (sum(xs) / 4.0, sum(ys) / 4.0)
    except Exception:
        return None


def _is_parent_name_candidate(text: str) -> bool:
    """True for a clean person name (not a label/doc no.)."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if _is_noise_value(t) or _NEXT_FIELD_LABEL_RE.match(t):
        return False
    if (
        _FATHER_LABEL_FUZZY_RE.search(t)
        or _MOTHER_LABEL_FUZZY_RE.search(t)
        or _SPOUSE_LABEL_FUZZY_RE.search(t)
    ):
        return False
    if _FILE_LABEL_FUZZY_RE.search(t):
        return False
    if re.search(r"(?i)\b(?:address|given\s*name|surname|place\s*of|date\s*of)\b", t):
        return False
    # Allow initials like "K." / "A.B." but reject long digit runs (PIN / file no.).
    if re.search(r"\d{3,}", t):
        return False
    if _PARENT_NAME_JUNK_RE.search(t):
        return False
    # Issue/birth cities must never be parent-name candidates (place fields keep them).
    if re.fullmatch(
        r"(?i)(?:hyderabad|chennai|mumbai|delhi|bengaluru|bangalore|"
        r"kolkata|pune|jaipur|ahmedabad|lucknow|patna|kochi|trivandrum|"
        r"thiruvananthapuram|visakhapatnam|vijayawada|erode|guntur|"
        r"nagpur|telangana|maharashtra|tamil\s*nadu|karnataka|kerala|andhra)",
        t,
    ):
        return False
    # Prefer Latin tokens (passport English zone); allow a few punctuation chars.
    tokens = re.split(r"[\s/]+", t)
    tokens = [tok for tok in tokens if tok]
    if not tokens or len(tokens) > 7:
        return False
    _STOP = {
        "ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "IN", "AT",
        "NAME", "NO", "NO.", "MQ", "O", "N", "MQ.", "DEN", "RT", "RAN",
    }
    latin = 0
    meaningful = 0
    for tok in tokens:
        up = tok.upper().rstrip(".")
        if up in _STOP:
            continue
        # Short non-initial crumbs in a multi-token string → OCR soup
        # ("ww Onof sptry"), not a person name.
        if len(up) <= 2 and not re.fullmatch(r"[A-Za-z]\.?", tok):
            if len(tokens) >= 2:
                return False
        if _NAME_TOKEN_RE.match(tok):
            latin += 1
            if len(up) >= 2:
                meaningful += 1
            continue
        # Single-letter initials with optional period.
        if re.fullmatch(r"[A-Za-z]\.?", tok):
            latin += 1
            continue
        return False
    if latin < 1 or meaningful < 1:
        return False
    # Reject truncated OCR crumbs ("RAN", "RT", "on o mq").
    if meaningful == 1:
        only = next(
            tok.upper().rstrip(".")
            for tok in tokens
            if tok.upper().rstrip(".") not in _STOP
        )
        if len(only) < 4:
            return False
    return True


def _is_plausible_person_name(val: str | None) -> bool:
    """Final gate for father/mother/spouse — drops truncated OCR fragments."""
    if not val:
        return False
    if _is_ocr_junk_text_value(val):
        return False
    cleaned = _clean_person_name(val)
    if not cleaned:
        return False
    if _is_ocr_junk_text_value(cleaned):
        return False
    # Address / place bleed (comma + locality tokens).
    if "," in cleaned:
        return False
    if re.search(
        r"(?i)\b(?:urban|pin|university|room|sadan|lane|street|road|nagar|"
        r"pradesh|nadu|state|india|address|thota|block|school|college|"
        r"engineering|institute|polytechnic|hospital)\b",
        cleaned,
    ):
        return False
    # Door / flat numbers (E-202, 3-78/1) are addresses, not people.
    if re.search(r"\d", cleaned):
        return False
    # Issue/birth city crumbs must not become parent/spouse names.
    if re.fullmatch(
        r"(?i)(?:hyderabad|chennai|mumbai|delhi|bengaluru|bangalore|"
        r"kolkata|pune|jaipur|ahmedabad|lucknow|patna|kochi|trivandrum|"
        r"thiruvananthapuram|visakhapatnam|vijayawada|erode|guntur|"
        r"telangana|maharashtra|tamil\s*nadu|karnataka|kerala|andhra)",
        cleaned,
    ):
        return False
    # Address crumbs are not people ("BLOK A OAD", "NDIAN").
    if re.search(
        r"(?i)\b(?:blok|block|road|street|lane|nagar|pin|address|oad|thota)\b",
        cleaned,
    ):
        return False
    if re.fullmatch(r"(?i)n?dian|india|nationality|national|male|female", cleaned):
        return False
    if _NAME_OCR_CRUMB_RE.match(cleaned):
        return False
    tokens = cleaned.split()
    # Slash / pipe OCR soup ("eeuing/bllbe") is never a person name.
    if re.search(r"[/\\|]", cleaned):
        return False
    # Single short tokens are almost always OCR crumbs ("went", "fn"), not names.
    # Four-letter surnames (MUDI, RAO is three and stays out) are real.
    if len(tokens) == 1:
        only = tokens[0]
        if len(only) < 4 or _NAME_OCR_CRUMB_RE.match(only):
            return False
    if re.search(r"(?i)(?:^|\s)(?:ndian|indian|india)(?:\s|$)", cleaned) and (
        len(cleaned.split()) <= 2
        or re.search(r"\b[MFX]\b", cleaned)
        or re.search(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}", cleaned)
    ):
        return False
    if re.search(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}", cleaned):
        return False
    if re.fullmatch(r"(?i)[MFX]", cleaned):
        return False
    if _is_parent_name_candidate(cleaned):
        return True
    if (
        len(tokens) >= 2
        and len(cleaned) >= 8
        and re.search(r"[A-Za-z]{3,}", cleaned)
        and not _PARENT_NAME_JUNK_RE.search(cleaned)
        and not any(_NAME_OCR_CRUMB_RE.match(t) for t in tokens)
    ):
        return True
    return False


def _norm_holder_token(val: str | None) -> str:
    u = re.sub(r"[^A-Z0-9 ]", " ", (val or "").upper())
    return re.sub(r"\s+", " ", u).strip()


def _looks_like_signature_or_given_name(
    val: str | None,
    given_names: str | None = None,
    *,
    surname: str | None = None,
) -> bool:
    """True when a place field latched onto the holder's name or a signature."""
    t = (val or "").strip()
    if not t:
        return False
    if t.endswith(".") and len(t.split()) <= 2:
        return True
    if re.match(r"^[A-Z]\.\s*[A-Za-z]", t):
        return True
    u = _norm_holder_token(t)
    u_compact = u.replace(" ", "")
    # Surname: exact / compact equality only (avoid ALI ⊂ ALIGARH false positives).
    sn = _norm_holder_token(surname)
    if sn and (u == sn or u_compact == sn.replace(" ", "")):
        return True
    g = _norm_holder_token(given_names)
    if not g:
        return False
    if u == g or u_compact == g.replace(" ", ""):
        return True
    if u in g or g in u or u_compact in g.replace(" ", "") or g.replace(" ", "") in u_compact:
        return True
    # Token overlap (VENU GOPAL ↔ Venugopal).
    g_toks = {tok for tok in g.split() if len(tok) >= 3}
    for tok in g_toks:
        if tok in u_compact or u_compact in tok:
            return True
    return False


def _is_holder_name_as_place(
    val: str | None,
    *,
    surname: str | None = None,
    given_names: str | None = None,
) -> bool:
    """Structural reject: place must never equal the holder's given name or surname."""
    return _looks_like_signature_or_given_name(
        val, given_names, surname=surname
    )


def _looks_like_file_number_token(val: str | None) -> bool:
    """True for compact stamps (NG1063937171819) or office codes (HYD/1234/19)."""
    raw = str(val or "").strip()
    if not raw or len(raw) < 6:
        return False
    if _FILE_DATE_IN_TEXT_RE.search(raw):
        return False
    if _FILE_VALUE_JUNK_RE.search(raw):
        return False
    compact = re.sub(r"\s+", "", raw).upper()
    noslash = re.sub(r"[/\-]+", "", compact)
    if not noslash or len(noslash) < 6:
        return False
    if _PASSPORT_NO_SHAPE_RE.match(noslash):
        return False
    if re.search(r"\d{6}[MFX]\d{4,6}", noslash):
        return False
    if _looks_like_date_value(raw):
        return False
    if _FILE_NO_SHAPE_RE.match(noslash):
        return True
    if re.search(r"[A-Z]", compact) and _FILE_OFFICE_CODE_RE.match(compact):
        return True
    return False


def _is_garbage_file_number(val: str | None) -> bool:
    """Reject dates, father/Pita bleed, MRZ crumbs, and non-file tokens."""
    raw = str(val or "").strip()
    if not raw:
        return True
    if _FILE_DATE_IN_TEXT_RE.search(raw) or _FILE_VALUE_JUNK_RE.search(raw):
        return True
    if raw.count("/") >= 2 and not re.search(r"[A-Za-z]", raw):
        return True
    t = re.sub(r"[\s\-/]+", "", raw).upper()
    if not t or len(t) < 6:
        return True
    if re.match(r"^\d{4,6}[A-Z]{0,4}$", t) and len(t) <= 10:
        return True
    if _looks_like_date_value(raw):
        return True
    if _PASSPORT_NO_SHAPE_RE.match(t):
        return True
    if re.search(r"\d{6}[MFX]\d{4,6}", t):
        return True
    return not _looks_like_file_number_token(raw)


def _looks_like_date_value(val: str | None) -> bool:
    if not val:
        return False
    if _parse_flexible_date(val):
        return True
    return bool(re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$", (val or "").strip()))


def _complete_passport_date(val: str | None) -> str | None:
    """Keep only a full day-month-year. Fragments such as ``19`` are not dates."""
    parsed = _parse_flexible_date(val)
    if not parsed:
        return None
    parts = re.split(r"[-/.]", parsed.strip())
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    years = [part for part in parts if len(part) == 4]
    if len(years) != 1:
        return None
    year = int(years[0])
    if year < 1900 or year > 2100:
        return None
    return parsed


def _normalize_place_token(text: str | None) -> str:
    """Strip OCR page crumbs (``1 VISAKHAPATNAM``) without inventing values."""
    t = (text or "").strip()
    t = re.sub(r"^\d+\s+", "", t).strip(" ,/-")
    return t


def _is_postal_address_as_place(text: str | None) -> bool:
    """True for residential / PIN lines — never an issuing-office city.

    Place of Issue is the office city near its label. Address may still keep
    ``PIN:######, STATE, INDIA``; that line must not be stored as place_of_issue.
    """
    t = _normalize_place_token(text)
    if not t:
        return False
    if re.search(r"(?i)\bPIN\b", t):
        return True
    if re.search(r"(?<!\d)\d{6}(?!\d)", t):
        return True
    if re.search(
        r"(?i)\b(?:road|street|lane|colony|nagar|thota|complex|apartment|"
        r"flat|house|block|h\.?\s*no\.?|d\.?\s*no\.?|door|society)\b",
        t,
    ):
        return True
    # Multi-part postal: …, STATE, COUNTRY (or PIN already caught above).
    if t.count(",") >= 2 and re.search(
        r"(?i)\b(?:pradesh|nadu|india|state|province|territory)\b", t
    ):
        return True
    if re.search(r"(?i),\s*INDIA\s*$", t) and "," in t:
        return True
    return False


def _is_place_candidate(
    text: str,
    *,
    surname: str | None = None,
    given_names: str | None = None,
) -> bool:
    """True for letter-only place names of any reasonable length (CITY, STATE ok).

    Rejects only structural junk: nationality headers, MRZ crumbs (``<`` / digits),
    signatures, and the holder's own given name / surname when known.
    Birth may be ``CITY, STATE``. Issuing office uses ``_is_issuing_office_candidate``.
    """
    t = _normalize_place_token(text)
    if not t or len(t) < 3 or len(t) > 80:
        return False
    if _is_ocr_junk_text_value(t):
        return False
    if _looks_like_date_value(t):
        return False
    if _is_noise_value(t) or _NEXT_FIELD_LABEL_RE.match(t):
        return False
    if _is_nationality_as_place(t):
        return False
    if _is_holder_name_as_place(t, surname=surname, given_names=given_names):
        return False
    # Handwritten signature lines often sit near Place of Issue.
    if re.match(r"^[A-Z]\.\s*[A-Za-z]", t):
        return False
    if t.endswith(".") and len(t.split()) <= 2:
        return False
    if re.search(
        r"(?i)\b(?:place of|date of|passport|nationality|surname|given|sex|type|code)\b",
        t,
    ):
        return False
    if not re.search(r"[A-Za-z]{3,}", t):
        return False
    # Slash or pipe is OCR soup (``f/Sos``), not a city or ``CITY, STATE``.
    if re.search(r"[/\\|]", t):
        return False
    # MRZ crumbs only: fillers or digits. Pure-letter cities of any length stay.
    compact = re.sub(r"[\s,./\-]+", "", t)
    if "<" in compact or (
        len(compact) >= 12
        and re.fullmatch(r"[A-Z0-9]+", compact)
        and re.search(r"\d", compact)
    ):
        return False
    return True


def _is_issuing_office_candidate(
    text: str,
    *,
    surname: str | None = None,
    given_names: str | None = None,
) -> bool:
    """Place of Issue: office city near the issue label — not address / birth shape.

    Rejects PIN / postal address lines and ``CITY, STATE`` (birth-shaped). A single
    city token such as VISAKHAPATNAM or CHENNAI is accepted.
    """
    t = _normalize_place_token(text)
    if not _is_place_candidate(t, surname=surname, given_names=given_names):
        return False
    if _is_postal_address_as_place(t):
        return False
    if "," in t and re.search(
        r"(?i)\b(?:pradesh|nadu|india|state|province|territory)\b", t
    ):
        return False
    if t.count(",") >= 2:
        return False
    return True


_GLUED_STATE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("ANDHRAPRADESH", "ANDHRA PRADESH"),
    ("ARUNACHALPRADESH", "ARUNACHAL PRADESH"),
    ("HIMACHALPRADESH", "HIMACHAL PRADESH"),
    ("MADHYAPRADESH", "MADHYA PRADESH"),
    ("UTTARAKHAND", "UTTARAKHAND"),
    ("UTTARPRADESH", "UTTAR PRADESH"),
    ("TAMILNADU", "TAMIL NADU"),
    ("WESTBENGAL", "WEST BENGAL"),
    ("MAHARASHTRA", "MAHARASHTRA"),
    ("TELANGANA", "TELANGANA"),
    ("KARNATAKA", "KARNATAKA"),
    ("RAJASTHAN", "RAJASTHAN"),
    ("CHHATTISGARH", "CHHATTISGARH"),
    ("JHARKHAND", "JHARKHAND"),
)


def _split_glued_city_state(token: str | None) -> str | None:
    """Insert comma-space when OCR glues ``CITYSTATE`` (MUMBAIMAHARASHTRA)."""
    raw = re.sub(r"\s+", " ", str(token or "")).strip(" ,.")
    raw = re.sub(r"\s*,\s*", ", ", raw)
    if not raw or "," in raw:
        return raw or None
    compact = re.sub(r"[^A-Za-z]", "", raw).upper()
    for suffix, pretty in _GLUED_STATE_SUFFIXES:
        if compact.endswith(suffix) and len(compact) > len(suffix) + 2:
            city = compact[: -len(suffix)]
            if city.isalpha() and len(city) >= 3:
                return f"{city}, {pretty}"
    return raw


# City, State — the state token is a grammar check, not a city copied from issue.
_STATE_GRAMMAR_RE = re.compile(
    r"(?i)\b("
    r"(?:andhra|arunachal|himachal|madhya|uttar)\s*pradesh|"
    r"tamil\s*nadu|west\s*bengal|"
    r"uttarakhand|telangana|maharashtra|karnataka|kerala|gujarat|"
    r"rajasthan|odisha|orissa|punjab|haryana|bihar|assam|"
    r"jharkhand|chhattisgarh|chattisgarh|goa"
    r")\b"
)


def _pretty_state_name(state: str) -> str:
    key = re.sub(r"[^A-Za-z]", "", state or "").upper()
    spaced = {
        "ANDHRAPRADESH": "ANDHRA PRADESH",
        "ARUNACHALPRADESH": "ARUNACHAL PRADESH",
        "HIMACHALPRADESH": "HIMACHAL PRADESH",
        "MADHYAPRADESH": "MADHYA PRADESH",
        "UTTARPRADESH": "UTTAR PRADESH",
        "TAMILNADU": "TAMIL NADU",
        "WESTBENGAL": "WEST BENGAL",
    }
    if key in spaced:
        return spaced[key]
    return re.sub(r"\s+", " ", (state or "").upper()).strip()


def _city_state_token(fragment: str | None) -> str | None:
    """CITY, STATE inside a line. Streets, PIN lines, and districts do not pass."""
    text = re.sub(r"\s+", " ", str(fragment or "")).strip(" ,|")
    if not text:
        return None
    for match in re.finditer(
        r"(?i)\b([A-Z]{3,24})\s*,\s*([A-Z][A-Z .]{2,40})",
        text,
    ):
        if re.search(r"\d", match.group(0)):
            continue
        city = match.group(1).upper()
        state_hit = _STATE_GRAMMAR_RE.search(match.group(2))
        if not state_hit:
            continue
        if re.search(r"(?i)nagar|road|street|school|lane|colony", city):
            continue
        state = _pretty_state_name(state_hit.group(1))
        candidate = f"{city}, {state}"
        if _place_value_is_label_junk(candidate) or not _is_place_candidate(candidate):
            continue
        return candidate
    compact = re.sub(r"[^A-Za-z]", "", text).upper()
    if not compact or re.search(r"\d", text):
        return None
    glued = _split_glued_city_state(compact)
    if not glued or "," not in glued or not _STATE_GRAMMAR_RE.search(glued):
        return None
    city, state = [part.strip() for part in glued.split(",", 1)]
    candidate = f"{city}, {_pretty_state_name(state)}"
    if _place_value_is_label_junk(candidate) or not _is_place_candidate(candidate):
        return None
    return candidate


def _city_state_near_birth_label(text: str | None) -> str | None:
    """Place of birth from its own label, including ``Place gf Birth``.

    The value has to be city/state grammar. A street glued on the label line
    is skipped. Place of issue is not reused.
    """
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        if not _PLACE_OF_BIRTH_LABEL_RE.search(line):
            continue
        if _PLACE_OF_ISSUE_LABEL_RE.search(line) and not re.search(
            r"(?i)birth|birt|burt|blrth|birih|bith", line
        ):
            continue
        tail = re.sub(
            rf"(?i)^.*?\b{_PLACE_OF_BIRTH_WORD_OCR}\b",
            "",
            line,
            count=1,
        ).strip(" ,|")
        hit = _city_state_token(tail) if tail else None
        if hit:
            return hit
        for nxt in lines[index + 1 : index + 4]:
            piece = nxt.strip()
            if not piece:
                continue
            if _PLACE_OF_ISSUE_LABEL_RE.search(piece) or _PLACE_OF_BIRTH_LABEL_RE.search(
                piece
            ):
                break
            if _line_is_mrz_boundary(piece):
                break
            hit = _city_state_token(piece)
            if hit:
                return hit
    return None


def _place_value_is_label_junk(val: str | None) -> bool:
    """A place field must not be a garbled Place-of label or symbol soup."""
    s = str(val or "").strip()
    if not s:
        return True
    if re.search(r"(?i)\b(?:p[il]?ace|pace|puce)\s*o[ft]\b", s):
        return True
    letters = re.findall(r"[A-Za-z]", s)
    if len(s) >= 10 and (len(letters) / len(s)) < 0.45:
        return True
    return False


def _birth_after_short_place_label(text: str | None) -> str | None:
    """``Place of 6`` then ``CITY, STATE`` when Birth OCR collapses to junk."""
    match = re.search(
        r"(?im)^[^\n]*\b(?:place|pace|puce|piace)\s+of\s+\S{1,4}\s*$\n+"
        r"\s*([A-Za-z][A-Za-z .'-]{1,30}\s*,\s*[A-Za-z][A-Za-z .'-]{2,40})",
        text or "",
    )
    if not match:
        return None
    city = _split_glued_city_state(match.group(1))
    if not city or _place_value_is_label_junk(city):
        return None
    return city.upper()[:80]


def _city_state_before_birth_label(text: str | None) -> str | None:
    """Reversed column OCR: ``ERODE,TAMIL NADU Place of Birth``."""
    match = re.search(
        rf"(?i)\b([A-Z][A-Z]{{2,24}}\s*,\s*[A-Z][A-Z .]{{2,30}})\s+"
        rf"(?:[a-z]\s*/\s*)?{_PLACE_WORD_OCR}\s*o[ft]\s*{_PLACE_OF_BIRTH_WORD_OCR}\b",
        text or "",
    )
    if not match:
        return None
    city = _split_glued_city_state(match.group(1))
    if not city or _place_value_is_label_junk(city):
        return None
    return city.upper()[:80]


def _city_token_from_noisy_line(line: str | None) -> str | None:
    """Longest alphabetic token on a noisy issue line (``R.L. HYDERABAD …``)."""
    best = ""
    for tok in re.findall(r"[A-Za-z]{4,}", line or ""):
        if re.fullmatch(
            r"(?i)place|pace|piace|issue|lssue|ssue|date|dnte|iaptry|expiry|birth",
            tok,
        ):
            continue
        if len(tok) > len(best):
            best = tok
    return best.upper() if best else None


def _issue_city_before_garbled_label(text: str | None) -> str | None:
    """``Date of issue CHENNAI … Piace of ssue`` — city sits before the label."""
    match = re.search(
        rf"(?i)date\s*of\s*{_PLACE_OF_ISSUE_OCR}\s+([A-Za-z]{{4,24}})\b"
        rf".{{0,48}}?{_PLACE_WORD_OCR}\s*o[ft]",
        text or "",
    )
    if not match:
        return None
    return match.group(1).upper()


def _issue_city_on_garbled_label(text: str | None) -> str | None:
    """City on the line after ``Place ot.lssue`` / ``Piace of ssue``."""
    raw = text or ""
    for match in _PLACE_OF_ISSUE_LABEL_RE.finditer(raw):
        tail = raw[match.end() :].split("\n", 1)[0]
        if "," in tail:
            tail = ""
        city = _city_token_from_noisy_line(tail)
        if city:
            return city
        for ln in raw[match.end() :].splitlines()[:4]:
            line = ln.strip()
            if not line:
                continue
            if re.search(r"(?i)\b(?:place|pace|piace)\s*o[ft]\s*birth\b", line):
                break
            city = _city_token_from_noisy_line(line)
            if city:
                return city
            break
    return None


def _spouse_value_is_address_like(
    value: str | None,
    address: str | None = None,
) -> bool:
    """True when a spouse string is a street, school, door number, or city line.

    A Spouse label with a blank cell often sits directly above Address. ALL-CAPS
    address lines must not be stored as a person.
    """
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return False
    if re.search(
        r"(?i)\b(?:school|college|university|institute|engineering|polytechnic|"
        r"hospital|apartment|road|street|lane|nagar|colony|block|flat|room|"
        r"house|door|plot|pin|address|urban|district)\b",
        raw,
    ):
        return True
    if re.search(r"(?i)\b(?:h|d)\.?\s*no\b", raw):
        return True
    if re.search(r"\d", raw):
        return True
    if re.search(
        r"(?i)\b(?:hyderabad|chennai|mumbai|delhi|bengaluru|bangalore|"
        r"kolkata|pune|jaipur|ahmedabad|lucknow|patna|kochi|"
        r"karnataka|telangana|maharashtra|tamil\s*nadu|kerala|andhra|"
        r"pradesh|india)\b",
        raw,
    ):
        return True
    addr = re.sub(r"\s+", " ", str(address or "")).strip()
    core = re.sub(r"(?i)^(?:qa|den|qan|qm)\s+", "", raw).strip(" /")
    if addr and core and len(core) >= 12 and core.upper() in addr.upper():
        return True
    return False


def _spouse_supported_by_label(
    value: str | None,
    text: str | None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """Spouse stays only when a Spouse label or an unlabeled person-row supports it.

    Address-like strings never count as support. Without a Spouse label, the only
    allowed source is the three-name unlabeled family row (a real person name).
    """
    if not value or _spouse_value_is_address_like(value):
        return False
    if not _is_plausible_person_name(value):
        return False
    lines = [ln for ln in (text or "").splitlines()]
    for blk in blocks or []:
        if isinstance(blk, dict):
            lines.append(_block_text(blk))
    if _name_is_notary_neighbor(value, lines):
        return False
    # A Spouse label only supports the value in its own cell. A stamp or
    # another field sitting elsewhere on the page is not that value.
    if not _passport_has_spouse_label(text, blocks):
        return False
    zone = _family_label_zone_value(
        "spouse_name", text=text, ocr_blocks=blocks
    )
    return bool(zone and zone.strip().upper() == str(value).strip().upper())


_STAMP_TITLE_RE = re.compile(
    r"(?i)\b(?:advoc\w*|notary|notar\w*|attorney|attest\w*|"
    r"b\.?\s*a\.?\s*l+\.?\s*m\.?|b\.?\s*allm|ballm|b\.?\s*a\.?\s*llm|"
    r"ll\.?\s*m\.?)\b"
)
# Notary / attestation / true-copy comments overlaid on a passport page.
# OCR often drops a letter (Netary, Otary) or glues "ATTESTED".
_NOTARY_COMMENT_RE = re.compile(
    r"(?i)(?:"
    r"\badvoc\w*\b|"
    r"\bnotari\w*\b|"
    r"\bnotar\w*\b|"
    r"\bnetary\b|"
    r"\botary\b|"
    r"\battest\w*\b|"
    r"\battorney\b|"
    r"\btrue\s*cop\w*\b|"
    r"\bcertified\s*(?:true\s*)?cop\w*\b|"
    r"\bstamp\s*duty\b|"
    r"\bsolemnly\b|"
    r"\bverified\b|"
    r"\bverification\b|"
    r"\bb\.?\s*a\.?\s*l+\.?\s*m\.?\b|"
    r"\bb\.?\s*allm\b|"
    r"\bballm\b|"
    r"\bb\.?\s*a\.?\s*llm\b|"
    r"\bll\.?\s*b\.?\b|"
    r"\bll\.?\s*m\.?\b"
    r")"
)
# Lines that carry passport content stay even when a stamp shares the line.
_PASSPORT_PAYLOAD_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:passport|passeport)\b|"
    r"\brepublic\s+of\b|"
    r"\b(?:surname|family\s+name|given\s+names?)\b|"
    r"\bdate\s+of\s+(?:birth|issue|expir\w*)\b|"
    r"\b(?:nationality|nationalit[eé])\b|"
    r"\bplace\s+of\s+(?:birth|issue)\b|"
    r"\b(?:father|mother|spouse)\b|"
    r"\b(?:file\s*(?:no\.?|number)|mrz)\b|"
    r"\baddress\b|"
    r"P\s*<|"
    r"<{4,}"
    r")"
)
_PASSPORT_LABEL_LINE_RE = re.compile(
    r"(?i)\b(?:surname|given\s+names?|date\s+of\s+birth|date\s+of\s+issue|"
    r"date\s+of\s+expir|place\s+of\s+birth|place\s+of\s+issue|address|"
    r"nationality|name\s+of\s+(?:father|mother|spouse)|passport\s*(?:no|number)|"
    r"file\s*(?:no|number))\b"
)
# Residential lines (street, door, PIN) are not stamp locality.
_STREET_LINE_RE = re.compile(
    r"(?i)(?:\bpin\s*:?\s*\d{6}\b|\b\d{6}\b|"
    r"\b(?:road|street|lane|nagar|colony|block|flat|room|house|door|plot|"
    r"apartment)\b|\bh\.?\s*no\b|\bd\.?\s*no\b)"
)
# State / admin words are shared by a stamp and a real place of birth.
# Distinctive locality tokens (the town the stamp repeats) are what cluster.
_STAMP_GEO_GENERIC = frozenset(
    {
        "india",
        "state",
        "urban",
        "rural",
        "district",
        "pradesh",
        "telangana",
        "karnataka",
        "maharashtra",
        "tamil",
        "nadu",
        "kerala",
        "andhra",
        "gujarat",
        "bengal",
        "uttar",
        "madhya",
        "rajasthan",
        "punjab",
        "haryana",
        "bihar",
        "odisha",
        "orissa",
        "assam",
        "delhi",
        "goa",
        "jharkhand",
        "chhattisgarh",
        "uttarakhand",
        "himachal",
        "manipur",
        "meghalaya",
        "mizoram",
        "nagaland",
        "tripura",
        "sikkim",
        "ladakh",
        "kashmir",
        "jammu",
    }
)
# "B. BHAVANY" is an attestor initial, not "T.S. INDIA" / "S. INDIA".
_STAMP_NAME_PREFIX_RE = re.compile(
    r"(?i)(?<![A-Za-z.])\b[A-Z]\.\s+(?!INDIA\b|STATE\b)[A-Z]{4,}\b"
)
_LOCALITY_MARK_RE = re.compile(
    r"(?i)\b(?:india|state|urban|rural|district|pradesh|nagar|"
    r"road|street|colony|taluk|mandal|pin)\b|\bT\.?\s*S\.?\b"
)
_LOCALITY_TOKEN_SKIP = frozenset(
    {
        "india",
        "state",
        "urban",
        "rural",
        "advocate",
        "notary",
        "notarial",
        "attorney",
        "attested",
        "attest",
        "ballm",
        "allm",
    }
)


def _prep_locality_line(line: str) -> str:
    s = _STAMP_TITLE_RE.sub(" ", line or "")
    s = _STAMP_NAME_PREFIX_RE.sub(" ", s)
    s = re.sub(r"[★*•|]+", " ", s)
    s = re.sub(r"\s+\d{1,3}\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-/&")
    s = re.sub(r"\s*,\s*", ", ", s)
    return s.strip(" ,")


def _locality_signature(line: str) -> set[str]:
    out: set[str] = set()
    for tok in re.findall(r"[A-Za-z]{4,}", (line or "").lower()):
        if tok in _LOCALITY_TOKEN_SKIP:
            continue
        out.add(tok)
    return out


def _locality_token_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    matched = 0
    used: set[str] = set()
    for ta in left:
        for tb in right:
            if tb in used:
                continue
            if ta == tb or (
                len(ta) >= 4
                and len(tb) >= 4
                and SequenceMatcher(None, ta, tb).ratio() >= 0.78
            ):
                matched += 1
                used.add(tb)
                break
    return matched / max(min(len(left), len(right)), 1)


def _locality_parts_are_repeats(parts: list[str]) -> bool:
    """True when fragments are OCR variants of one locality, not a street address."""
    return _largest_locality_cluster(parts) is not None


def _largest_locality_cluster(parts: list[str]) -> list[str] | None:
    """Biggest set of near-duplicate locality lines. Street addresses stay split."""
    sigs = [_locality_signature(p) for p in parts]
    n = len(parts)
    if n < 3:
        return None
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        if not sigs[i]:
            continue
        for j in range(i + 1, n):
            if not sigs[j]:
                continue
            if _locality_token_overlap(sigs[i], sigs[j]) >= 0.5:
                union(i, j)
    groups: dict[int, list[str]] = {}
    for i, part in enumerate(parts):
        if not sigs[i]:
            continue
        groups.setdefault(find(i), []).append(part)
    if not groups:
        return None
    ranked = sorted(groups.values(), key=len, reverse=True)
    largest = ranked[0]
    second = len(ranked[1]) if len(ranked) > 1 else 0
    # A real street address splits into singletons. A stamp repeats one locality.
    if len(largest) < 3 or len(largest) <= second:
        return None
    return largest


def _best_locality_line(parts: list[str]) -> str | None:
    sigs = [_locality_signature(p) for p in parts]
    best: str | None = None
    best_score = -1e9
    for i, line in enumerate(parts):
        consensus = 0
        for tok in sigs[i]:
            hits = 0
            for j, other in enumerate(sigs):
                if j == i:
                    continue
                if any(
                    tok == o
                    or (
                        len(tok) >= 4
                        and len(o) >= 4
                        and SequenceMatcher(None, tok, o).ratio() >= 0.78
                    )
                    for o in other
                ):
                    hits += 1
            if hits >= max(2, int(0.25 * max(len(sigs) - 1, 1))):
                consensus += 1
        bonus = 0
        if re.search(r"(?i)\bindia\b", line):
            bonus += 3
        if re.search(r"(?i)\bstate\b|\bT\.?\s*S\.?\b", line):
            bonus += 2
        if re.search(r"(?i)\burban\b|\brural\b", line):
            bonus += 1
        garbage = len(re.findall(r"[^A-Za-z\s,.\-]", line))
        score = consensus * 4 + bonus + min(len(line), 90) / 30.0 - garbage * 2
        if score > best_score:
            best_score = score
            best = line
    return best


def _attach_country_fragment(chosen: str, parts: list[str]) -> str:
    """Keep one state/country tail when the winning line does not already have it."""
    if re.search(r"(?i)\bindia\b|\bstate\b|\bT\.?\s*S\.?\b", chosen):
        return chosen
    for part in parts:
        if part.upper() == chosen.upper():
            continue
        if not re.search(r"(?i)\bindia\b|\bstate\b|\bT\.?\s*S\.?\b", part):
            continue
        if len(part) > 48:
            continue
        if _locality_token_overlap(_locality_signature(part), _locality_signature(chosen)) >= 0.5:
            continue
        return f"{chosen}, {part}"
    return chosen


def _collapse_repeated_locality_parts(parts: list[str]) -> str | None:
    """Reduce repeated city/state OCR variants to one line that is actually present."""
    prepped: list[str] = []
    country_tails: list[str] = []
    for raw in parts:
        line = _prep_locality_line(raw)
        letters = re.sub(r"[^A-Za-z]", "", line)
        if len(letters) < 4:
            continue
        if (
            re.search(r"(?i)\bindia\b|\bT\.?\s*S\.?\b", line)
            and not _locality_signature(line)
            and len(line) <= 24
        ):
            if line.upper() not in {t.upper() for t in country_tails}:
                country_tails.append(line)
            continue
        if not _LOCALITY_MARK_RE.search(line) or not _locality_signature(line):
            continue
        if line.upper() not in {p.upper() for p in prepped}:
            prepped.append(line)
    if not _locality_parts_are_repeats(prepped):
        return None
    cluster = _largest_locality_cluster(prepped) or []
    best = _best_locality_line(cluster)
    if not best:
        return None
    return _attach_country_fragment(best, [*cluster, *country_tails])[:400]


def _line_is_notary_comment(line: str) -> bool:
    return bool(_NOTARY_COMMENT_RE.search(line or ""))


def _line_is_passport_payload(line: str) -> bool:
    """Passport label, MRZ, or passport-number line — not a stamp comment."""
    s = line or ""
    if _PASSPORT_PAYLOAD_RE.search(s):
        return True
    return bool(re.search(r"\b[A-Z]\d{7}\b", s.upper()))


def _stamp_place_signature(line: str) -> set[str]:
    out: set[str] = set()
    for tok in re.findall(r"[A-Za-z]{4,}", (line or "").lower()):
        if tok in _STAMP_GEO_GENERIC or tok in _LOCALITY_TOKEN_SKIP:
            continue
        out.add(tok)
    return out


def _is_stamp_country_tail(line: str) -> bool:
    """'T.S. INDIA' / 'State-INDIA' fragments that sit under a notary stamp."""
    words = re.findall(r"[A-Za-z]{2,}", line or "")
    if not words:
        return False
    distinctive = [
        w
        for w in words
        if len(w) >= 4 and w.lower() not in _STAMP_GEO_GENERIC and w.lower() not in _LOCALITY_TOKEN_SKIP
    ]
    if distinctive:
        return False
    return bool(re.search(r"(?i)\bindia\b|\bstate\b|\bT\.?\s*S\.?\b", line or ""))


def _follows_notary_stamp(lines: list[str], index: int) -> bool:
    """A town line sitting under a notary comment is a stamp, not an address."""
    prev = _previous_content_line(lines, index)
    if not prev or not _line_is_notary_comment(prev):
        return False
    line = lines[index]
    if _line_is_passport_payload(line) or _STREET_LINE_RE.search(line):
        return False
    if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", line):
        return False
    if re.search(r"(?i)\b(?:india|state|urban|district)\b", line):
        return True
    generic = {
        "advocate",
        "notary",
        "netary",
        "attorney",
        "attested",
        "attest",
        "certified",
        "stamp",
        "duty",
        "true",
        "copy",
        "verified",
    }
    prev_toks = {
        tok.lower()
        for tok in re.findall(r"[A-Za-z]{5,}", prev)
        if tok.lower() not in generic
    }
    line_toks = {tok.lower() for tok in re.findall(r"[A-Za-z]{5,}", line)}
    return bool(prev_toks & line_toks)


def _previous_content_line(lines: list[str], index: int) -> str:
    j = index - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    return lines[j] if j >= 0 else ""


def _stamp_locality_indexes(lines: list[str]) -> set[int]:
    """Indexes of near-duplicate stamp places, when notary comments are present.

    A residential line (street, door, PIN) and the value under a passport label
    are not part of the stamp cluster.
    """
    idxs: list[int] = []
    sigs: list[set[str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or _line_is_notary_comment(s) or _line_is_passport_payload(s):
            continue
        if _STREET_LINE_RE.search(s):
            continue
        if _PASSPORT_LABEL_LINE_RE.search(_previous_content_line(lines, i)):
            continue
        sig = _stamp_place_signature(s)
        if not sig:
            continue
        if not (
            _LOCALITY_MARK_RE.search(s)
            or re.search(r"(?i)\bindia\b|\bstate\b|\burban\b", s)
        ):
            continue
        idxs.append(i)
        sigs.append(sig)
    n = len(idxs)
    if n < 3:
        return set()
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            if _locality_token_overlap(sigs[i], sigs[j]) >= 0.5:
                union(i, j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    ranked = sorted(groups.values(), key=len, reverse=True)
    largest = ranked[0]
    second = len(ranked[1]) if len(ranked) > 1 else 0
    if len(largest) < 3 or len(largest) <= second:
        return set()
    return {idxs[i] for i in largest}


def _repeated_stamp_signatures(text: str | None) -> list[set[str]]:
    """Distinctive tokens of a town the notary stamp repeats."""
    lines = (text or "").splitlines()
    if not lines or not any(_line_is_notary_comment(ln) for ln in lines):
        return []
    sigs: list[set[str]] = []
    for i in _stamp_locality_indexes(lines):
        sig = _stamp_place_signature(lines[i])
        if sig:
            sigs.append(sig)
    return sigs


def _line_matches_stamp_locality(line: str, signatures: list[set[str]]) -> bool:
    """True when a fragment is a repeated stamp town, not a residential line."""
    if not signatures:
        return False
    if re.search(
        r"(?i)\b(?:house|village|mandal|pin|road|street|lane|nagar|colony|"
        r"block|flat|room|door|number)\b",
        line or "",
    ):
        return False
    if re.search(r"\d", line or ""):
        return False
    sig = _stamp_place_signature(line)
    if not sig:
        return False
    return any(_locality_token_overlap(sig, other) >= 0.5 for other in signatures)


def _strip_stamp_locality_tail(address: str | None, text: str | None) -> str | None:
    """Drop a notary-town suffix glued after the real residential lines."""
    raw = str(address or "").strip()
    if not raw:
        return None
    signatures = _repeated_stamp_signatures(text)
    if not signatures:
        return raw
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    while parts and _line_matches_stamp_locality(parts[-1], signatures):
        parts.pop()
    if not parts:
        return None
    return ", ".join(parts)[:400]


_NOTARY_NAME_SKIP = _LOCALITY_TOKEN_SKIP | frozenset(
    {
        "advocate",
        "notarial",
        "attorney",
        "attested",
        "attest",
        "certified",
        "copy",
        "true",
        "stamp",
        "duty",
        "solemnly",
        "verified",
        "verification",
        "ballm",
        "allm",
    }
)


def _notary_neighbor_tokens(lines: list[str]) -> set[str]:
    """Person-like tokens that sit on or beside an advocate / notary comment."""
    bad: set[str] = set()
    for i, line in enumerate(lines):
        window = lines[max(0, i - 2) : i + 3]
        if not any(_line_is_notary_comment(part) for part in window):
            continue
        for tok in re.findall(r"[A-Za-z]{4,}", line or ""):
            low = tok.lower()
            if low in _NOTARY_NAME_SKIP or low in _STAMP_GEO_GENERIC:
                continue
            bad.add(low)
    return bad


def _name_is_notary_neighbor(name: str | None, lines: list[str]) -> bool:
    """True when a 'name' is a garbled attestor (B. BHAVANY → B Bhaoay), not a relative."""
    parts = re.findall(r"[A-Za-z]{4,}", str(name or "").lower())
    if not parts:
        return False
    stamps = _notary_neighbor_tokens(lines)
    if not stamps:
        return False
    for part in parts:
        for stamp in stamps:
            if part == stamp or SequenceMatcher(None, part, stamp).ratio() >= 0.72:
                return True
    return False


def _passport_number_or_mrz_fragment(line: str) -> str:
    """Keep a passport number or MRZ token that OCR glued onto a comment line."""
    bits: list[str] = []
    mrz = re.search(r"P\s*<[A-Z0-9< ]{8,}", line or "", re.I)
    if mrz:
        bits.append(re.sub(r"\s+", "", mrz.group(0).upper()))
    for tok in re.findall(r"\b[A-Z]\d{7}\b", (line or "").upper()):
        if tok not in bits:
            bits.append(tok)
    return " ".join(bits)


def strip_non_passport_comments(text: str | None) -> str:
    """Drop notary, attestation, and true-copy lines before field assignment.

    Passport labels, MRZ, passport numbers, and residential lines stay.
    A town repeated only inside the stamp is dropped with the comments.
    When the page has no comment boilerplate, the text is unchanged.
    """
    raw = text or ""
    lines = raw.splitlines()
    if not lines or not any(_line_is_notary_comment(ln) for ln in lines):
        return raw
    drop_locality = _stamp_locality_indexes(lines)
    kept: list[str] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            kept.append(ln)
            continue
        comment = _line_is_notary_comment(s)
        if comment and not _line_is_passport_payload(s):
            fragment = _passport_number_or_mrz_fragment(s)
            if fragment:
                kept.append(fragment)
            continue
        if comment and _line_is_passport_payload(s):
            kept.append(ln)
            continue
        if (
            i in drop_locality
            or _follows_notary_stamp(lines, i)
            or (
                _is_stamp_country_tail(s)
                and not _line_is_passport_payload(s)
                and not _STREET_LINE_RE.search(s)
                and not _PASSPORT_LABEL_LINE_RE.search(_previous_content_line(lines, i))
            )
        ):
            continue
        kept.append(ln)
    return "\n".join(kept)


def _passport_signal_count(text: str | None) -> int:
    """How many independent passport cues are in ``text``. MRZ alone counts as enough."""
    raw = text or ""
    compact = re.sub(r"\s+", "", raw)
    if re.search(r"P<[A-Z0-9<]{3}", compact, re.I):
        return 2
    n = 0
    if re.search(r"\b(?:PASSPORT|PASSEPORT)\b", raw, re.I):
        n += 1
    if re.search(r"\bREPUBLIC\s+OF\s+[A-Z]", raw, re.I):
        n += 1
    if re.search(r"\b(?:SURNAME|GIVEN\s+NAMES?)\b", raw, re.I):
        n += 1
    if re.search(r"\bDATE\s+OF\s+BIRTH\b", raw, re.I):
        n += 1
    if re.search(r"\b[A-Z]\d{7}\b", raw.upper()):
        n += 1
    if re.search(
        r"\b(?:DATE\s+OF\s+(?:ISSUE|EXPIRY)|NATIONALITY|PLACE\s+OF\s+BIRTH)\b",
        raw,
        re.I,
    ):
        n += 1
    return n


def text_has_enough_passport_evidence(text: str | None) -> bool:
    """True when the page is still a passport after comment lines are ignored.

    Notary or attestation text does not cancel MRZ, a passport number together
    with a passport label, or the usual biodata headings. A stamp locality
    and a bare passport number are not enough on their own.
    """
    raw = text or ""
    if _passport_signal_count(raw) >= 2:
        return True
    stripped = strip_non_passport_comments(raw)
    if stripped != raw and _passport_signal_count(stripped) >= 2:
        return True
    return False


def _filter_ocr_blocks_after_comment_strip(
    blocks: list[dict[str, Any]] | None,
    original_text: str,
    stripped_text: str,
) -> list[dict[str, Any]] | None:
    """Drop OCR boxes whose lines were removed as notary or stamp comments.

    Boxes that never appeared as their own line in the page text are kept.
    A split name box (``JOSEPHINE`` beside ``ANUNCIA``) is not a comment line.
    """
    if not blocks:
        return blocks

    def norm(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip().upper()

    kept = {norm(ln) for ln in (stripped_text or "").splitlines() if ln.strip()}
    dropped = {
        norm(ln)
        for ln in (original_text or "").splitlines()
        if ln.strip() and norm(ln) not in kept
    }
    if not dropped:
        return blocks
    out: list[dict[str, Any]] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        text = str(
            blk.get("cleaned_text") or blk.get("text") or blk.get("raw_ocr_text") or ""
        ).strip()
        if not text:
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()] or [text]
        surviving = [ln for ln in lines if norm(ln) not in dropped]
        if not surviving:
            continue
        if len(surviving) == len(lines):
            out.append(blk)
            continue
        copied = dict(blk)
        joined = "\n".join(surviving)
        copied["cleaned_text"] = joined
        if "text" in copied:
            copied["text"] = joined
        out.append(copied)
    return out


def _value_grounded_in_text(
    value: str,
    text: str,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """True when a free-text value still appears on the page after comments are removed.

    Spatial OCR boxes count. A stamp town that was stripped out of both the
    page text and its boxes does not.
    """
    blob = text or ""
    for blk in ocr_blocks or []:
        if not isinstance(blk, dict):
            continue
        blob += "\n" + str(
            blk.get("cleaned_text") or blk.get("text") or blk.get("raw_ocr_text") or ""
        )
    tokens = [
        tok
        for tok in re.findall(r"[A-Za-z]{4,}", (value or "").lower())
        if tok not in _STAMP_GEO_GENERIC and tok not in _LOCALITY_TOKEN_SKIP
    ]
    if not tokens:
        digits = re.findall(r"\d{3,}", value or "")
        return any(d in blob for d in digits) if digits else True
    blob_l = blob.lower()
    return any(tok in blob_l for tok in tokens)


def _tidy_passport_address(val: str | None) -> str | None:
    """Keep street lines; drop dates, names, and visa crumbs glued into address."""
    raw = _strip_address_header_prefix(str(val or ""))
    if not raw:
        return None
    collapsed = _collapse_repeated_locality_parts(re.split(r"[\n,]+", raw))
    if collapsed:
        # A repeated town/state line is a notary stamp, not the holder's address.
        # A repeated street (road, door, PIN) is still the residential address.
        if _STREET_LINE_RE.search(collapsed):
            sanitized = _sanitize_passport_address(collapsed)
            if sanitized:
                return sanitized
            if _address_is_administrative_noise(collapsed):
                return None
            return collapsed
        return None
    # Door numbers such as 12-1-47/1 share a date shape. Keep them when a slash
    # tail shows they are a street token, not a glued issue date.
    raw = re.sub(r"\s+\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b(?!/\d)", " ", raw)
    parts = re.split(
        r"(?i)\b(?:name\s*(?:of|ot)\s*(?:spouse|father|mother)|visa)\b|\s*\|\s*",
        raw,
    )
    kept: list[str] = []
    for part in parts:
        piece = re.sub(r"\s+", " ", part).strip(" ,;|")
        if not piece or len(piece) < 8:
            continue
        if re.search(r"(?i)\b(?:spouse|father|mother|guardian)\b", piece):
            continue
        if re.search(r"\b\d{7,}\b", piece) and not re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", piece):
            piece = re.sub(r"\b\d{7,}\b", " ", piece)
            piece = re.sub(r"\s+", " ", piece).strip(" ,")
        if re.fullmatch(r"[A-Za-z]{3,24}", piece):
            continue
        looks_street = bool(
            re.search(
                r"(?i)\b(?:road|street|nagar|colony|block|flat|room|lane|society|"
                r"pin\s*:?\s*\d{6}|h\s*no|no\s*:|house\s*(?:no\.?|number)|"
                r"village|mandal)\b|\d{1,4}\s*-\s*\d{1,4}",
                piece,
            )
        )
        looks_locality = bool(
            re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,40}, [A-Za-z][A-Za-z .'-]{2,30}", piece)
        )
        if not looks_street and not looks_locality:
            continue
        if piece.upper() not in {p.upper() for p in kept}:
            kept.append(piece)
    joined = normalize_multiline_address(", ".join(kept)[:400]) if kept else None
    if not joined:
        return _sanitize_passport_address(raw)
    parts = [re.sub(r"\s+", " ", p).strip() for p in joined.split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for i, part in enumerate(parts):
        key = part.upper()
        if not key or key in seen:
            continue
        if re.fullmatch(r"\d{1,3}", key):
            nxt = parts[i + 1] if i + 1 < len(parts) else ""
            if not re.search(r"(?i)\b(?:road|street|nagar|lane|colony)\b", nxt):
                continue
        seen.add(key)
        deduped.append(part)
    i = 1
    while i < len(deduped) - 1:
        city = deduped[i]
        prev = deduped[i - 1]
        nxt = deduped[i + 1]
        if (
            re.fullmatch(r"[A-Za-z]{4,20}", city)
            and re.search(r"(?i)\b(?:road|street|nagar|lane)\b", prev)
            and " " in nxt
            and not re.search(
                r"(?i)(?:\b(?:road|street|nagar|lane|pin|taluk|urban|rural|district)\b|\(po\))",
                nxt,
            )
        ):
            deduped[i], deduped[i + 1] = nxt, city
        i += 1
    final = ", ".join(deduped)[:400] or None
    if final and _address_is_administrative_noise(final):
        return None
    return final


def _ocr_block_items(
    blocks: list[dict[str, Any]] | None,
) -> list[tuple[float, float, float, float, float, str]]:
    """Return sorted (page, cy, cx, width, height, text) items from OCR boxes."""
    items: list[tuple[float, float, float, float, float, str]] = []
    if not blocks:
        return items
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        text = str(
            blk.get("cleaned_text") or blk.get("text") or blk.get("raw_ocr_text") or ""
        ).strip()
        if not text:
            continue
        center = _box_center(blk.get("bounding_box"))
        if not center:
            continue
        try:
            page = int(
                blk.get("page_index")
                if blk.get("page_index") is not None
                else blk.get("page")
                or 0
            )
        except (TypeError, ValueError):
            page = 0
        box = blk.get("bounding_box")
        try:
            xs = [float(p[0]) for p in box[:4]]
            ys = [float(p[1]) for p in box[:4]]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
        except Exception:
            width, height = 40.0, 14.0
        items.append((float(page), center[1], center[0], width, height, text))
    items.sort(key=lambda t: (t[0], t[1], t[2]))
    return items


def _name_from_same_box(label_text: str, label_re: re.Pattern[str]) -> str | None:
    """Pull a person name that OCR glued onto the same label box."""
    remainder = label_re.sub(" ", label_text or "")
    remainder = re.sub(r"[/|:\-–—]+", " ", remainder)
    remainder = re.sub(
        r"(?i)\b(?:legal|lega[ls]?|guardian|guardlan|gusrdian|gurdian|curdian|lepai|name|of|ot|ol|"
        r"father|fother|foter|pathvet|mother|mather|mothor|spouse|spouce|fn|afy|faf|nere|anfyeow)\b",
        " ",
        remainder,
    )
    remainder = re.sub(r"\s+", " ", remainder).strip(" .")
    cleaned = _clean_person_name(remainder)
    if cleaned and _is_plausible_person_name(cleaned):
        return cleaned
    return None


def _value_near_label(
    items: list[tuple[float, float, float, float, float, str]],
    label_idx: int,
    *,
    is_value,
    stop_res: list[re.Pattern[str]] | None = None,
    directions: tuple[str, ...] = ("right", "below"),
) -> str | None:
    """Pick the best value near a label (anchor geometry).

    ``directions``: right / left / below / above. Rotated biodata scans often
    put values left-of or above labels (CamScanner: city above Place of Issue).
    Spouse should use ``directions=("below",)`` so mother/father names sitting
    above the Spouse label cannot leak in.
    """
    page0, y0, x0, w0, h0, _label = items[label_idx]
    row_tol = max(22.0, h0 * 2.2)
    below_max = max(110.0, h0 * 8.0)
    above_max = max(110.0, h0 * 8.0)
    side_max = max(320.0, w0 * 8.0)
    # Column alignment: keep below-values under this label, not the neighbour column.
    col_tol = max(90.0, w0 * 2.2)
    stop_res = stop_res or []
    allow_right = "right" in directions
    allow_left = "left" in directions
    allow_below = "below" in directions
    allow_above = "above" in directions
    best: tuple[float, str] | None = None

    for j, (page, cy, cx, _w, _h, text) in enumerate(items):
        if j == label_idx or page != page0:
            continue
        if any(rx.search(text) for rx in stop_res):
            continue
        if not is_value(text):
            continue
        dx = cx - x0
        dy = cy - y0
        score: float | None = None
        # Same-row side hits must not sit clearly above the label (prevents
        # mother-name → spouse when mother is above-right of the Spouse label).
        row_dy_ok = dy >= -max(12.0, h0 * 0.35)
        if allow_right and abs(dy) <= row_tol and 0 < dx <= side_max and row_dy_ok:
            score = abs(dy) * 2.0 + dx
        elif allow_left and abs(dy) <= row_tol and -side_max <= dx < 0 and row_dy_ok:
            score = abs(dy) * 2.0 + abs(dx)
        elif allow_below and 0 < dy <= below_max and abs(dx) <= col_tol:
            # Higher base than side hits so left/right same-row values win when
            # both exist (avoids Place-of-Issue picking the Birth city below).
            score = 200.0 + dy + abs(dx) * 0.5
        elif allow_above and 0 < -dy <= above_max and abs(dx) <= col_tol:
            # City often sits just above Place of Issue when OCR stacks
            # Date-of-Issue / CITY / Place-of-Issue / birth-city.
            score = 200.0 + abs(dy) + abs(dx) * 0.5
        if score is None:
            continue
        if best is None or score < best[0]:
            best = (score, text)
    if best:
        return best[1]
    return None


# OCR often turns Issue → lssue / lssuo / tssuo; do not require the leading "i".
# Trailing e-acute is the same word when the last letter is accented.
_PLACE_OF_ISSUE_OCR = (
    r"(?:l?issue|lssue|lssuo|lssve|issuc|issuance|issu|sue|tssue|tssuo|tssve|"
    r"tsue|ssue|lasue|lesue|tssu[eé]|ssu[eé])"
)
# "Place" often OCRs as Pace / Puce / Piace / Pteca, and "of issue" glues to "ofsue".
_PLACE_WORD_OCR = r"(?:place|pace|puce|piace|pteca)"
# "of" often OCRs as ot / gf / af (Place gf Birth).
_PLACE_OF_CONNECTOR_OCR = r"(?:o[ft]|gf|af|0f)"
# OCR-tolerant: Birth → Blrth / Birih / Bith / Burt / Birt; "of" → "ot" / "gf".
_PLACE_OF_BIRTH_WORD_OCR = r"(?:birth|blrth|birih|bith|burth|burt|birt|bre)"
_PLACE_OF_BIRTH_LABEL_RE = re.compile(
    rf"(?i)\b{_PLACE_WORD_OCR}\s*{_PLACE_OF_CONNECTOR_OCR}\s*{_PLACE_OF_BIRTH_WORD_OCR}\b"
)
_PLACE_OF_ISSUE_LABEL_RE = re.compile(
    rf"(?i)\b{_PLACE_WORD_OCR}\s*o[ft][.\s]*{_PLACE_OF_ISSUE_OCR}"
)
# Page-2 stamp line embeds "Place of Issue" but is not the biodata office label.
_OLD_PASSPORT_PLACE_OF_ISSUE_RE = re.compile(
    rf"(?i)old\s*passport[^\n]{{0,80}}place\s*of[.\s]*{_PLACE_OF_ISSUE_OCR}"
)
_DATE_OF_BIRTH_LABEL_RE = re.compile(
    r"(?i)(?:\bdate\s*of\s*birth\b|\bdob\b|wferfer\s*/\s*date\s*of\s*birth)"
)
_DATE_OF_ISSUE_LABEL_RE = re.compile(
    rf"(?i)\bdate\s*of\s*{_PLACE_OF_ISSUE_OCR}"
)
# OCR often mangles Address (Addiese / Adrhess / Adress) and bilingual crumbs.
_ADDRESS_LABEL_RE = re.compile(
    r"(?i)\b(?:address|addrese|addiese|adrhess|adress|addres|adres|"
    r"denl\s*/\s*add\w*|qa\s*/\s*add\w*|qm\s*/\s*add\w*|"
    r"ift.?l?\s*/\s*adrhess)\b"
)

# High RapidFuzz bar so "Piace of ssue" / "Date of issse" match, and
# "Place of Birth" does not win the place-of-issue slot.
_ISSUE_LABEL_FUZZY_THRESHOLD = 85

_ADDRESS_MAJOR_STOP_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:name\s+of|file\s*(?:no\.?|number)|fileno|old\s+passport|"
    r"place\s+of|date\s+of|surname|given\s+names?|nationality|"
    r"father|mother|spouse|legal\s+guardian|passport\s+no)\b"
    r")"
)
# Leftmost पता / Address label, including a trailing letter glued on (Addresse)
# and bilingual crumbs (qa / Address). The value starts after this match.
_ADDRESS_VALUE_ANCHOR_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:addresse|address|addiese|adrhess|addrese|adress|addres|adres)\b"
    r"|(?:denl|qan|qa|qm|went)\s*/\s*add\w*"
    r"|ift.?l?\s*/\s*adrhess"
    r"|(?:पता|पत्ता)"
    r")"
)
# Header noise only at the absolute start: "e, Address,", "पता / Address", OCR
# variants of Address. A street already starting at "D.NO:" or "12-1-47/1" does
# not match. Address / पता later in the line are left alone.
_ADDRESS_HEADER_PREFIX_RE = re.compile(
    r"^(?:"
    r"[\s,;:/|–—.\-]*"
    r"(?:"
    r"[A-Za-z]\s*,\s*"
    r"|(?:qan|denl|qa|qm|den|went)\s*/\s*"
    r")?"
    r"(?:"
    r"addresse|address|addiese|adrhess|addrese|adress|addres|adres|पता|पत्ता"
    r")"
    r"(?![A-Za-z\u0900-\u097F])"
    r"[\s,;:/|–—.\-]*"
    r")+",
    re.IGNORECASE,
)
_STREET_VALUE_START_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:d\.?\s*no|h\.?\s*no|door|flat|house|room|block|plot|lane|road|street|nagar)\b"
    r"|\d{1,5}\s*[-/]\s*\d"
    r"|^\d{1,6}\b"
    r")"
)


def _issue_label_scores(line: str) -> dict[str, float]:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return {}
    norm = re.sub(r"[^a-z0-9]+", " ", (line or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if len(re.sub(r"[^a-z]", "", norm)) < 8:
        return {}
    phrases = {
        "place_of_issue": "place of issue",
        "date_of_issue": "date of issue",
        "place_of_birth": "place of birth",
    }
    return {key: float(fuzz.WRatio(norm, phrase)) for key, phrase in phrases.items()}


def _fuzzy_issue_label_kind(line: str) -> str | None:
    scores = _issue_label_scores(line)
    if not scores:
        return None
    best = max(scores, key=lambda key: scores[key])
    if scores[best] < _ISSUE_LABEL_FUZZY_THRESHOLD:
        return None
    for other, score in scores.items():
        if other != best and score >= scores[best]:
            return None
    return best


def _line_is_mrz_boundary(line: str) -> bool:
    norm = _normalize_mrz_candidate(line or "")
    if len(norm) < 20:
        return False
    return _looks_like_td3_line1(norm) or _looks_like_td3_line2(norm)


def _anchor_tail_after_issue_label(line: str) -> str:
    tail = re.sub(
        r"(?i)^.*\b(?:issue|lssue|issse|issuc|lssuo|ssue|birth|blrth|birih|bith)\b",
        "",
        line or "",
    )
    tail = re.sub(r"^[\s.:/\-–—]+", "", tail).strip()
    if tail and _fuzzy_issue_label_kind(tail):
        return ""
    return tail


def _values_from_fuzzy_issue_labels(text: str | None) -> dict[str, str]:
    """Place/date of issue (and birth) from a fuzzy label plus value grammar."""
    found: dict[str, str] = {}
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        if _OLD_PASSPORT_PLACE_OF_ISSUE_RE.search(line) or _line_is_notary_comment(line):
            continue
        kind = _fuzzy_issue_label_kind(line)
        if kind not in {"place_of_issue", "date_of_issue", "place_of_birth"}:
            continue
        if found.get(kind):
            continue
        candidates: list[str] = []
        tail = _anchor_tail_after_issue_label(line)
        if tail:
            candidates.append(tail)
        for nxt in lines[index + 1 : index + 3]:
            piece = nxt.strip()
            if not piece:
                continue
            if (
                _line_is_notary_comment(piece)
                or _line_is_mrz_boundary(piece)
                or _fuzzy_issue_label_kind(piece)
                or _PLACE_OF_BIRTH_LABEL_RE.search(piece)
                or _PLACE_OF_ISSUE_LABEL_RE.search(piece)
                or _DATE_OF_ISSUE_LABEL_RE.search(piece)
                or _ADDRESS_LABEL_RE.search(piece)
            ):
                break
            candidates.append(piece)
            break
        for cand in candidates:
            if kind == "date_of_issue":
                iso = _parse_flexible_date(cand)
                if not iso:
                    dm = re.search(r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}", cand)
                    iso = _parse_flexible_date(dm.group(0) if dm else None)
                if iso:
                    found[kind] = iso
                    break
            elif kind == "place_of_issue":
                token = _normalize_place_token(cand)
                if token and _is_issuing_office_candidate(token):
                    found[kind] = token[:80]
                    break
            else:
                token = _split_glued_city_state(_normalize_place_token(cand))
                if (
                    token
                    and not _place_value_is_label_junk(token)
                    and _is_place_candidate(token)
                ):
                    found[kind] = token[:80]
                    break
    return found


def _is_address_line_candidate(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) < 6:
        return False
    if _looks_like_date_value(t):
        return False
    if re.match(
        r"(?i)^(place of|date of|name of|file|fileno|passport|nationality|sex)\b",
        t,
    ):
        return False
    return bool(
        re.search(
            r"(?i)(?:room|h\.?\s*no|d\.?\s*no|door|flat|house|block|lane|"
            r"complex|apartment|colony|society|nagar|road|street|pin\b|,|\d)",
            t,
        )
    )


_ADDRESS_STREET_FULL_RE = re.compile(
    r"(?i)\b(?:BLOCK|H\.?\s*NO\.?|D\.?\s*NO\.?|ROOM|FLAT)\s*"
    r"[A-Z0-9][A-Z0-9 ,./\-]{6,}"
)
_ADDRESS_STREET_CRUMB_RE = re.compile(
    r"(?i)^(BLOK|BLOCK)\s*[A-Z]?\s*(OAD|ROAD)?$"
)


def _prefer_full_address_lines(lines: list[str]) -> list[str]:
    """Drop truncated OCR crumbs when a fuller street line is present.

    RapidOCR sometimes emits both ``BLOK A OAD`` and the real
    ``BLOCK 3/C1, JAINS GREEN ACRES. 91 DARGA ROAD`` — keep the full line.
    """
    if not lines:
        return lines
    cleaned = [re.sub(r"\s+", " ", (ln or "").strip(" ,")) for ln in lines]
    cleaned = [ln for ln in cleaned if ln]
    has_full = any(_ADDRESS_STREET_FULL_RE.search(ln) and len(ln) >= 20 for ln in cleaned)
    if not has_full:
        return cleaned
    out: list[str] = []
    for ln in cleaned:
        if _ADDRESS_STREET_CRUMB_RE.match(ln) or (
            re.search(r"(?i)\bblok\b", ln) and len(ln) < 16
        ):
            continue
        out.append(ln)
    return out or cleaned


_LEADING_NATIONALITY_GLUE_RE = re.compile(
    r"^(?P<glue>[A-Za-z]{2,4}\s*/\s*INDIAN)\b[\s,;:/|.\-]*",
    re.IGNORECASE,
)
_LEADING_BIRTH_LABEL_FRAGMENT_RE = re.compile(
    rf"^(?:{_PLACE_WORD_OCR})\s+{_PLACE_OF_CONNECTOR_OCR}\s+"
    rf"{_PLACE_OF_BIRTH_WORD_OCR}\b[\s,;:/|.\-]*",
    re.IGNORECASE,
)


def _strip_leading_address_noise(raw: str) -> str:
    """Drop a junk header only at the absolute start of an address.

    ``NTR/INDIAN`` and a following ``Place gf Birth`` fragment are header noise.
    A street that does not start with that noise is unchanged.
    """
    s = raw
    changed = False
    glue = _LEADING_NATIONALITY_GLUE_RE.match(s)
    if glue:
        s = s[glue.end() :]
        changed = True
        s = re.sub(r"^[\s,;:/|.\-]+", "", s)
        s = re.sub(
            r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b(?!/\d)[\s,;]*",
            "",
            s,
        )
        s = re.sub(r"^[\s,;:/|.\-]+", "", s)
    birth = _LEADING_BIRTH_LABEL_FRAGMENT_RE.match(s)
    if birth:
        s = s[birth.end() :]
        changed = True
    if not changed:
        return raw
    return re.sub(r"^[\s,;:/|–—.\-]+", "", s)


def _strip_address_header_prefix(raw: str | None) -> str:
    """Drop Address / पता label noise only from the start of an address string."""
    s = str(raw or "").strip()
    if not s:
        return ""
    cleaned = _ADDRESS_HEADER_PREFIX_RE.sub("", s)
    cleaned = _strip_leading_address_noise(cleaned)
    if cleaned == s:
        return s
    cleaned = re.sub(r"^[\s,;:/|–—.\-]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" ,;")


def _line_has_address_anchor(line: str) -> bool:
    text = line or ""
    return bool(
        _ADDRESS_VALUE_ANCHOR_RE.search(text)
        or _ADDRESS_LABEL_RE.search(text)
        or block_is_field_label(text, "address")
    )


def _street_value_starts(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # A leading issue date is not a door. 12-1-47/1 stays (slash tail).
    if re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b(?!/\d)", t):
        return False
    return bool(_STREET_VALUE_START_RE.search(t))


def _text_after_address_anchor(line: str) -> str:
    """Text strictly after पता / Address and its immediate punctuation."""
    match = _ADDRESS_VALUE_ANCHOR_RE.search(line or "")
    if not match:
        return ""
    tail = (line or "")[match.end() :]
    tail = re.sub(r"^[\s,;:/|–—.\-]+", "", tail)
    tail = re.sub(r"(?i)\b(?:qan|denl|qa|den|went|qm)\b", " ", tail)
    tail = re.sub(r"^[\s,;:/|–—.\-]+", "", tail)
    tail = _strip_address_header_prefix(tail)
    return re.sub(r"\s+", " ", tail).strip(" ,;")


def _address_block_pre_street(piece: str) -> str | None:
    """Street text after a leading label fragment, or None while still pre-street.

    Field labels and OCR crumbs between the anchor and the door line are not
    part of the address. A line that is only ``e, Address,`` is skipped; the
    same line with a street after that fragment starts at the street.
    """
    text = re.sub(r"\s+", " ", (piece or "").strip())
    if not text or _line_is_notary_comment(text) or _line_is_mrz_boundary(text):
        return None
    stripped = _strip_address_header_prefix(text)
    # A date glued ahead of the door is label-adjacent noise, not the street.
    stripped = re.sub(
        r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\b(?!/\d)\s*,?\s*",
        "",
        stripped,
    ).strip(" ,;")
    if not stripped or _looks_like_file_number_token(stripped):
        return None
    # Door tokens (D.NO, 12-1-47/1) and ordinary street lines (complex, nagar).
    # Labels and short OCR crumbs stay skipped until that line appears.
    if _street_value_starts(stripped) or _is_address_line_candidate(stripped):
        return stripped
    return None


def _address_from_ocr_text(raw: str) -> str | None:
    """Consume address lines in order from the address label until the next stop.

    The street starts strictly after पता / Address. Intermediate labels and
    OCR noise before that street are skipped. Line 1 of the street is kept.
    A notary tail is dropped. The next major label or an MRZ line ends the block.
    """
    lines_in = (raw or "").splitlines()
    start = None
    for index, line in enumerate(lines_in):
        if _line_has_address_anchor(line):
            start = index
            break
    if start is None:
        return None
    collected: list[str] = []
    tail = _text_after_address_anchor(lines_in[start])
    if tail:
        started = _address_block_pre_street(tail)
        if started:
            collected.append(started)
    for line in lines_in[start + 1 :]:
        piece = line.strip()
        if not piece:
            continue
        if _line_is_mrz_boundary(piece):
            break
        if not collected:
            if _line_is_notary_comment(piece):
                continue
            started = _address_block_pre_street(piece)
            if started:
                collected.append(started)
            continue
        if _line_is_notary_comment(piece):
            break
        if _ADDRESS_MAJOR_STOP_RE.search(piece) or _FILE_LABEL_FUZZY_RE.search(piece):
            break
        if block_is_field_label(piece, "file_number") or block_is_field_label(
            piece, "father_name"
        ):
            break
        collected.append(piece)
        if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", piece):
            break
    while collected and _line_is_notary_comment(collected[-1]):
        collected.pop()
    collected = _prefer_full_address_lines(collected)
    joined = normalize_multiline_address("\n".join(collected)[:400])
    if joined and len(joined) >= 12:
        return joined
    return None


def _address_is_residential(val: str | None) -> bool:
    return bool(
        re.search(
            r"(?i)\b(?:pin\s*:?\s*\d{6}|house|village|mandal|road|street|nagar|"
            r"block|flat|room|lane|colony|h\.?\s*no|d\.?\s*no)\b|\d{1,4}\s*-\s*\d",
            val or "",
        )
    )


def _address_from_reading_order(
    blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Address lines after the Address label in OCR reading order.

    Rotated pages put the street lines "above" the label in image y, so a
    center-y "below" search drops line 1. Reading order still has
    Address, street, locality, PIN.
    """
    if not blocks:
        return None
    rows: list[tuple[int, int, int, str]] = []
    for idx, blk in enumerate(blocks):
        if not isinstance(blk, dict):
            continue
        text = _block_text(blk)
        if not text:
            continue
        try:
            page = int(
                blk.get("page_index")
                if blk.get("page_index") is not None
                else blk.get("page")
                or 0
            )
        except (TypeError, ValueError):
            page = 0
        raw_order = blk.get("reading_order_index")
        if raw_order is None:
            raw_order = blk.get("order")
        try:
            order = int(raw_order) if raw_order is not None else idx
        except (TypeError, ValueError):
            order = idx
        rows.append((page, order, idx, text))
    by_page: dict[int, list[tuple[int, int, str]]] = {}
    for page, order, idx, text in rows:
        by_page.setdefault(page, []).append((order, idx, text))
    for page_rows in by_page.values():
        page_rows.sort(key=lambda item: (item[0], item[1]))
        texts = [text for _, _, text in page_rows]
        stamp_sigs = _repeated_stamp_signatures("\n".join(texts))
        for i, text in enumerate(texts):
            if not _line_has_address_anchor(text):
                continue
            lines: list[str] = []
            remainder = _text_after_address_anchor(text)
            started = _address_block_pre_street(remainder) if remainder else None
            if started:
                lines.append(started)
            for nxt in texts[i + 1 :]:
                piece = nxt.strip()
                if not piece:
                    continue
                if _line_matches_stamp_locality(piece, stamp_sigs):
                    continue
                if _line_is_mrz_boundary(piece):
                    break
                if not lines:
                    if _line_is_notary_comment(piece):
                        continue
                    started = _address_block_pre_street(piece)
                    if started:
                        lines.append(started)
                    continue
                if _line_is_notary_comment(piece):
                    break
                if (
                    _ADDRESS_MAJOR_STOP_RE.search(piece)
                    or _FILE_LABEL_FUZZY_RE.search(piece)
                    or re.match(
                        r"(?i)^(old passport|name of|file|fileno|passport|fke|a3\s*/)",
                        piece,
                    )
                ):
                    break
                if _looks_like_file_number_token(piece):
                    break
                lines.append(piece)
                if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", piece):
                    break
            lines = _prefer_full_address_lines(lines)
            joined = normalize_multiline_address("\n".join(lines)[:400])
            if joined and len(joined) >= 12 and _address_is_residential(joined):
                return joined
    return None


def _address_from_ocr_blocks(blocks: list[dict[str, Any]] | None) -> str | None:
    """Residential address under the Address label (page-2 / dual-page scans).

    Long address lines have a right-shifted *center* even when left-aligned with
    the Address header. Scoring by center-x then picks line 2 as “below” and
    drops line 1. Collect by left-edge alignment instead. Rotated scans use
    reading order so the first street line is not treated as above the label.
    """
    ordered = _address_from_reading_order(blocks)
    if ordered:
        return ordered
    items = _ocr_block_items(blocks)
    if not items:
        return None
    stop = [
        _FATHER_LABEL_FUZZY_RE,
        _MOTHER_LABEL_FUZZY_RE,
        _SPOUSE_LABEL_FUZZY_RE,
        _FILE_LABEL_FUZZY_RE,
        re.compile(r"(?i)\b(?:old\s*passport|place\s*of|date\s*of|surname|given)\b"),
    ]

    for i, (page0, y0, x0, w0, _h0, text) in enumerate(items):
        if not _line_has_address_anchor(text):
            continue
        label_left = x0 - (w0 / 2.0)
        lines: list[str] = []
        remainder = _text_after_address_anchor(text)
        started = _address_block_pre_street(remainder) if remainder else None
        if started:
            lines.append(started)
        for page, cy, cx, w, _h, t2 in items:
            if page != page0 or t2 == text:
                continue
            if cy <= y0:
                continue
            left = cx - (w / 2.0)
            # Wide street lines share the label's left edge, not its center.
            if abs(left - label_left) > 180:
                continue
            if _line_is_mrz_boundary(t2):
                break
            if not lines:
                if _line_is_notary_comment(t2):
                    continue
                started = _address_block_pre_street(t2)
                if started:
                    lines.append(started)
                continue
            if _line_is_notary_comment(t2):
                break
            if any(rx.search(t2) for rx in stop):
                break
            lines.append(t2)
            if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", t2):
                break
        if not any(re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", ln) for ln in lines):
            for page, cy, cx, _w, _h, t2 in items:
                if page != page0 or cy < y0:
                    continue
                if re.search(r"(?i)\bPIN\s*:?\s*\d{6}\b", t2):
                    lines.append(t2.strip())
                    break
        lines = _prefer_full_address_lines(lines)
        joined = normalize_multiline_address("\n".join(lines)[:400])
        if joined and len(joined) >= 12 and _address_is_residential(joined):
            return joined
    return None


def _issue_expiry_dates_from_ocr_blocks(
    items: list[tuple[float, float, float, float, float, str]],
) -> dict[str, str]:
    """Resolve Date of Issue / Expiry when OCR merges both labels into one box.

    Indian biodata scans often OCR a single label strip
    ``Date of issue … Date of Expiry`` with the two dates sitting below-left
    and below-right. Picking the nearest date alone wrongly assigns expiry
    to ``date_of_issue``.

    Also handles the common CamScanner case where only ``Date of Issue`` is
    readable and the Expiry label is garbled, but both dates still sit on the
    same row under the dates band.
    """
    out: dict[str, str] = {}

    def _pair_dates(
        page0: float,
        y0: float,
        x0: float,
        w0: float,
        h0: float,
        *,
        require_wide_band: bool,
    ) -> dict[str, str]:
        below_max = max(160.0, h0 * 12.0)
        label_left = x0 - (w0 / 2.0)
        label_right = x0 + (w0 / 2.0)
        dates: list[tuple[float, float, str]] = []
        for j, (page, cy, cx, _w, _h, text) in enumerate(items):
            if page != page0:
                continue
            if cy < y0 - max(40.0, h0 * 2.5) or cy > y0 + below_max:
                continue
            if require_wide_band:
                if cx < label_left - 100 or cx > label_right + 220:
                    continue
            else:
                # Lone Issue label: still allow the right-hand expiry date.
                if cx < label_left - 80 or cx > label_right + 520:
                    continue
            if not _looks_like_date_value(text):
                continue
            iso = _parse_flexible_date(text.strip())
            if not iso:
                continue
            dates.append((cx, cy, iso))
        if not dates:
            return {}
        dates.sort(key=lambda t: (t[0], t[1]))
        uniq: list[tuple[float, str]] = []
        seen: set[str] = set()
        for cx, _cy, iso in dates:
            if iso in seen:
                continue
            seen.add(iso)
            uniq.append((cx, iso))
        if len(uniq) < 2:
            return {}
        from datetime import datetime as _dt

        def _pd(s: str):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return _dt.strptime(s[:10], fmt)
                except ValueError:
                    continue
            return None

        left, right = uniq[0][1], uniq[1][1]
        a, b = _pd(left), _pd(right)
        if a and b and a > b:
            left, right = right, left
        return {"date_of_issue": left, "date_of_expiry": right}

    for i, (page0, y0, x0, w0, h0, label) in enumerate(items):
        if not _DATE_OF_ISSUE_LABEL_RE.search(label):
            continue
        stacked = bool(re.search(r"(?i)expir", label))
        paired = _pair_dates(
            page0, y0, x0, w0, h0, require_wide_band=stacked
        )
        if paired:
            return paired
        # Stacked label with a single ambiguous date — leave for `_near` / MRZ.
        if stacked:
            return out
    return out


def _biodata_places_dates_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Place/date of birth/issue via box geometry (handles rotated biodata pages)."""
    items = _ocr_block_items(blocks)
    if not items:
        return {}
    out: dict[str, str] = {}
    # Infer holder identity from labeled surname/given blocks so place geometry
    # never latches onto the holder's own name (permanent, not city denylist).
    holder_surname: str | None = None
    holder_given: str | None = None
    for i, (*_, text) in enumerate(items):
        low = text.lower()
        if re.search(r"(?i)\bsurname\b|\bfamily\s*name\b", text) and i + 1 < len(items):
            nxt = items[i + 1][5]
            if _is_parent_name_candidate(nxt) or (
                re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", nxt or "")
                and "," not in (nxt or "")
            ):
                holder_surname = nxt.strip()
        if re.search(r"(?i)\bgiven\s*name", text) and i + 1 < len(items):
            nxt = items[i + 1][5]
            if nxt and not _is_noise_value(nxt) and not _NEXT_FIELD_LABEL_RE.match(nxt):
                holder_given = nxt.strip()

    def _place_ok(t: str) -> bool:
        return _is_place_candidate(
            t, surname=holder_surname, given_names=holder_given
        )

    def _issue_ok(t: str) -> bool:
        return _is_issuing_office_candidate(
            t, surname=holder_surname, given_names=holder_given
        )

    # Place of Birth: never search "above" — nationality (HA/INDIAN) sits there.
    # Place of Issue: keep "above" (CamScanner stacks CITY above that label).
    birth_dirs: tuple[str, ...] = ("left", "right", "below")
    issue_dirs: tuple[str, ...] = ("left", "right", "below", "above")
    date_dirs: tuple[str, ...] = ("left", "right", "below")
    stop = [
        _PLACE_OF_BIRTH_LABEL_RE,
        _PLACE_OF_ISSUE_LABEL_RE,
        _DATE_OF_BIRTH_LABEL_RE,
        _DATE_OF_ISSUE_LABEL_RE,
        re.compile(r"(?i)\b(?:surname|given\s*name|nationality|sex|passport)\b"),
    ]

    def _near(
        label_re: re.Pattern[str],
        is_value,
        *,
        directions: tuple[str, ...],
        skip_label=None,
    ) -> str | None:
        for i, (*_, text) in enumerate(items):
            if not label_re.search(text):
                continue
            if skip_label and skip_label.search(text):
                continue
            # Skip the stacked Issue+Expiry strip — handled by pairing helper.
            if label_re is _DATE_OF_ISSUE_LABEL_RE and re.search(
                r"(?i)expir", text
            ):
                continue
            raw = _value_near_label(
                items,
                i,
                is_value=is_value,
                directions=directions,
                stop_res=stop,
            )
            if raw:
                return _normalize_place_token(raw) if label_re in (
                    _PLACE_OF_BIRTH_LABEL_RE,
                    _PLACE_OF_ISSUE_LABEL_RE,
                ) else raw
        return None

    pob = _near(_PLACE_OF_BIRTH_LABEL_RE, _place_ok, directions=birth_dirs)
    if pob and not _is_nationality_as_place(pob):
        out["place_of_birth"] = pob.strip()[:80]
    poi = _near(
        _PLACE_OF_ISSUE_LABEL_RE,
        lambda t: _issue_ok(t)
        and _normalize_place_token(t).upper()
        != str(out.get("place_of_birth") or "").strip().upper(),
        directions=issue_dirs,
        skip_label=_OLD_PASSPORT_PLACE_OF_ISSUE_RE,
    )
    if poi:
        out["place_of_issue"] = poi.strip()[:80]

    dob = _near(
        _DATE_OF_BIRTH_LABEL_RE,
        _looks_like_date_value,
        directions=date_dirs,
    )
    if dob:
        iso = _parse_flexible_date(dob)
        if iso:
            out["date_of_birth"] = iso

    issue_exp = _issue_expiry_dates_from_ocr_blocks(items)
    out.update(issue_exp)
    if not out.get("date_of_issue"):
        doi = _near(
            _DATE_OF_ISSUE_LABEL_RE,
            _looks_like_date_value,
            directions=date_dirs,
        )
        if doi:
            iso = _parse_flexible_date(doi)
            if iso:
                out["date_of_issue"] = iso
    # Dedicated Date of Expiry label (when not stacked with Issue).
    if not out.get("date_of_expiry"):
        exp_re = re.compile(r"(?i)\bdate\s*of\s*expir")
        for i, (*_, text) in enumerate(items):
            if not exp_re.search(text):
                continue
            if _DATE_OF_ISSUE_LABEL_RE.search(text):
                continue  # stacked strip already handled
            raw = _value_near_label(
                items,
                i,
                is_value=_looks_like_date_value,
                directions=date_dirs,
                stop_res=stop,
            )
            if raw:
                iso = _parse_flexible_date(raw)
                if iso:
                    out["date_of_expiry"] = iso
                    break
    return out


def _nationality_candidate_text(text: str) -> str | None:
    """Strip label prefixes from an OCR block that may hold a nationality value."""
    t = (text or "").strip()
    if not t:
        return None
    # "Nationality / Nationalité INDIAN" or label-only blocks.
    if _NATIONALITY_LABEL_FUZZY_RE.fullmatch(t):
        return None
    if _NATIONALITY_LABEL_FUZZY_RE.search(t):
        t = _NATIONALITY_LABEL_FUZZY_RE.sub(" ", t)
        t = re.sub(r"[/|:\-–—]+", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
    return t or None


def _nationality_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
) -> tuple[str | None, str | None]:
    """Locate Nationality via relative proximity (right-of or below label).

    Layout-agnostic: works when nationality sits in a centre column or beside
    Sex / Date of Birth rather than at a fixed pixel offset.
    """
    if not blocks:
        return None, None

    items: list[tuple[float, float, float, float, float, str]] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        text = str(
            blk.get("cleaned_text") or blk.get("text") or blk.get("raw_ocr_text") or ""
        ).strip()
        if not text:
            continue
        center = _box_center(blk.get("bounding_box"))
        if not center:
            continue
        try:
            page = int(
                blk.get("page_index")
                if blk.get("page_index") is not None
                else blk.get("page")
                or 0
            )
        except (TypeError, ValueError):
            page = 0
        box = blk.get("bounding_box")
        try:
            xs = [float(p[0]) for p in box[:4]]
            ys = [float(p[1]) for p in box[:4]]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
        except Exception:
            width, height = 40.0, 14.0
        items.append((float(page), center[1], center[0], width, height, text))

    if not items:
        return None, None
    items.sort(key=lambda t: (t[0], t[1], t[2]))

    labels = [
        (i, page, cy, cx, w, h, text)
        for i, (page, cy, cx, w, h, text) in enumerate(items)
        if _NATIONALITY_LABEL_FUZZY_RE.search(text)
    ]
    if not labels:
        return None, None

    best: tuple[float, str, str | None] | None = None  # score, demonym, alpha3

    for _, page0, y0, x0, w0, h0, label_text in labels:
        # Same-box value after the label word.
        same = _nationality_candidate_text(label_text)
        if same:
            demonym, alpha = resolve_nationality(same)
            if demonym:
                return demonym, alpha

        row_tol = max(18.0, h0 * 1.8)
        below_max = max(55.0, h0 * 4.5)
        right_max = max(220.0, w0 * 6.0)

        for page, cy, cx, _w, _h, text in items:
            if page != page0:
                continue
            cand = _nationality_candidate_text(text)
            if not cand or cand == label_text.strip():
                continue
            if _NATIONALITY_LABEL_FUZZY_RE.search(cand) and len(cand.split()) <= 2:
                continue
            demonym, alpha = resolve_nationality(cand)
            if not demonym:
                continue

            dx = cx - x0
            dy = cy - y0
            # Prefer value immediately to the right on the same row.
            if abs(dy) <= row_tol and 0 < dx <= right_max:
                score = abs(dy) * 2.0 + dx
            # Else value stacked immediately below the anchor.
            elif 0 < dy <= below_max and abs(dx) <= max(120.0, w0 * 3.0):
                score = 80.0 + dy + abs(dx) * 0.5
            else:
                continue
            if best is None or score < best[0]:
                best = (score, demonym, alpha)

    if best:
        return best[1], best[2]
    return None, None


def _parent_names_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
) -> tuple[str | None, str | None]:
    """Father/mother names from page-2 OCR boxes (right-of or below anchors).

    CamScanner often garbles labels (Foter/Mather) while the name lines stay
    clean — match labels fuzzily, then take the nearest name candidate.
    """
    items = _ocr_block_items(blocks)
    if not items:
        return None, None

    father: str | None = None
    mother: str | None = None
    stop_common = [
        _FILE_LABEL_FUZZY_RE,
        _SPOUSE_LABEL_FUZZY_RE,
        re.compile(r"(?i)\b(?:address|old\s*passport|pin\b|room\b)\b"),
    ]

    def _pull_parent(field_key: str, regex, stop_res) -> str | None:
        idxs: list[int] = []
        fi = find_label_anchor_index(items, field_key)
        if fi is not None:
            idxs.append(fi)
        for i, (_, _, _, _, _, text) in enumerate(items):
            if i in idxs:
                continue
            if regex.search(text) or block_is_field_label(text, field_key):
                # Avoid father/mother cross-hit on shared guardian phrases.
                if field_key == "father_name" and _MOTHER_LABEL_FUZZY_RE.search(text):
                    continue
                idxs.append(i)
        for i in idxs:
            text = items[i][5]
            same = _name_from_same_box(text, regex) if regex.search(text) else None
            raw = _value_near_label(
                items,
                i,
                is_value=_is_parent_name_candidate,
                stop_res=stop_res,
            )
            near = _clean_person_name(raw) if raw else None
            if near and _is_plausible_person_name(near):
                return near
            if same and _is_plausible_person_name(same):
                return same
        # ROI is only for garbled-but-present labels on the same page as the
        # anchor. Fully unlabeled pages must fall through to the unlabeled
        # family-row path — not a mid-band name guess on the biodata page.
        if not idxs:
            return None
        for li in idxs:
            page = items[li][0]
            for cand in values_in_field_roi(
                items,
                field_key,
                is_value=_is_parent_name_candidate,
                page=page,
            ):
                cleaned = _clean_person_name(cand)
                if cleaned and _is_plausible_person_name(cleaned):
                    return cleaned
        return None

    father = _pull_parent(
        "father_name",
        _FATHER_LABEL_FUZZY_RE,
        [_MOTHER_LABEL_FUZZY_RE, *stop_common],
    )
    mother = _pull_parent(
        "mother_name",
        _MOTHER_LABEL_FUZZY_RE,
        [_FATHER_LABEL_FUZZY_RE, *stop_common],
    )

    # Fallback: left/right column split when stacked lookup missed one side.
    # Only fill a side that still has its own label on that page — never pull
    # biodata-page holder names (given/surname) into father when Father OCR is garbled.
    if not father or not mother:
        label_father = [
            (page, cx, cy)
            for page, cy, cx, _w, _h, text in items
            if _FATHER_LABEL_FUZZY_RE.search(text)
            and not _MOTHER_LABEL_FUZZY_RE.search(text)
        ]
        label_mother = [
            (page, cx, cy)
            for page, cy, cx, _w, _h, text in items
            if _MOTHER_LABEL_FUZZY_RE.search(text)
        ]
        label_pages = {p for p, _, _ in label_father} | {p for p, _, _ in label_mother}
        candidates = [
            (page, cx, cy, text)
            for page, cy, cx, _w, _h, text in items
            if page in label_pages and _is_parent_name_candidate(text)
        ]
        if candidates and (label_father or label_mother):
            split_x: float | None = None
            if label_father and label_mother:
                split_x = (
                    sum(x for _, x, _ in label_father) / len(label_father)
                    + sum(x for _, x, _ in label_mother) / len(label_mother)
                ) / 2.0
            y_floor = min(
                [y for _, _, y in label_father] + [y for _, _, y in label_mother],
                default=0.0,
            )
            left: list[tuple[float, str]] = []
            right: list[tuple[float, str]] = []
            for _page, cx, cy, text in candidates:
                if cy < y_floor - 5:
                    continue
                if split_x is None or cx <= split_x:
                    left.append((cy, text))
                else:
                    right.append((cy, text))
            left.sort(key=lambda t: t[0])
            right.sort(key=lambda t: t[0])
            if not father and label_father and left:
                father = _clean_person_name(left[0][1])
            if not mother and label_mother and right:
                mother = _clean_person_name(right[0][1])
            if (not father or not mother) and left and not right:
                left_names = [n for _, t in left if (n := _clean_person_name(t))]
                if not father and label_father and left_names:
                    father = left_names[0]
                if not mother and label_mother and len(left_names) > 1:
                    mother = left_names[1]
                elif not mother and label_mother and left_names and not label_father:
                    mother = left_names[0]

    if father and mother and father.upper() == mother.upper():
        return father, None
    return father, mother


def _block_text(blk: dict[str, Any]) -> str:
    return str(
        blk.get("text")
        or blk.get("raw_ocr_text")
        or blk.get("cleaned_text")
        or ""
    ).strip()


def _unlabeled_family_row_from_blocks(
    blocks: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Father / mother / spouse / address when CamScanner dropped the labels.

    Some booklet pages OCR as ``NAME junk NAME junk NAME`` plus address lines,
    with no "Name of Father" anchor. Reading order on that page is
    street, father, mother, spouse, locality, PIN. Only used when the page
    has no father/mother labels, so labeled passports are left alone.
    """
    if not blocks:
        return {}
    by_page: dict[int, list[tuple[int, str]]] = {}
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        text = _block_text(blk)
        if not text:
            continue
        try:
            page = int(
                blk.get("page_index")
                if blk.get("page_index") is not None
                else blk.get("page")
                or 0
            )
            order = int(
                blk.get("reading_order_index")
                if blk.get("reading_order_index") is not None
                else blk.get("order")
                or 0
            )
        except (TypeError, ValueError):
            continue
        by_page.setdefault(page, []).append((order, text))

    def _addr_piece(text: str) -> bool:
        t = text.strip()
        if not t or _looks_like_date_value(t):
            return False
        compact = re.sub(r"[\s\-/]+", "", t).upper()
        if _FILE_NO_SHAPE_RE.match(compact) or _PASSPORT_NO_SHAPE_RE.match(compact):
            return False
        if re.fullmatch(r"\d{1,4}", compact):
            return False
        if re.search(r"(?i)\bPIN\s*:?\s*\d{6}\b", t):
            return True
        if re.search(
            r"(?i)\b(?:blok|block|h\.?\s*no|d\.?\s*no|room|road|street|lane|nagar|oad|"
            r"school|college|engineering|institute|house\s*(?:no\.?|number))\b",
            t,
        ):
            return True
        if re.search(r"(?i)\b[A-Z]{1,3}-\d|\d{1,4}\s*/\s*\d|\d{1,4}\s*-\s*\d{1,4}", t):
            return True
        if "," in t and re.search(r"[A-Za-z]{4,}", t):
            return True
        return False

    for rows in by_page.values():
        rows.sort(key=lambda pair: pair[0])
        texts = [t for _, t in rows]
        blob = "\n".join(texts)
        if _FATHER_LABEL_FUZZY_RE.search(blob) or _MOTHER_LABEL_FUZZY_RE.search(blob):
            continue
        if not (
            re.search(r"(?i)\bPIN\s*:?\s*\d{6}\b", blob)
            or re.search(r"(?i)\b(?:blok|block|house\s*(?:no\.?|number))\b", blob)
        ):
            continue
        stamp_names = _notary_neighbor_tokens(texts)
        names: list[str] = []
        addr: list[str] = []
        for text in texts:
            if _line_is_notary_comment(text) or _name_is_notary_neighbor(text, texts):
                continue
            if _addr_piece(text):
                if _line_matches_stamp_locality(text, _repeated_stamp_signatures(blob)):
                    continue
                addr.append(re.sub(r"\s+", " ", text).strip(" ,"))
                continue
            if (
                len(names) < 3
                and _is_plausible_person_name(text)
                and len(text.split()) >= 2
                and "," not in text
                and not _name_is_notary_neighbor(text, texts)
                and not any(
                    SequenceMatcher(None, part, stamp).ratio() >= 0.72
                    for part in re.findall(r"[A-Za-z]{4,}", text.lower())
                    for stamp in stamp_names
                )
            ):
                cleaned = _clean_person_name(text)
                if cleaned and not _name_is_notary_neighbor(cleaned, texts):
                    names.append(cleaned)
                continue
        # Spouse is the third person only. Two names are father and mother;
        # a blank spouse cell must not be filled from a stamp.
        if len(names) < 2 or len(addr) < 2:
            continue
        out: dict[str, str] = {
            "father_name": names[0],
            "mother_name": names[1],
        }
        if len(names) >= 3:
            out["spouse_name"] = names[2]
        addr = _prefer_full_address_lines(addr)
        joined = normalize_multiline_address(", ".join(addr))
        if joined and len(joined) >= 12:
            out["address"] = joined
        return out
    return {}


def _passport_has_spouse_label(
    text: str | None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """True when OCR shows a Spouse name label (many passports omit this field)."""
    if text and _SPOUSE_LABEL_EVIDENCE_RE.search(text):
        return True
    for line in (text or "").splitlines():
        if block_is_field_label(line, "spouse_name") or _SPOUSE_LABEL_EVIDENCE_RE.search(
            line
        ):
            return True
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        t = str(
            blk.get("cleaned_text")
            or blk.get("text")
            or blk.get("raw_ocr_text")
            or ""
        )
        if t and (
            _SPOUSE_LABEL_EVIDENCE_RE.search(t) or block_is_field_label(t, "spouse_name")
        ):
            return True
    return False


def _passport_has_spouse_evidence(
    text: str | None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """True when a spouse value is grounded in OCR (label or unlabeled 3-name row).

    CamScanner often garbles ``Name of Spouse`` into crumbs like ``nod w/`` while
    still printing a clear third person name (e.g. LAKXMI ARAVIND). Do not wipe
    that name solely because the label string is missing.
    """
    return _passport_has_spouse_label(text, blocks)


def _is_blank_spouse_value(value: str | None) -> bool:
    t = (value or "").strip()
    if not t:
        return True
    if _SPOUSE_BLANK_VALUE_RE.match(t):
        return True
    # Label remnant only (no actual name).
    if _SPOUSE_LABEL_FUZZY_RE.fullmatch(t) or re.fullmatch(
        r"(?i)name\s*(?:of|ot)\s*(?:spouse|spouce)\s*/?", t
    ):
        return True
    return False


def _spouse_name_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Spouse name from page-2 OCR fuzzy/regex label anchors only.

    When a Spouse label exists but the value is blank/junk (went, N/A), return
    None — do not invent from ROI (cities, date-line OCR, surname). Fully
    unlabeled family pages are handled by ``_unlabeled_family_row_from_blocks``.
    """
    items = _ocr_block_items(blocks)
    if not items:
        return None
    stop = [
        _FATHER_LABEL_FUZZY_RE,
        _MOTHER_LABEL_FUZZY_RE,
        _FILE_LABEL_FUZZY_RE,
        re.compile(r"(?i)\b(?:address|old\s*passport|pin\b|room\b)\b"),
    ]

    def _accept(raw: str | None) -> str | None:
        if not raw:
            return None
        cleaned = _clean_person_name(raw)
        if cleaned and not _is_blank_spouse_value(cleaned) and _is_plausible_person_name(
            cleaned
        ):
            return cleaned
        return None

    anchor_idxs: list[int] = []
    fuzzy_i = find_label_anchor_index(items, "spouse_name")
    if fuzzy_i is not None:
        anchor_idxs.append(fuzzy_i)
    for i, (_, _, _, _, _, text) in enumerate(items):
        if i in anchor_idxs:
            continue
        if _SPOUSE_LABEL_FUZZY_RE.search(text) or block_is_field_label(text, "spouse_name"):
            anchor_idxs.append(i)
    for i in anchor_idxs:
        text = items[i][5]
        same = (
            _name_from_same_box(text, _SPOUSE_LABEL_FUZZY_RE)
            if _SPOUSE_LABEL_FUZZY_RE.search(text)
            else None
        )
        hit = _accept(same)
        if hit:
            return hit
        raw = _value_near_label(
            items,
            i,
            is_value=_is_parent_name_candidate,
            stop_res=stop,
            directions=("below",),
        )
        hit = _accept(raw)
        if hit:
            return hit

    return None


def _file_number_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Alphanumeric File No. token right-of / under an OCR-garbled File/A3 label."""
    items = _ocr_block_items(blocks)
    if not items:
        return None

    def _file_token(text: str) -> str | None:
        raw = (text or "").strip()
        if _looks_like_file_number_token(raw):
            return re.sub(r"\s+", "", raw).upper()
        tok = re.sub(r"[\s\-/]+", "", raw).upper()
        if not tok:
            return None
        if _is_garbage_file_number(raw) or _is_garbage_file_number(tok):
            return None
        if _PASSPORT_NO_SHAPE_RE.match(tok):
            return None
        if _FILE_NO_SHAPE_RE.match(tok) and _looks_like_file_number_token(tok):
            return tok
        m = re.search(r"([A-Z]{1,5}\d{6,14}[A-Z0-9]{0,4})", tok)
        if (
            m
            and not _PASSPORT_NO_SHAPE_RE.match(m.group(1))
            and _looks_like_file_number_token(m.group(1))
        ):
            return m.group(1)
        return None

    anchor_idxs: list[int] = []
    fi = find_label_anchor_index(items, "file_number")
    if fi is not None:
        anchor_idxs.append(fi)
    for i, (_, _, _, _, _, text) in enumerate(items):
        if i in anchor_idxs:
            continue
        if block_is_field_label(text, "file_number") or _FILE_LABEL_FUZZY_RE.search(text):
            if re.search(r"(?i)\bpita\b|\bpil?ta\b", text):
                continue
            anchor_idxs.append(i)
    for i in anchor_idxs:
        text = items[i][5]
        same = (
            _file_token(_FILE_LABEL_FUZZY_RE.sub(" ", text))
            if _FILE_LABEL_FUZZY_RE.search(text)
            else None
        )
        if same:
            return same
        raw = _value_near_label(
            items,
            i,
            is_value=lambda t: _file_token(t) is not None,
            stop_res=[
                _FATHER_LABEL_FUZZY_RE,
                _MOTHER_LABEL_FUZZY_RE,
                _SPOUSE_LABEL_FUZZY_RE,
                re.compile(r"(?i)\b(?:address|old\s*passport|pin\b)\b"),
            ],
        )
        if raw:
            tok = _file_token(raw)
            if tok:
                return tok
    for cand in values_in_field_roi(
        items, "file_number", is_value=lambda t: _file_token(t) is not None
    ):
        tok = _file_token(cand)
        if tok:
            return tok
    # Global fallback on any page (single-image OCR often keeps page_index=0).
    for _page, _, _, _, _, text in items:
        tok = _file_token(text)
        if tok and not _FILE_LABEL_FUZZY_RE.search(text):
            return tok
    return None


def _recover_orphan_name_tokens(
    text: str,
    father: str | None,
    mother: str | None,
) -> tuple[str | None, str | None]:
    """Append trailing tokens / split interleaved columnar OCR name lines."""
    f_parts = (father or "").split()
    m_parts = (mother or "").split()
    _STOP = {
        "ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "IN", "AT",
        "NAME", "NO", "NO.", "MQ", "O", "N", "MQ.",
    }

    # Shared name region: after the parent labels, before address/file.
    # When both labels appear before any values (columnar OCR), all name lines
    # often land in one bucket — recover by interleaving rows (L/R columns).
    region_m = re.search(
        r"(?is)(?:name[ \t]*(?:of|ot)[ \t]*(?:father|foter)|father(?:'s)?[ \t]*name|"
        r"foter|curdian|name[ \t]*(?:of|ot)[ \t]*(?:mother|mather)|"
        r"mother(?:'s)?[ \t]*name|mather)"
        r".{0,80}?"
        r"(?:name[ \t]*(?:of|ot)[ \t]*(?:father|foter)|father(?:'s)?[ \t]*name|"
        r"foter|curdian|name[ \t]*(?:of|ot)[ \t]*(?:mother|mather)|"
        r"mother(?:'s)?[ \t]*name|mather)"
        r"[^\n]*\n(.*?)(?=^[ \t]*(?:address|file[ \t]*(?:no|number)|fke|"
        r"a3[ \t]*/|old[ \t]*passport|denl|pin\b|name[ \t]*(?:of|ot)[ \t]*spouse)"
        r"|\Z)",
        text or "",
        re.MULTILINE,
    )
    name_lines: list[str] = []
    if region_m:
        for raw in region_m.group(1).splitlines():
            line = raw.strip()
            if not line or _NEXT_FIELD_LABEL_RE.match(line) or _is_noise_value(line):
                continue
            if _FATHER_LABEL_FUZZY_RE.search(line) or _MOTHER_LABEL_FUZZY_RE.search(line):
                continue
            if re.search(r"\d{3,}", line):
                break
            if _is_name_continuation_line(line) or re.match(
                r"^[A-Za-z][A-Za-z .'-]{1,60}$", line
            ):
                name_lines.append(line)

    # Interleaved rows: Father-col, Mother-col, Father-col, Mother-col, …
    if name_lines and (not f_parts or not m_parts or len(m_parts) >= 5 and not f_parts):
        left: list[str] = []
        right: list[str] = []
        for i, line in enumerate(name_lines):
            (left if i % 2 == 0 else right).append(line)
        left_name = _clean_person_name(" ".join(left))
        right_name = _clean_person_name(" ".join(right))
        if left_name and (not father or len(left_name.split()) > len(f_parts)):
            f_parts = left_name.split()
        if right_name:
            # Replace an over-long mother blob that absorbed both columns, or
            # fill when mother was missing.
            if (
                not m_parts
                or len(m_parts) >= 5
                or (father is None and len(m_parts) > len(right_name.split()))
            ):
                m_parts = right_name.split()
            elif len(right_name.split()) > len(m_parts):
                m_parts = right_name.split()
    # Single-token orphans still missing after the interleaved pass.
    known = {p.upper() for p in f_parts + m_parts}
    orphans: list[str] = []
    for line in name_lines:
        tokens = line.replace("/", " ").split()
        if len(tokens) == 1 and tokens[0].upper() not in known:
            tok = tokens[0]
            if tok.upper().rstrip(".") in _STOP:
                continue
            if not _NAME_TOKEN_RE.match(tok) or len(tok) < 3:
                continue
            orphans.append(tok)
            known.add(tok.upper())

    for tok in orphans:
        need_f = len(f_parts) < 4
        need_m = len(m_parts) < 3
        if need_f and (not need_m or len(f_parts) <= len(m_parts)):
            f_parts.append(tok)
        elif need_m:
            m_parts.append(tok)
        elif need_f:
            f_parts.append(tok)

    return (
        _clean_person_name(" ".join(f_parts)) if f_parts else None,
        _clean_person_name(" ".join(m_parts)) if m_parts else None,
    )


def _extract_labeled_fields(
    text: str,
    *,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    found: dict[str, str] = {}
    raw = text or ""

    # --- Surname / given names (multi-line Indian layout) ---
    # Bound surname to the next personal label so we never swallow Place of Birth.
    surname_block = _slice_between_labels(
        raw,
        r"(?:[A-Za-z0-9]{2,8}[ \t]*/[ \t]*)?"
        r"(?:surname|family[ \t]*name|last[ \t]*name)"
        r"(?:[ \t]*/[ \t]*nom)?",
        r"(?:given[ \t]*names?(?:\s*\(\s*s\s*\))?|first[ \t]*names?(?:\s*\(\s*s\s*\))?|"
        r"forenames?|prenoms?|"
        r"place[ \t]*of[ \t]*birth|date[ \t]*of[ \t]*birth|sex|nationality|"
        r"passport|place[ \t]*of[ \t]*issue)",
    )
    surname = _clean_person_name(
        _value_after_label(
            raw,
            r"(?:[A-Za-z0-9]{2,8}[ \t]*/[ \t]*)?"
            r"(?:surname|family[ \t]*name|last[ \t]*name)"
            r"(?:[ \t]*/[ \t]*nom)?",
        )
    ) or _name_from_block(surname_block)
    # Reject values that are clearly the next field's label or a place string.
    if surname and (
        _is_noise_value(surname)
        or re.search(r"(?i)place of|birth|issue|nationality", surname)
        or "," in surname
    ):
        surname = None
    if surname:
        found["surname"] = surname
        # Do not invent given_names from the line under Surname. Given names
        # come only from their own label or from the MRZ given-name tokens.

    given = _value_after_label(
        raw,
        r"(?:given[ \t]*names?(?:\s*\(\s*s\s*\))?|first[ \t]*names?(?:\s*\(\s*s\s*\))?|"
        r"forenames?|prenoms?)",
    )
    given = _clean_person_name(given)
    if given and not re.search(r"(?i)place of|date of|nationality", given):
        found["given_names"] = given

    # --- Places (must not cross-wire birth ↔ issue ↔ dates) ---
    block_biodata = _biodata_places_dates_from_ocr_blocks(ocr_blocks)
    for bk in (
        "place_of_birth",
        "place_of_issue",
        "date_of_birth",
        "date_of_issue",
        "date_of_expiry",
    ):
        if block_biodata.get(bk):
            found[bk] = block_biodata[bk]

    pob = _value_after_label(
        raw,
        rf"{_PLACE_WORD_OCR}[ \t]*{_PLACE_OF_CONNECTOR_OCR}[ \t]*{_PLACE_OF_BIRTH_WORD_OCR}|"
        r"lieu[ \t]*de[ \t]*naissance",
    )
    if pob and (_looks_like_date_value(pob) or _is_nationality_as_place(pob)):
        # Rotated OCR often puts DOB immediately after the Place of Birth label.
        # PDF OCR may also leave nationality (HR/INDIAN) on the prior line.
        pob = None
    if pob and not _is_noise_value(pob) and not re.search(r"(?i)issue", pob):
        # Stacked "Surname / Place of Birth / KUMAR / CHENNAI" — skip if value
        # is clearly the surname we already captured.
        if found.get("surname") and pob.strip().upper() == found["surname"].strip().upper():
            # Walk one more line after the mistaken value.
            idx = raw.upper().find(pob.upper())
            alt = None
            if idx >= 0:
                for ln in raw[idx + len(pob) :].splitlines()[:4]:
                    t = ln.strip()
                    if not t or _is_noise_value(t) or _NEXT_FIELD_LABEL_RE.match(t):
                        if t and _NEXT_FIELD_LABEL_RE.match(t):
                            break
                        continue
                    if t.upper() == found["surname"].strip().upper():
                        continue
                    if _looks_like_date_value(t):
                        continue
                    alt = t
                    break
            pob = alt
        if (
            pob
            and not _is_noise_value(pob)
            and not re.search(r"(?i)issue", pob)
            and not _looks_like_date_value(pob)
            and not found.get("place_of_birth")
        ):
            found["place_of_birth"] = pob[:80]
    # Spatial block wins over a date-shaped text hit.
    if found.get("place_of_birth") and _looks_like_date_value(str(found["place_of_birth"])):
        found["place_of_birth"] = block_biodata.get("place_of_birth")
    if not found.get("place_of_birth") and block_biodata.get("place_of_birth"):
        found["place_of_birth"] = block_biodata["place_of_birth"]
    if (
        not found.get("place_of_birth")
        or _is_postal_address_as_place(str(found.get("place_of_birth") or ""))
        or re.search(r"\d", str(found.get("place_of_birth") or ""))
    ):
        city_state = _city_state_near_birth_label(raw)
        if city_state:
            found["place_of_birth"] = city_state

    # Biodata Place of Issue only — skip "Old Passport … Place of Issue" stamps.
    poi = None
    for poi_m in re.finditer(
        rf"(?im)^[^\n]*\b{_PLACE_WORD_OCR}\s*o[ft][.\s]*{_PLACE_OF_ISSUE_OCR}"
        r"[ \t]*[:\-–—/]?[ \t]*(.*)$",
        raw,
    ):
        line_head = raw[poi_m.start() : poi_m.end()]
        if _OLD_PASSPORT_PLACE_OF_ISSUE_RE.search(line_head) or re.search(
            r"(?i)old\s*passport", line_head
        ):
            continue
        same = (poi_m.group(1) or "").strip()
        if same and not _is_noise_value(same) and not re.match(
            r"(?i)^(place|date|name|sex|nationality|code|type|father|mother|"
            r"guardian|legal)\b",
            same,
        ):
            poi = same
            break
        poi = None
        for ln in raw[poi_m.end() :].splitlines()[:8]:
            line = ln.strip()
            if not line:
                continue
            if _is_noise_value(line):
                continue
            if _NEXT_FIELD_LABEL_RE.match(line) or re.match(
                r"(?i)^(place of|date of|name of|sex|gender|nationality|surname|"
                r"given|passport|code|type|file|address|old passport)\b",
                line,
            ):
                break
            poi = line
            break
        if poi:
            break
    if poi and not _is_noise_value(poi) and not re.search(r"(?i)birth", poi):
        pob_u = str(found.get("place_of_birth") or "").strip().upper()
        poi_n = _normalize_place_token(poi)
        if pob_u and poi_n.upper() == pob_u:
            poi = None
        else:
            existing_poi = str(found.get("place_of_issue") or "").strip()
            holder_given = str(found.get("given_names") or "")
            holder_surname = str(found.get("surname") or "")
            # Linear city wins when geometry latched onto given-name / surname /
            # residential PIN address (permanent issuing-office rule).
            if (
                not existing_poi
                or _is_holder_name_as_place(
                    existing_poi, surname=holder_surname, given_names=holder_given
                )
                or _is_postal_address_as_place(existing_poi)
                or not _is_issuing_office_candidate(
                    existing_poi, surname=holder_surname, given_names=holder_given
                )
            ):
                if _is_issuing_office_candidate(
                    poi_n, surname=holder_surname, given_names=holder_given
                ):
                    found["place_of_issue"] = poi_n[:80]

    # Linear OCR: "Date of Issue CHENNAI Place of lssue ERODE… Place of Birth".
    # City between the two issue labels is place of issue (not birth).
    if not found.get("place_of_issue"):
        between = re.search(
            rf"(?is)date\s*of\s*{_PLACE_OF_ISSUE_OCR}\s+"
            rf"([A-Za-z][A-Za-z .]{{2,40}}?)\s+"
            rf"place\s*of\s*{_PLACE_OF_ISSUE_OCR}",
            raw,
        )
        if between:
            city = _normalize_place_token(between.group(1))
            pob_u = str(found.get("place_of_birth") or "").strip().upper()
            if (
                city
                and not _is_noise_value(city)
                and not _looks_like_date_value(city)
                and city.upper() != pob_u
                and _is_issuing_office_candidate(
                    city,
                    surname=str(found.get("surname") or ""),
                    given_names=str(found.get("given_names") or ""),
                )
            ):
                found["place_of_issue"] = city[:80]

    # When OCR stacks "Place of Birth / Place of issue / CITY", city is often issue.
    if "place_of_birth" not in found and "place_of_issue" in found:
        pass
    stacked = re.search(
        rf"(?is)place\s*of\s*birth\s*\n\s*place\s*of\s*{_PLACE_OF_ISSUE_OCR}\s*\n\s*"
        r"([A-Za-z][A-Za-z0-9 ,.\-/]{2,60})",
        raw,
    )
    if stacked:
        city = _normalize_place_token(stacked.group(1))
        if city and not _is_noise_value(city) and _is_issuing_office_candidate(
            city,
            surname=str(found.get("surname") or ""),
            given_names=str(found.get("given_names") or ""),
        ):
            # Under stacked birth/issue labels the first city is usually place of issue.
            found["place_of_issue"] = city[:80]

    # Birth place sometimes appears as "CITY, STATE" away from labels — only
    # when a Place of Birth label exists. Never promote address city/state lines
    # from a last-page-only scan that has Address but no birth label.
    if "place_of_birth" not in found:
        has_pob_label = bool(
            re.search(
                r"(?i)place\s*of\s*(?:birth|blrth|birih|bith|bre\b)",
                raw,
            )
        )
        if has_pob_label:
            addr_span = None
            addr_m = re.search(
                r"(?im)^[^\n]*\b(?:address|addrese|addiese|adrhess|adress)\b",
                raw,
            )
            if addr_m:
                addr_span = addr_m.start()
            for m in re.finditer(
                r"(?im)^([A-Z][A-Za-z .]{2,40},\s*[A-Z][A-Za-z ]{3,40})$",
                raw,
            ):
                if addr_span is not None and m.start() >= addr_span:
                    continue
                cand = m.group(1).strip()
                if cand and not _is_noise_value(cand) and not _is_nationality_as_place(cand):
                    found["place_of_birth"] = cand[:80]
                    break

    # --- Nationality (validate demonym / ISO; reject Sex/DOB bleed garbage) ---
    block_nat, block_nat_code = _nationality_from_ocr_blocks(ocr_blocks)
    if block_nat:
        found["nationality"] = block_nat
        if block_nat_code:
            found["country_code"] = block_nat_code

    nat_line = _value_after_label(
        raw, r"nationality|nationalit[eé]|citizenship|citoyennet[eé]"
    )
    demonym, nat_code = resolve_nationality(nat_line)
    if demonym and not found.get("nationality"):
        found["nationality"] = demonym
        if nat_code:
            found.setdefault("country_code", nat_code)
    elif not found.get("nationality") and re.search(
        r"(?i)republic\s*of\s*india|\bindian\b", raw
    ):
        found["nationality"] = "INDIAN"
        found.setdefault("country_code", "IND")

    # --- Sex ---
    sex_m = re.search(
        r"(?i)(?:sex|gender|sexe|pem\s*/\s*sex)\s*[:\-–—/]?\s*([MFX]|Male|Female)\b",
        raw,
    )
    if sex_m:
        sex = _norm_sex(sex_m.group(1))
        if sex:
            found["sex"] = sex

    # Indian biodata row: "INDIAN F 10/06/1990" or "H/INDIAN F 24/11/1994".
    # Sex / DOB labels are often garbled while this combo line stays clean.
    combo = re.search(
        rf"(?i)\b(?:[A-Z]{{1,3}}\s*/\s*)?(?:INDIAN|IND)\s+([MFX])\s+{_DATE_CAPTURE}",
        raw,
    )
    if combo:
        if not found.get("sex"):
            sex = _norm_sex(combo.group(1))
            if sex:
                found["sex"] = sex
        if not found.get("nationality"):
            found["nationality"] = "INDIAN"
            found.setdefault("country_code", "IND")
        if not found.get("date_of_birth"):
            iso = _parse_flexible_date(combo.group(2))
            if iso and not _date_only_in_old_passport_context(raw, iso):
                found["date_of_birth"] = iso
    # Same biodata row often OCRs as "30/06/1995 M" when the Sex label is on the line above.
    if not found.get("sex"):
        date_then_sex = re.search(
            r"(?i)\b\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}\s+([MFX])\b",
            raw,
        )
        if date_then_sex:
            sex = _norm_sex(date_then_sex.group(1))
            if sex:
                found["sex"] = sex
            if not found.get("date_of_birth"):
                iso = _parse_flexible_date(date_then_sex.group(0).split()[0])
                if iso and not _date_only_in_old_passport_context(raw, iso):
                    found["date_of_birth"] = iso

    # --- Document number (Indian: letter + 7 digits) ---
    indian_nos = re.findall(r"\b([A-Z]\d{7})\b", raw.upper())
    doc_m = re.search(
        r"(?i)(?:passport\s*(?:no|number|#)|passpon\s*no|document\s*(?:no|number))"
        r"\s*[:\-–—]?\s*([A-Z][0-9]{7}|[A-Z0-9]{6,9})",
        raw,
    )
    if doc_m and re.fullmatch(r"[A-Z]\d{7}", doc_m.group(1).upper()):
        found["document_number"] = doc_m.group(1).upper()
    elif indian_nos:
        # Prefer the first passport-shaped token (page 1), not a repeat later.
        found["document_number"] = indian_nos[0]

    # --- Dates (page 1 biodata; issue date is NOT in MRZ) ---
    # Prefer geometry-based dates when OCR reading order swapped Place↔Date.
    for bk in ("date_of_birth", "date_of_issue"):
        if block_biodata.get(bk) and bk not in found:
            found[bk] = block_biodata[bk]

    for key, label in (
        ("date_of_birth", r"date[ \t]*of[ \t]*birth|birth[ \t]*date|dob"),
        (
            "date_of_issue",
            r"date[ \t]*of[ \t]*(?:issu(?:e|ance)|lssue|issuc|lssuo)|"
            r"issued[ \t]*(?:on|date)?|date[ \t]*of[ \t]*issue",
        ),
        (
            "date_of_expiry",
            r"date[ \t]*of[ \t]*expir[yation]*|date[ \t]*of[ \t]*expiny|expiry[ \t]*date|"
            r"expiration(?:[ \t]*date)?|valid[ \t]*(?:until|thru|through)",
        ),
    ):
        if found.get(key):
            continue
        m = re.search(
            rf"(?i)(?:{label})[ \t]*[:\-–—/]?[ \t]*{_DATE_CAPTURE}",
            raw,
        )
        if m:
            iso = _parse_flexible_date(m.group(1))
            if iso:
                if key == "date_of_birth" and _date_only_in_old_passport_context(raw, iso):
                    pass
                else:
                    found[key] = iso
                    continue
        # Label on one line, date on next (common Indian layout).
        val = _value_after_label(raw, label)
        iso = _parse_flexible_date(val)
        if iso:
            if not (key == "date_of_birth" and _date_only_in_old_passport_context(raw, iso)):
                found[key] = iso
        elif val:
            # Date may share the line with OCR junk — pull first date token.
            dm = re.search(_DATE_CAPTURE, val)
            if dm:
                iso = _parse_flexible_date(dm.group(1))
                if iso and not (
                    key == "date_of_birth" and _date_only_in_old_passport_context(raw, iso)
                ):
                    found[key] = iso

    # Extra pass for date_of_issue: stacked "Date of Issue / Date of Expiry" layouts.
    if "date_of_issue" not in found:
        stacked_iss = re.search(
            r"(?is)date[ \t]*of[ \t]*(?:issu(?:e|ance|c)|lssue)[^\n]{0,80}\n[ \t]*"
            rf"{_DATE_CAPTURE}",
            raw,
        )
        if stacked_iss:
            iso = _parse_flexible_date(stacked_iss.group(1))
            if iso:
                found["date_of_issue"] = iso
    # Geometry override when text path still has Place/Date crossed.
    if block_biodata.get("date_of_birth"):
        found["date_of_birth"] = block_biodata["date_of_birth"]
    # Always prefer geometry for issue/expiry — text OCR often swaps them
    # when both labels sit on one line.
    if block_biodata.get("date_of_issue"):
        found["date_of_issue"] = block_biodata["date_of_issue"]
    if block_biodata.get("date_of_expiry"):
        found["date_of_expiry"] = block_biodata["date_of_expiry"]
    if block_biodata.get("place_of_birth"):
        found["place_of_birth"] = block_biodata["place_of_birth"]

    # Paired issue/expiry dates on one OCR row: earlier = issue, later = expiry.
    # Allow MM/YYYY (truncated day) and a wider gap for address PIN OCR noise.
    _DATE_OR_MY = (
        r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{1,2}[./\-]\d{4})"
    )
    pair = re.search(
        rf"(?is)date\s*of\s*(?:issu|lssu).{{0,160}}?"
        rf"(?:date\s*of\s*exp|expir|sptry|expty|expiny).{{0,120}}?"
        rf"{_DATE_OR_MY}.{{0,40}}?{_DATE_OR_MY}",
        raw,
    )
    if not pair:
        # Garbled labels ("Date af etie … / Date at Capiry") with both dates
        # on the next line — still recover issue/expiry by shape. Require full
        # day-month-year tokens so "5/2015" inside "22/05/2015" cannot win.
        pair = re.search(
            rf"(?is)date\s*\w+.{{0,100}}?(?:expir|capir|sptry|expty|expiny|capiry).{{0,80}}"
            rf"(?:\n[^\n]{{0,40}})?{_DATE_CAPTURE}[ \t]+{_DATE_CAPTURE}",
            raw,
        )
    if pair:
        d1 = _parse_flexible_date(pair.group(1)) or _parse_month_year_date(pair.group(1))
        d2 = _parse_flexible_date(pair.group(2)) or _parse_month_year_date(pair.group(2))
        if d1 and d2:
            from datetime import datetime as _dt

            def _pd(s: str):
                for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
                    try:
                        return _dt.strptime(s[:10], fmt)
                    except ValueError:
                        continue
                return None

            a, b = _pd(d1), _pd(d2)
            if a and b and a != b:
                if a <= b:
                    # Don't overwrite a geometry-resolved issue with a truncated
                    # month/year parse when geometry already has a full date.
                    if not block_biodata.get("date_of_issue"):
                        found["date_of_issue"] = d1
                    found.setdefault("date_of_expiry", d2)
                else:
                    if not block_biodata.get("date_of_issue"):
                        found["date_of_issue"] = d2
                    found.setdefault("date_of_expiry", d1)

    paired_issue, paired_expiry = _issue_expiry_from_paired_date_line(raw)
    if paired_issue and not found.get("date_of_issue"):
        found["date_of_issue"] = paired_issue
    if paired_expiry and not found.get("date_of_expiry"):
        found["date_of_expiry"] = paired_expiry
    if not found.get("date_of_issue"):
        before_issue = _date_before_issue_label(raw)
        if before_issue and before_issue != found.get("date_of_birth"):
            found["date_of_issue"] = before_issue

    fuzzy_issue = _values_from_fuzzy_issue_labels(raw)
    if not found.get("place_of_birth") and fuzzy_issue.get("place_of_birth"):
        found["place_of_birth"] = fuzzy_issue["place_of_birth"]
    if not found.get("place_of_issue") and fuzzy_issue.get("place_of_issue"):
        poi_f = fuzzy_issue["place_of_issue"]
        pob_u = str(found.get("place_of_birth") or "").strip().upper()
        if poi_f.strip().upper() != pob_u:
            found["place_of_issue"] = poi_f
    if not found.get("date_of_issue") and fuzzy_issue.get("date_of_issue"):
        doi_f = fuzzy_issue["date_of_issue"]
        if doi_f != found.get("date_of_birth"):
            found["date_of_issue"] = doi_f

    iss = _value_after_label(
        raw,
        r"issuing[ \t]*(?:state|country|authority)|code[ \t]*of[ \t]*issuing",
    )
    alpha = _to_alpha3(iss)
    if alpha and alpha in _VALID_ALPHA3:
        found["country_code"] = alpha
    elif re.search(r"(?i)republic\s*of\s*india|\bindian\b", raw):
        found.setdefault("country_code", "IND")

    # Second-pass visual nationality: only accept validated demonyms / codes.
    nat_visual = _value_after_label(
        raw, r"nationality|citizenship|nationalit[eé]|citoyennet[eé]"
    )
    demonym_v, alpha_v = resolve_nationality(nat_visual)
    if demonym_v:
        found["nationality"] = demonym_v
        if alpha_v:
            found["country_code"] = alpha_v
    if not found.get("nationality") and found.get("country_code"):
        dem = demonym_for_country_code(str(found["country_code"]))
        if dem:
            found["nationality"] = dem

    # --- Page 2 fields (label-bounded + OCR-column + orphan token recovery) ---
    block_father, block_mother = _parent_names_from_ocr_blocks(ocr_blocks)
    if block_father and not _is_plausible_person_name(block_father):
        block_father = None
    if block_mother and not _is_plausible_person_name(block_mother):
        block_mother = None
    block_spouse = _spouse_name_from_ocr_blocks(ocr_blocks)
    if block_spouse and not _is_plausible_person_name(block_spouse):
        block_spouse = None
    block_file = _file_number_from_ocr_blocks(ocr_blocks)

    father_label = (
        r"n(?:ame|ane|eme|ere)[ \t]*(?:of|ot|ol)[ \t]*"
        r"(?:father|foter|fother|pathvet)"
        r"(?:[ \t]*/[ \t]*lega[ls]?[ \t]*(?:guardian|guardlan|gusrdian|gurdian|curdian))?|"
        r"father(?:'s)?[ \t]*name|foter|fother|name[ \t]*of[ \t]*guardian|"
        r"(?:lega[ls]?[ \t]*)?(?:guardian|guardlan|gusrdian|gurdian|curdian|uardian|quardian)|"
        r"reme[ \t]*of[ \t]*foter|lepai[ \t]*curdian|"
        r"nere[ \t]*of[ \t]*pathvet"
    )
    mother_label = (
        r"n(?:ame|ane|eme)[ \t]*(?:of|ot|ol)[ \t]*(?:mother|mather|mothor|mathe|maches)|"
        r"mother(?:'s)?[ \t]*name|mather|mathe|name[ \t]*of[ \t]*maches"
    )
    spouse_label = (
        r"name[ \t]*(?:of|ot)[ \t]*(?:spouse|spouce)|"
        r"spouse(?:'s)?[ \t]*name"
    )

    father_block = _slice_between_labels(
        raw,
        father_label,
        mother_label + r"|address|file[ \t]*(?:no|number)|fke[ \t]*no|place[ \t]*of",
    )
    father = _name_from_block(father_block)
    if not father or not _is_plausible_person_name(father):
        father = _person_name_after_label(raw, father_label)
    # Last-page layout: holder/father name sits left of the Father label while
    # the slice between labels may latch onto the next person line (mother).
    before_father = _person_name_before_label_on_line(raw, father_label)
    if before_father and _is_plausible_person_name(before_father):
        father = before_father
    if father and re.search(r"(?i)guardian|guardlan|lega|canrdian|parer|poner|foter|lepai", father):
        father = None
    if not father:
        # Do not let IGNORECASE apply to the name capture — OCR crumbs like
        # "on" / "Name" would otherwise match as continuation lines.
        fm = re.search(
            r"(?s)(?:[Ff]ather|[Ff]oter|[Gg]uardian|[Qq]uardian|[Pp]arer|[Cc]urdian)[^\n]{0,60}\n"
            r"([A-Z][A-Za-z .']{4,100}(?:\n[A-Z][A-Za-z.']{2,40}){0,3})",
            raw,
        )
        if fm:
            father = _clean_person_name(re.sub(r"\s+", " ", fm.group(1)))
        if father and re.search(
            r"(?i)guardian|guardlan|lega|canrdian|name of|foter|lepai|mather", father
        ):
            father = None
    # Prefer OCR-block names when available (cleaner than garbled text lines).
    if block_father and (
        not father
        or _PARENT_NAME_JUNK_RE.search(father or "")
        or _has_trailing_name_crumb(father)
        or len(block_father.split()) >= len((father or "").split())
    ):
        father = block_father

    mother_block = _slice_between_labels(
        raw,
        mother_label,
        r"address|file[ \t]*(?:no|number)|fke[ \t]*no|old[ \t]*passport|denl|"
        r"name[ \t]*(?:of|ot)[ \t]*spouse|spouse(?:'s)?[ \t]*name|place[ \t]*of",
    )
    mother = _name_from_block(mother_block)
    if not mother or not _is_plausible_person_name(mother):
        mother = _person_name_after_label(raw, mother_label)
    if not mother:
        mm = re.search(
            r"(?s)(?:[Mm]other|[Mm]ather|[Mm]aches)[^\n]{0,40}\n"
            r"([A-Z][A-Za-z .']{4,100}(?:\n[A-Z][A-Za-z.']{2,40}){0,3})",
            raw,
        )
        if mm:
            mother = _clean_person_name(re.sub(r"\s+", " ", mm.group(1)))
    if block_mother and (
        not mother
        or _PARENT_NAME_JUNK_RE.search(mother or "")
        or _has_trailing_name_crumb(mother)
        or len(block_mother.split()) >= len((mother or "").split())
    ):
        mother = block_mother

    # Only run orphan recovery when a side is still missing — never mutate
    # clean OCR-block names with CamScanner crumbs ("on", "Name").
    if not father or not mother:
        rec_f, rec_m = _recover_orphan_name_tokens(raw, father, mother)
        if not father and rec_f:
            father = rec_f
        if not mother and rec_m:
            mother = rec_m
    father = _strip_trailing_name_crumbs(father)
    mother = _strip_trailing_name_crumbs(mother)
    if father and not _is_plausible_person_name(father):
        father = None
    if mother and not _is_plausible_person_name(mother):
        mother = None
    if father and not _PARENT_NAME_JUNK_RE.search(father):
        found["father_name"] = father
    if mother and not _PARENT_NAME_JUNK_RE.search(mother):
        found["mother_name"] = mother

    # Spouse is booklet-optional. Prefer fuzzy/regex label anchors; if garbled,
    # keep OCR/ROI/block values that pass person-name shape. Never invent from
    # address / parent names; never wipe a valid value for a label miss.
    spouse: str | None = None
    if _passport_has_spouse_label(raw, ocr_blocks):
        spouse_block = _slice_between_labels(
            raw,
            spouse_label,
            r"address|file[ \t]*(?:no|number)|fke[ \t]*no|old[ \t]*passport|denl|"
            r"place[ \t]*of|father|mother",
        )
        spouse = _name_from_block(spouse_block) or _person_name_after_label(
            raw,
            spouse_label,
        )
        if spouse and re.search(r"(?i)^(den|address|room)\b", spouse):
            spouse = None
        if not spouse:
            sm = re.search(
                r"(?s)(?:[Nn]ame[ \t]*(?:of|ot)[ \t]*(?:spouse|spouce)|"
                r"(?:[Ss]pouse|[Ss]pouce)(?:'s)?[ \t]*name)"
                r"[^\n]{0,40}\n"
                r"([A-Z][A-Za-z .']{4,100}(?:\n[A-Z][A-Za-z.']{2,40}){0,3})",
                raw,
            )
            if sm and not re.match(
                r"(?i)^(den|address|room|file|old)", sm.group(1).strip()
            ):
                spouse = _clean_person_name(re.sub(r"\s+", " ", sm.group(1)))
    if block_spouse and (
        not spouse
        or _PARENT_NAME_JUNK_RE.search(spouse or "")
        or _has_trailing_name_crumb(spouse)
        or len(block_spouse.split()) >= len((spouse or "").split())
    ):
        spouse = block_spouse
    spouse = _strip_trailing_name_crumbs(spouse)
    spouse = retain_if_valid_value(
        "spouse_name",
        spouse,
        shape_ok=lambda v: (
            not _is_blank_spouse_value(v)
            and _is_plausible_person_name(v)
            and not _PARENT_NAME_JUNK_RE.search(v)
        ),
    )
    if spouse and (
        (father and spouse.upper() == father.upper())
        or (mother and spouse.upper() == mother.upper())
    ):
        spouse = None
    if spouse:
        found["spouse_name"] = spouse

    addr_joined = _address_from_ocr_text(raw)
    if not addr_joined:
        addr = _value_after_label(
            raw,
            r"address|denl[ \t]*/[ \t]*address|qa[ \t]*/[ \t]*address|residential[ \t]*address",
        )
        if addr and (
            _is_noise_value(addr)
            or re.match(r"(?i)^(a3\s*/\s*f\s*no|file|fileno|f\.?\s*no|fke)", addr)
            or len(addr) < 8
            or _looks_like_date_value(addr)
        ):
            addr = None
        if not addr:
            # Indian page-2 address often starts at ROOM / door / BLOCK after labels.
            am = re.search(
                r"(?im)^((?:ROOM|H\.?\s*NO|D\.?\s*NO|DOOR|FLAT|HOUSE|BLOCK)[^\n]{5,160})$",
                raw,
            )
            if am:
                addr = am.group(1).strip()
        if not addr:
            # Same-line family OCR: "... LAKXMI ARAVIND BLOCK 3 C 1 JAINS ..."
            am2 = re.search(
                r"(?i)\b((?:BLOCK|H\.?\s*NO\.?|D\.?\s*NO\.?|ROOM)\s+[A-Z0-9][A-Z0-9 ,.\-/]{8,160})",
                raw,
            )
            if am2:
                addr = am2.group(1).strip()
        if addr and not _is_noise_value(addr):
            lines = [addr]
            idx = raw.lower().find(addr.lower())
            if idx >= 0:
                for ln in raw[idx + len(addr) :].splitlines()[:10]:
                    t = ln.strip()
                    if not t:
                        if len(lines) == 1:
                            continue
                        break
                    if re.match(
                        r"(?i)^(old passport|name of|file|fileno|passport|fke|ma\s*3)",
                        t,
                    ):
                        break
                    lines.append(t)
                    if re.search(
                        r"(?i)\bpin\s*:?\s*\d{6}\b|\b\d{6}\b.*(?:pradesh|india|nadu)",
                        t,
                    ):
                        break
            addr_joined = normalize_multiline_address("\n".join(lines)[:400])
    if addr_joined:
        # Never keep a bare Place-of-Birth city as the whole address.
        pob_u = str(found.get("place_of_birth") or "").strip().upper()
        if pob_u and addr_joined.strip().upper() == pob_u:
            addr_joined = None
        if addr_joined and len(addr_joined) >= 12:
            found["address"] = addr_joined

    block_addr = _address_from_ocr_blocks(ocr_blocks)
    if block_addr and not found.get("address"):
        found["address"] = block_addr
    elif block_addr and found.get("address"):
        # Prefer longer spatial address over a short text crumb.
        if len(block_addr) > len(str(found["address"])):
            found["address"] = block_addr

    # Prefer a full BLOCK/H.NO street line from raw OCR over a truncated crumb.
    found_addr = str(found.get("address") or "")
    street_m = re.search(
        r"(?i)\b((?:BLOCK|H\.?\s*NO\.?|D\.?\s*NO\.?|ROOM)\s+"
        r"[A-Z0-9][A-Z0-9 ,./\-]{8,160})",
        raw or "",
    )
    if street_m:
        street = re.sub(r"\s+", " ", street_m.group(1)).strip(" ,")
        street = re.split(
            r"(?i)\b(?:old\s*passport|file\s*no|pin\b|zameen\b)",
            street,
            maxsplit=1,
        )[0].strip(" ,")
        if street and len(street) >= 12:
            if not found_addr:
                found["address"] = street
            elif re.search(r"(?i)\bblok\b", found_addr) or len(street) > len(
                found_addr.split(",")[0]
            ):
                # Keep locality / PIN tails; replace only the truncated first line.
                parts = [p.strip() for p in found_addr.split(",") if p.strip()]
                if parts and (
                    re.search(r"(?i)\b(?:blok|block|h\.?\s*no|room)\b", parts[0])
                    or len(parts[0]) < 16
                ):
                    parts[0] = street
                    found["address"] = normalize_multiline_address(", ".join(parts))
                elif street.upper() not in found_addr.upper():
                    found["address"] = normalize_multiline_address(
                        f"{street}, {found_addr}"
                    )

    file_no = _value_after_label(
        raw,
        r"file[ \t]*(?:no\.?|number)|fileno|a3[ \t]*/[ \t]*f[ \t]*no|"
        r"f\.?[ \t]*no\.?|fke[ \t]*no\.?|ma[ \t]*3[ \t]*/[ \t]*fke",
    )
    file_cand: str | None = None
    if file_no:
        # Prefer alphanumeric file tokens (letter+digits). Reject pure date runs.
        token = re.search(
            r"\b([A-Z]{1,5}\d{6,14}[A-Z0-9]{0,4}|\d{1,4}[A-Z]{1,5}\d{6,14})\b",
            file_no.upper(),
        )
        if not token:
            token = re.search(
                r"\b([A-Z][A-Z0-9]{5,16})\b",
                file_no.upper(),
            )
        if token:
            cand = token.group(1)
            if not re.fullmatch(r"\d{6,14}", cand) and not re.search(
                r"(?i)ROOM|PIN|ADDR|INDIA|PASSPORT|CHENNAI|MUMBAI|DELHI", cand
            ):
                file_cand = cand
    if not file_cand:
        # Margin stamp near File No / A3/F No / FILENO on page 2 — scan nearby lines.
        near = re.search(
            r"(?is)(?:file[ \t]*(?:no\.?|number)|fileno|a3[ \t]*/[ \t]*f[ \t]*no|"
            r"fke[ \t]*no\.?|ma[ \t]*3[ \t]*/[ \t]*fke)"
            r".{0,160}?\b([A-Z]{1,5}\d{6,14}[A-Z0-9]{0,4})\b",
            raw,
        )
        if near:
            file_cand = near.group(1).upper()
    if not file_cand:
        # Standalone Indian-style file tokens away from MRZ (avoid passport no.).
        for m in re.finditer(
            r"(?i)\b([A-Z]{2,5}\d{6,14})\b",
            raw,
        ):
            tok = m.group(1).upper()
            if found.get("document_number") and tok == str(
                found["document_number"]
            ).upper():
                continue
            if re.fullmatch(r"[A-Z]\d{7}", tok):
                # Looks like passport number — skip unless labeled as file.
                continue
            file_cand = tok
            break
    # Prefer spatially linked OCR-block file number (often cleaner than text).
    if block_file and (
        not file_cand
        or _PASSPORT_NO_SHAPE_RE.match(file_cand)
        or (file_cand.isdigit() and not block_file.isdigit())
    ):
        file_cand = block_file
    if file_cand and found.get("document_number"):
        if file_cand.upper() == str(found["document_number"]).upper():
            file_cand = block_file
    if file_cand and not _is_garbage_file_number(file_cand):
        found["file_number"] = file_cand
    elif block_file and not _is_garbage_file_number(block_file):
        found["file_number"] = block_file
    # Never copy passport number or date crumbs into file_number.
    # Compact CamScanner family line (all names + address on one OCR row):
    # "Name of Father/Legal Guardian SUNDARAM ANNADURAI … VENKATRAMAN NAGALAKSHMI / LAKXMI ARAVIND BLOCK…"
    fam_line = re.search(
        r"(?is)name\s*(?:of|ot)\s*father(?:\s*/\s*legal\s*guardian)?\s+"
        r"([A-Z][A-Z .']{4,50}?)"
        r"(?:\s+(?:s\s*o\s*a|s\s*tes|[/|]|name\s*(?:of|ot)\s*mother|mother)[^\nA-Z]*){0,6}"
        r"([A-Z][A-Z .']{4,50}?)\s*/\s*([A-Z][A-Z .']{4,50}?)\s+"
        r"((?:BLOCK|H\.?\s*NO\.?|D\.?\s*NO\.?|ROOM|FLAT)\b.*)",
        raw,
    )
    if not fam_line and not found.get("father_name"):
        fam_line = re.search(
            r"(?i)\b([A-Z]{3,}(?:[ \t]+[A-Z]{3,}){1,3})\b"
            r"(?:\s+\S+){0,6}\s+"
            r"([A-Z]{3,}(?:[ \t]+[A-Z]{3,}){1,3})\s+"
            r"name\s*(?:of|ot)\s*spouse\s+"
            r"([A-Z]{3,}(?:[ \t]+[A-Z]{3,}){0,3})",
            raw,
        )
    if fam_line:
        f_name = _clean_person_name(fam_line.group(1))
        m_name = _clean_person_name(
            re.sub(r"(?i)^(s\s*tes|s\s*o\s*a|tes)\s+", "", fam_line.group(2) or "")
        )
        s_name = _clean_person_name(fam_line.group(3))
        if f_name and _is_plausible_person_name(f_name):
            found["father_name"] = f_name
            father = f_name
        if m_name and _is_plausible_person_name(m_name):
            found["mother_name"] = m_name
            mother = m_name
        if (
            s_name
            and _is_plausible_person_name(s_name)
            and (not father or s_name.upper() != father.upper())
            and (not mother or s_name.upper() != mother.upper())
        ):
            found["spouse_name"] = s_name
            spouse = s_name
        addr_tail = fam_line.group(4) if fam_line.lastindex and fam_line.lastindex >= 4 else None
        if addr_tail:
            # Stop before old-passport / file / PIN crumbs.
            addr_tail = re.split(
                r"(?i)\b(?:old\s*passport|file\s*no|pin\b|\d{1,2}\s+\d{1,2}\s+\d{2,4}|"
                r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|k\d{7}|ma\d{10,}|\bpdia\b)",
                addr_tail,
                maxsplit=1,
            )[0]
            addr_tail = re.sub(r"(?i)\s+\b(?:ddy|den|qa)\s*/\s*", ", ", addr_tail)
            joined = normalize_multiline_address(addr_tail[:400])
            if joined and len(joined) >= 12:
                # Prefer cleaned fam-line address over a polluted earlier capture.
                prev = str(found.get("address") or "")
                if (
                    not prev
                    or len(joined) >= 12
                    and (
                        re.search(r"(?i)\b(?:pdia|k\d{7}|ma\d{10,})\b", prev)
                        or len(joined) >= len(prev) * 0.6
                    )
                ):
                    found["address"] = joined

    # Label-less family page (CamScanner dropped Father/Mother/Spouse anchors).
    # Cover-note junk ("BY ORDER") must never block a 3-name unlabeled row.
    def _parent_slot_usable(val: str | None) -> bool:
        if not val:
            return False
        if _PARENT_NAME_JUNK_RE.search(val):
            return False
        return bool(_is_plausible_person_name(val))

    if not _parent_slot_usable(found.get("father_name")) and not _parent_slot_usable(
        found.get("mother_name")
    ):
        unlabeled = _unlabeled_family_row_from_blocks(ocr_blocks)
        for key in ("father_name", "mother_name", "address"):
            cand = unlabeled.get(key)
            if not cand:
                continue
            if key in ("father_name", "mother_name"):
                if not _parent_slot_usable(found.get(key)):
                    found[key] = cand
            elif not found.get(key):
                found[key] = cand
        # Prefer the street+locality address over a locality-only crumb.
        if unlabeled.get("address") and found.get("address"):
            prev = str(found["address"])
            new = str(unlabeled["address"])
            if len(new) > len(prev) and not re.search(
                r"(?i)\b(?:pdia|k\d{7}|ma\d{10,})\b", new
            ):
                found["address"] = new

    # Surname must not equal place-of-birth city (common label-stack OCR bug).
    if (
        found.get("surname")
        and found.get("place_of_birth")
        and found["surname"].strip().upper()
        == found["place_of_birth"].strip().upper().split(",")[0].strip()
    ):
        found.pop("surname", None)

    spouse_now = found.get("spouse_name")
    if spouse_now and (
        _spouse_value_is_address_like(spouse_now, found.get("address"))
        or not _spouse_supported_by_label(spouse_now, raw, ocr_blocks)
    ):
        found.pop("spouse_name", None)

    return found


def _confidence_for_field(
    key: str,
    value: str | None,
    *,
    from_mrz: bool,
    ocr_mean: float | None,
) -> float:
    if not value:
        return 0.0
    base = 0.92 if from_mrz else 0.78
    if ocr_mean is not None:
        base = min(1.0, 0.55 * base + 0.45 * float(ocr_mean))
    if key in _CRITICAL_KEYS and from_mrz:
        base = max(base, 0.88)
    return round(max(0.0, min(1.0, base)), 4)


def _boxes_from_ocr_blocks(
    blocks: list[dict[str, Any]] | None,
    *,
    needles: list[tuple[str, str]],
) -> tuple[dict[str, list[list[float]]], dict[str, int]]:
    """Map field keys to first OCR block box + page_index whose text contains the needle."""
    if not blocks or not needles:
        return {}, {}
    out: dict[str, list[list[float]]] = {}
    pages: dict[str, int] = {}
    for key, needle in needles:
        if not needle or key in out:
            continue
        needle_u = needle.upper()
        for blk in blocks:
            text = str(
                blk.get("cleaned_text") or blk.get("text") or blk.get("raw_ocr_text") or ""
            ).upper()
            matched = False
            if needle_u[:6] and needle_u[:6] in text.replace(" ", ""):
                matched = True
            elif needle_u and needle_u in text:
                matched = True
            if not matched:
                continue
            box = blk.get("bounding_box")
            if isinstance(box, list) and len(box) >= 4:
                out[key] = box
                try:
                    pages[key] = int(blk.get("page_index") or 0)
                except (TypeError, ValueError):
                    pages[key] = 0
                break
    return out, pages


_PASSPORT_NAME_KEYS = (
    "surname",
    "given_names",
    "father_name",
    "mother_name",
    "spouse_name",
)


def _is_plausible_mrz_string(val: str | None) -> bool:
    """True when at least one line looks like TD3 line 1 or line 2."""
    for raw in str(val or "").splitlines():
        c = _normalize_mrz_candidate(raw)
        if len(c) >= 20 and (
            _looks_like_td3_line1(c) or _looks_like_td3_line2(c)
        ):
            return True
    return False


def _mrz_line1_name_parts(
    mrz_string: str | None,
) -> tuple[str | None, str | None]:
    """Return (surname, given_names) from TD3 line 1 when the << split exists."""
    for raw in str(mrz_string or "").splitlines():
        line = re.sub(r"\s+", "", (raw or "").upper())
        if not line.startswith("P") or len(line) < 10:
            continue
        names = line[5:44]
        if "<<" not in names:
            continue
        family, _, rest = names.partition("<<")
        surname = family.replace("<", " ").strip()
        given = re.sub(r"\s+", " ", rest.replace("<", " ").strip())
        surname = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "O", surname)
        given = re.sub(r"(?<=[A-Za-z])0(?=[A-Za-z])", "O", given)
        return (surname or None, given or None)
    return (None, None)


def _name_field_independently_supported(
    field_key: str,
    value: str | None,
    *,
    fields: dict[str, Any],
    labeled: dict[str, str] | None,
) -> bool:
    """True when label zone or MRZ supplies this field's own token (not a sibling copy)."""
    val = str(value or "").strip()
    if not val:
        return False
    val_u = val.upper()
    lab_raw = str((labeled or {}).get(field_key) or "").strip()
    lab = _clean_person_name(lab_raw) if lab_raw else None
    if lab and lab.upper() == val_u and _is_plausible_person_name(lab):
        return True
    mrz_sn, mrz_gn = _mrz_line1_name_parts(str(fields.get("mrz_string") or ""))
    if field_key == "surname" and mrz_sn and mrz_sn.upper() == val_u:
        return True
    if field_key == "given_names" and mrz_gn and mrz_gn.upper() == val_u:
        return True
    return False


_FAMILY_NAME_KEYS = ("father_name", "mother_name", "spouse_name")

_FATHER_TEXT_LABEL_RE = (
    r"n(?:ame|ane|eme|ere)[ \t]*(?:of|ot|ol)[ \t]*"
    r"(?:father|foter|fother|pathvet)"
    r"(?:[ \t]*/[ \t]*lega[ls]?[ \t]*(?:guardian|guardlan|gusrdian|gurdian|curdian))?|"
    r"father(?:'s)?[ \t]*name|foter|fother|name[ \t]*of[ \t]*guardian|"
    r"(?:lega[ls]?[ \t]*)?(?:guardian|guardlan|gusrdian|gurdian|curdian|uardian|quardian)|"
    r"reme[ \t]*of[ \t]*foter|lepai[ \t]*curdian|"
    r"nere[ \t]*of[ \t]*pathvet"
)
_MOTHER_TEXT_LABEL_RE = (
    r"n(?:ame|ane|eme)[ \t]*(?:of|ot|ol)[ \t]*(?:mother|mather|mothor|mathe|maches)|"
    r"mother(?:'s)?[ \t]*name|mather|mathe|name[ \t]*of[ \t]*maches"
)
_SPOUSE_TEXT_LABEL_RE = (
    r"name[ \t]*(?:of|ot)[ \t]*(?:spouse|spouce)|"
    r"spouse(?:'s)?[ \t]*name"
)


def _family_label_zone_value(
    field_key: str,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Person name from this family field's own label neighborhood only.

    Does not use cross-page ROI or left/right invent-from-neighbor fallbacks —
    those paths can copy the holder's given/surname into father/mother/spouse.
    """
    if field_key not in _FAMILY_NAME_KEYS:
        return None

    if field_key == "father_name":
        label_re = _FATHER_LABEL_FUZZY_RE
        text_label = _FATHER_TEXT_LABEL_RE
        stop_res = [
            _MOTHER_LABEL_FUZZY_RE,
            _FILE_LABEL_FUZZY_RE,
            _SPOUSE_LABEL_FUZZY_RE,
            re.compile(r"(?i)\b(?:address|old\s*passport|pin\b|room\b)\b"),
        ]
        directions: tuple[str, ...] = ("right", "below")
    elif field_key == "mother_name":
        label_re = _MOTHER_LABEL_FUZZY_RE
        text_label = _MOTHER_TEXT_LABEL_RE
        stop_res = [
            _FATHER_LABEL_FUZZY_RE,
            _FILE_LABEL_FUZZY_RE,
            _SPOUSE_LABEL_FUZZY_RE,
            re.compile(r"(?i)\b(?:address|old\s*passport|pin\b|room\b)\b"),
        ]
        directions = ("right", "below")
    else:
        label_re = _SPOUSE_LABEL_FUZZY_RE
        text_label = _SPOUSE_TEXT_LABEL_RE
        stop_res = [
            _FATHER_LABEL_FUZZY_RE,
            _MOTHER_LABEL_FUZZY_RE,
            _FILE_LABEL_FUZZY_RE,
            re.compile(r"(?i)\b(?:address|old\s*passport|pin\b|room\b)\b"),
        ]
        directions = ("below",)

    items = _ocr_block_items(ocr_blocks)
    if items:
        idxs: list[int] = []
        fi = find_label_anchor_index(items, field_key)
        if fi is not None:
            idxs.append(fi)
        for i, (_, _, _, _, _, blk_text) in enumerate(items):
            if i in idxs:
                continue
            if label_re.search(blk_text) or block_is_field_label(blk_text, field_key):
                if field_key == "father_name" and _MOTHER_LABEL_FUZZY_RE.search(blk_text):
                    continue
                idxs.append(i)
        for i in idxs:
            blk_text = items[i][5]
            same = (
                _name_from_same_box(blk_text, label_re) if label_re.search(blk_text) else None
            )
            raw = _value_near_label(
                items,
                i,
                is_value=_is_parent_name_candidate,
                stop_res=stop_res,
                directions=directions,
            )
            near = _clean_person_name(raw) if raw else None
            if near and _is_plausible_person_name(near):
                return near
            if same and _is_plausible_person_name(same):
                return same

    raw_text = text or ""
    if raw_text.strip():
        from_label = _person_name_after_label(raw_text, text_label)
        if from_label and _is_plausible_person_name(from_label):
            return from_label
        if field_key == "father_name":
            stop = (
                _MOTHER_TEXT_LABEL_RE
                + r"|address|file[ \t]*(?:no|number)|fke[ \t]*no|place[ \t]*of"
            )
        elif field_key == "mother_name":
            stop = (
                r"address|file[ \t]*(?:no|number)|fke[ \t]*no|old[ \t]*passport|denl|"
                r"name[ \t]*(?:of|ot)[ \t]*spouse|spouse(?:'s)?[ \t]*name|place[ \t]*of"
            )
        else:
            stop = (
                r"address|file[ \t]*(?:no|number)|fke[ \t]*no|old[ \t]*passport|denl|"
                r"place[ \t]*of|father|mother"
            )
        block = _slice_between_labels(raw_text, text_label, stop)
        from_block = _name_from_block(block) if block else None
        if from_block and _is_plausible_person_name(from_block):
            return from_block
    return None


def _family_field_independently_supported(
    field_key: str,
    value: str | None,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> bool:
    """True when a Father/Mother/Spouse label zone independently yields this value.

    Does not trust ``labeled[field_key]`` — that dict may already hold a
    cross-filled holder given/surname from ROI or neighbor invent paths.
    """
    val = str(value or "").strip()
    if not val or field_key not in _FAMILY_NAME_KEYS:
        return False
    zone = _family_label_zone_value(
        field_key, text=text, ocr_blocks=ocr_blocks
    )
    if not zone:
        return False
    return zone.strip().upper() == val.upper()


def _reject_cross_filled_holder_names(
    out: dict[str, Any],
    *,
    labeled: dict[str, str] | None,
    text: str | None = None,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> None:
    """Blank names that only exist as copies of another name field.

    Surname and given names may legitimately match only when each side has its
    own label/MRZ evidence. Father/mother/spouse must not equal the holder's
    given name or surname unless that family field's own label zone yields the
    same string independently.
    """
    sn = str(out.get("surname") or "").strip()
    gn = str(out.get("given_names") or "").strip()
    if sn and gn and sn.upper() == gn.upper():
        sn_ok = _name_field_independently_supported(
            "surname", sn, fields=out, labeled=labeled
        )
        gn_ok = _name_field_independently_supported(
            "given_names", gn, fields=out, labeled=labeled
        )
        if not sn_ok:
            out["surname"] = None
            sn = ""
        if not gn_ok:
            out["given_names"] = None
            gn = ""

    holder = {
        v.strip().upper()
        for v in (sn, gn)
        if v and str(v).strip()
    }
    if not holder:
        return
    # Without OCR text/blocks we cannot re-verify Father/Mother label zones —
    # keep values that already survived extract_passport_fields (e.g. father
    # legitimately equal to surname when the Father label yielded it).
    if not (text or "").strip() and not ocr_blocks:
        return
    for key in _FAMILY_NAME_KEYS:
        val = str(out.get(key) or "").strip()
        if not val or val.upper() not in holder:
            continue
        if _family_field_independently_supported(
            key, val, text=text, ocr_blocks=ocr_blocks
        ):
            continue
        out[key] = None


def _mother_name_on_own_label(
    mother: str | None,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> bool:
    """True when this mother name is the value of a mother label, not a father suffix."""
    target = str(mother or "").strip()
    if not target:
        return False
    zone = _family_label_zone_value(
        "mother_name", text=text, ocr_blocks=ocr_blocks
    )
    if zone and zone.strip().upper() == target.upper():
        return True
    if zone and zone.strip().upper() != target.upper():
        return False
    has_label = False
    has_value = False
    for blk in ocr_blocks or []:
        if not isinstance(blk, dict):
            continue
        blob = _block_text(blk)
        if not blob:
            continue
        if _MOTHER_LABEL_FUZZY_RE.search(blob) and not _FATHER_LABEL_FUZZY_RE.search(blob):
            has_label = True
        cleaned = _clean_person_name(blob)
        if (
            cleaned
            and cleaned.upper() == target.upper()
            and not _MOTHER_LABEL_FUZZY_RE.search(blob)
            and not _FATHER_LABEL_FUZZY_RE.search(blob)
        ):
            has_value = True
    return has_label and has_value


def _strip_trailing_mother_from_father(
    father: str | None,
    mother: str | None,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Drop a trailing mother name from father when that mother has her own label.

    The mother field is not modified and is not copied into father. A father
    name is left unchanged when the mother label does not independently show
    that name.
    """
    father_s = str(father or "").strip()
    mother_s = str(mother or "").strip()
    if not father_s or not mother_s:
        return father if father_s else None
    f_parts = father_s.split()
    m_parts = mother_s.split()
    if len(m_parts) < 2 or len(f_parts) <= len(m_parts):
        return father_s
    if [p.upper() for p in f_parts[-len(m_parts) :]] != [p.upper() for p in m_parts]:
        return father_s
    if not _mother_name_on_own_label(
        mother_s, text=text, ocr_blocks=ocr_blocks
    ):
        return father_s
    trimmed = " ".join(f_parts[: -len(m_parts)]).strip()
    if (
        not trimmed
        or trimmed.upper() == mother_s.upper()
        or not _is_plausible_person_name(trimmed)
    ):
        return father_s
    return trimmed


def _father_name_on_own_label(
    father: str | None,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> bool:
    """True when this father name is the value of a father label, not a mother suffix."""
    target = str(father or "").strip()
    if not target:
        return False
    zone = _family_label_zone_value(
        "father_name", text=text, ocr_blocks=ocr_blocks
    )
    if zone and zone.strip().upper() == target.upper():
        return True
    if zone and zone.strip().upper() != target.upper():
        return False
    has_label = False
    has_value = False
    for blk in ocr_blocks or []:
        if not isinstance(blk, dict):
            continue
        blob = _block_text(blk)
        if not blob:
            continue
        if _FATHER_LABEL_FUZZY_RE.search(blob) and not _MOTHER_LABEL_FUZZY_RE.search(blob):
            has_label = True
        cleaned = _clean_person_name(blob)
        if (
            cleaned
            and cleaned.upper() == target.upper()
            and not _MOTHER_LABEL_FUZZY_RE.search(blob)
            and not _FATHER_LABEL_FUZZY_RE.search(blob)
        ):
            has_value = True
    return has_label and has_value


def _strip_leading_father_portion_from_mother(
    mother: str | None,
    father: str | None,
) -> str | None:
    """Drop a father-name prefix from mother. The mother value stays hers.

    The prefix may be the whole father name or a portion of it (a leading
    token run that is a prefix or a suffix of the father tokens). A mother
    name that does not start with that portion is unchanged.
    """
    mother_s = str(mother or "").strip()
    father_s = str(father or "").strip()
    if not mother_s or not father_s:
        return mother if mother_s else None
    m_parts = mother_s.split()
    f_parts = father_s.split()
    if len(m_parts) < 2 or not f_parts:
        return mother_s
    m_up = [part.upper() for part in m_parts]
    f_up = [part.upper() for part in f_parts]
    best = 0
    for count in range(1, len(m_parts)):
        head = m_up[:count]
        is_prefix = count <= len(f_up) and head == f_up[:count]
        is_suffix = count <= len(f_up) and head == f_up[-count:]
        if is_prefix or is_suffix:
            best = count
    if best == 0:
        return mother_s
    trimmed = " ".join(m_parts[best:]).strip()
    if (
        not trimmed
        or trimmed.upper() == father_s.upper()
        or not _is_plausible_person_name(trimmed)
    ):
        return mother_s
    return trimmed


def _strip_trailing_father_from_mother(
    mother: str | None,
    father: str | None,
    *,
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> str | None:
    """Drop a trailing father name from mother when that father has his own label."""
    mother_s = str(mother or "").strip()
    father_s = str(father or "").strip()
    if not mother_s or not father_s:
        return mother if mother_s else None
    m_parts = mother_s.split()
    f_parts = father_s.split()
    if len(f_parts) < 2 or len(m_parts) <= len(f_parts):
        return mother_s
    if [p.upper() for p in m_parts[-len(f_parts) :]] != [p.upper() for p in f_parts]:
        return mother_s
    if not _father_name_on_own_label(father_s, text=text, ocr_blocks=ocr_blocks):
        return mother_s
    trimmed = " ".join(m_parts[: -len(f_parts)]).strip()
    if (
        not trimmed
        or trimmed.upper() == father_s.upper()
        or not _is_plausible_person_name(trimmed)
    ):
        return mother_s
    return trimmed


def _post_validate_passport_fields(
    fields: dict[str, Any],
    *,
    text: str | None = None,
    ocr_blocks: list[dict[str, Any]] | None = None,
    labeled: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Shared final gate: strip label/passport-no bleed from names, blank spouse, DOI OCR."""
    out = dict(fields) if isinstance(fields, dict) else {}
    if text:
        original_text = text
        stripped_text = strip_non_passport_comments(original_text)
        if stripped_text != original_text:
            ocr_blocks = _filter_ocr_blocks_after_comment_strip(
                ocr_blocks, original_text, stripped_text
            )
            text = stripped_text

    for nk in _PASSPORT_NAME_KEYS:
        val = str(out.get(nk) or "").strip()
        if not val:
            out[nk] = None
            continue
        cleaned = _clean_person_name(val)
        if (
            not cleaned
            or not _is_plausible_person_name(cleaned)
            or _PARENT_NAME_JUNK_RE.search(cleaned)
        ):
            out[nk] = None
        else:
            out[nk] = cleaned

    stripped_father = _strip_trailing_mother_from_father(
        str(out.get("father_name") or "") or None,
        str(out.get("mother_name") or "") or None,
        text=text,
        ocr_blocks=ocr_blocks,
    )
    if stripped_father:
        out["father_name"] = stripped_father
    out["mother_name"] = _strip_leading_father_portion_from_mother(
        str(out.get("mother_name") or "") or None,
        str(out.get("father_name") or "") or None,
    )
    stripped_mother = _strip_trailing_father_from_mother(
        str(out.get("mother_name") or "") or None,
        str(out.get("father_name") or "") or None,
        text=text,
        ocr_blocks=ocr_blocks,
    )
    if stripped_mother:
        out["mother_name"] = stripped_mother

    _reject_cross_filled_holder_names(
        out, labeled=labeled, text=text, ocr_blocks=ocr_blocks
    )

    # Universal non-destructive rule: never clear a field solely because its
    # label was garbled/missing. Value-shape / blank / parent-bleed still clear junk.
    if out.get("spouse_name"):
        kept = retain_if_valid_value(
            "spouse_name",
            out["spouse_name"],
            shape_ok=lambda v: (
                not _is_blank_spouse_value(v)
                and _is_plausible_person_name(v)
                and not _spouse_value_is_address_like(v, str(out.get("address") or ""))
            ),
        )
        out["spouse_name"] = kept
        if out.get("spouse_name") and _spouse_value_is_address_like(
            str(out.get("spouse_name") or ""),
            str(out.get("address") or ""),
        ):
            out["spouse_name"] = None
        if out.get("spouse_name"):
            sv = str(out["spouse_name"]).strip().upper()
            fv = str(out.get("father_name") or "").strip().upper()
            mv = str(out.get("mother_name") or "").strip().upper()
            sn = str(out.get("surname") or "").strip().upper()
            poi = str(out.get("place_of_issue") or "").strip().upper()
            pob = str(out.get("place_of_birth") or "").strip().upper()
            if sv and (sv == fv or sv == mv or sv == sn):
                out["spouse_name"] = None
            elif sv and (sv == poi or sv == pob or sv in poi or sv in pob):
                out["spouse_name"] = None
            elif re.search(
                r"(?i)\b(?:hyderabad|chennai|mumbai|delhi|bengaluru|bangalore|"
                r"kolkata|pune|jaipur|ahmedabad|lucknow|patna|kochi|trivandrum|"
                r"thiruvananthapuram|india|telangana|maharashtra|tamil\s*nadu|"
                r"karnataka|kerala|andhra|pradesh)\b",
                str(out.get("spouse_name") or ""),
            ):
                out["spouse_name"] = None
            elif len(sv.split()) < 2:
                # Single-token spouse is almost always surname/place bleed.
                out["spouse_name"] = None

    if not out.get("date_of_issue"):
        doi = _complete_passport_date((labeled or {}).get("date_of_issue"))
        if doi:
            out["date_of_issue"] = doi
        elif text:
            recovered = _extract_labeled_fields(text, ocr_blocks=ocr_blocks)
            if recovered.get("date_of_issue"):
                out["date_of_issue"] = recovered["date_of_issue"]

    fno = str(out.get("file_number") or "").strip()
    labeled_fno = str((labeled or {}).get("file_number") or "").strip()
    if fno and _is_garbage_file_number(fno):
        out["file_number"] = None
        fno = ""
    if labeled_fno and _is_garbage_file_number(labeled_fno):
        labeled_fno = ""
    if not fno and labeled_fno:
        out["file_number"] = labeled_fno
    elif out.get("file_number") and _is_garbage_file_number(str(out["file_number"])):
        out["file_number"] = None

    # Structural OCR junk → blank for free-text passport fields.
    for text_key in (
        "place_of_birth",
        "place_of_issue",
        "address",
        "surname",
        "given_names",
        "father_name",
        "mother_name",
        "spouse_name",
    ):
        raw_val = str(out.get(text_key) or "").strip()
        if raw_val and _is_ocr_junk_text_value(raw_val):
            out[text_key] = None

    if out.get("mrz_string") and not _is_plausible_mrz_string(str(out["mrz_string"])):
        out["mrz_string"] = None

    if out.get("date_of_birth") and text and _date_only_in_old_passport_context(
        text, str(out["date_of_birth"])
    ):
        out["date_of_birth"] = None

    for date_key in ("date_of_birth", "date_of_issue", "date_of_expiry"):
        out[date_key] = _complete_passport_date(str(out.get(date_key) or "") or None)

    if text and (not out.get("date_of_issue") or not out.get("date_of_expiry")):
        paired_issue, paired_expiry = _issue_expiry_from_paired_date_line(text)
        if paired_issue and not out.get("date_of_issue"):
            out["date_of_issue"] = paired_issue
        if paired_expiry and not out.get("date_of_expiry"):
            out["date_of_expiry"] = paired_expiry
    if text and not out.get("date_of_issue"):
        before_issue = _date_before_issue_label(text)
        if before_issue and before_issue != out.get("date_of_birth"):
            out["date_of_issue"] = before_issue

    holder_surname = str(out.get("surname") or (labeled or {}).get("surname") or "")
    holder_given = str(out.get("given_names") or (labeled or {}).get("given_names") or "")
    pob_now = str(out.get("place_of_birth") or "").strip()
    if pob_now:
        split_pob = _split_glued_city_state(pob_now)
        if split_pob:
            out["place_of_birth"] = split_pob
        if _place_value_is_label_junk(str(out.get("place_of_birth") or "")):
            out["place_of_birth"] = None
    if text:
        recovered_pob = _birth_after_short_place_label(text) or _city_state_before_birth_label(
            text
        )
        current_pob = str(out.get("place_of_birth") or "")
        current_has_state = bool(
            re.search(
                r"(?i)\b(?:pradesh|nadu|khand|bengal|maharashtra|kerala|gujarat|"
                r"telangana|karnataka)\b",
                current_pob,
            )
        )
        if recovered_pob and (not current_pob or not current_has_state):
            out["place_of_birth"] = recovered_pob
    if not out.get("place_of_issue") and text:
        issue_city = _issue_city_before_garbled_label(text) or _issue_city_on_garbled_label(
            text
        )
        if issue_city and _is_issuing_office_candidate(
            issue_city, surname=holder_surname, given_names=holder_given
        ):
            out["place_of_issue"] = issue_city
    if out.get("address"):
        out["address"] = _tidy_passport_address(str(out.get("address") or ""))
    if out.get("address") and text:
        out["address"] = _strip_stamp_locality_tail(str(out["address"]), text)
    if out.get("spouse_name") and _name_is_notary_neighbor(
        str(out.get("spouse_name") or ""),
        [ln for ln in (text or "").splitlines()]
        + [
            _block_text(blk)
            for blk in (ocr_blocks or [])
            if isinstance(blk, dict)
        ],
    ):
        out["spouse_name"] = None
    if out.get("address") and text and not _value_grounded_in_text(
        str(out["address"]), text, ocr_blocks
    ):
        out["address"] = None

    return out


def extract_passport_fields(
    text: str,
    *,
    ocr_blocks: list[dict[str, Any]] | None = None,
    ocr_mean_confidence: float | None = None,
) -> dict[str, Any]:
    """Return passport schema dict with confidence_scores / bounding_boxes / flags."""
    # Notary, attestation, and true-copy stamps must not become fields and
    # must not hide a passport page that still has biodata or an MRZ.
    original_text = text or ""
    stripped_text = strip_non_passport_comments(original_text)
    if stripped_text != original_text:
        ocr_blocks = _filter_ocr_blocks_after_comment_strip(
            ocr_blocks, original_text, stripped_text
        )
        text = stripped_text
    labeled = _extract_labeled_fields(text, ocr_blocks=ocr_blocks)
    mrz_lines = extract_mrz_lines(text)
    # Supplement MRZ candidates from OCR blocks (line 2 often only in blocks).
    if ocr_blocks:
        block_text = "\n".join(
            str(
                blk.get("cleaned_text")
                or blk.get("text")
                or blk.get("raw_ocr_text")
                or ""
            )
            for blk in ocr_blocks
            if isinstance(blk, dict)
        )
        for ln in extract_mrz_lines(block_text):
            if ln not in mrz_lines:
                mrz_lines.append(ln)
    doc_hint = None
    for cand in (
        labeled.get("document_number"),
        # Visual passport number often appears as a lone S####### block.
        *(
            str(
                blk.get("cleaned_text")
                or blk.get("text")
                or blk.get("raw_ocr_text")
                or ""
            ).strip()
            for blk in (ocr_blocks or [])
            if isinstance(blk, dict)
        ),
    ):
        tok = re.sub(r"[\s\-]", "", str(cand or "")).upper()
        if _PASSPORT_NO_SHAPE_RE.match(tok):
            doc_hint = tok
            break
    mrz = parse_td3_mrz(mrz_lines, doc_number_hint=doc_hint) if mrz_lines else {}
    # If MRZ still looks misaligned, retry once with the visual passport number.
    if mrz.get("_mrz_misaligned") and doc_hint:
        mrz = parse_td3_mrz(mrz_lines, doc_number_hint=doc_hint)

    fields: dict[str, Any] = {k: None for k in PASSPORT_FIELD_KEYS}
    from_mrz_keys: set[str] = set()

    # Prefer MRZ for identity/doc core; visual zone fills the rest (places, page 2).
    mrz_priority = {
        "surname",
        "given_names",
        "date_of_birth",
        "sex",
        "nationality",
        "document_number",
        "document_type",
        "country_code",
        "date_of_expiry",
        "mrz_string",
    }
    for key in PASSPORT_FIELD_KEYS:
        if key == "mrz_string":
            continue
        if key in mrz_priority and key in mrz and mrz[key]:
            fields[key] = mrz[key]
            from_mrz_keys.add(key)
        elif key in labeled and labeled[key]:
            fields[key] = labeled[key]

    # Fill remaining from the other source.
    for key in PASSPORT_FIELD_KEYS:
        if fields.get(key):
            continue
        if key in mrz and mrz[key]:
            fields[key] = mrz[key]
            from_mrz_keys.add(key)
        elif key in labeled and labeled[key]:
            fields[key] = labeled[key]

    if mrz.get("mrz_string"):
        fields["mrz_string"] = mrz["mrz_string"]
    elif mrz_lines:
        fields["mrz_string"] = "\n".join(mrz_lines[:3])

    # Prefer an explicit two-line MRZ when heuristics only captured line 1.
    if fields.get("mrz_string") and "\n" not in str(fields["mrz_string"]):
        l2 = next((ln for ln in mrz_lines if _looks_like_td3_line2(ln)), None)
        l1 = next((ln for ln in mrz_lines if _looks_like_td3_line1(ln)), None)
        if l1 and l2:
            fields["mrz_string"] = f"{(l1 + ('<' * 44))[:44]}\n{(l2 + ('<' * 44))[:44]}"
            fields.pop("_mrz_incomplete", None)
    # If mrz_string somehow starts with a fake P-line, rebuild from good candidates.
    ms = str(fields.get("mrz_string") or "")
    first = ms.split("\n", 1)[0]
    if ms and not _looks_like_td3_line1(_normalize_mrz_candidate(first)):
        l1 = next((ln for ln in mrz_lines if _looks_like_td3_line1(ln)), None)
        l2 = next((ln for ln in mrz_lines if _looks_like_td3_line2(ln)), None)
        if l1 and l2:
            fields["mrz_string"] = f"{(l1 + ('<' * 44))[:44]}\n{(l2 + ('<' * 44))[:44]}"
        elif l1:
            fields["mrz_string"] = (l1 + ("<" * 44))[:44]
        elif l2:
            fields["mrz_string"] = (l2 + ("<" * 44))[:44]
        else:
            fields["mrz_string"] = None
    if fields.get("mrz_string") and not _is_plausible_mrz_string(str(fields["mrz_string"])):
        fields["mrz_string"] = None

    if fields.get("address"):
        fields["address"] = normalize_multiline_address(str(fields["address"]))

    # Never invent document_type=P on empty / failed OCR. Only fill the ICAO
    # type letter when MRZ line 1 or other passport evidence was actually read.
    if not fields.get("document_type"):
        has_passport_evidence = any(
            fields.get(k)
            for k in (
                "document_number",
                "surname",
                "given_names",
                "date_of_birth",
                "date_of_expiry",
            )
        ) or _is_plausible_mrz_string(str(fields.get("mrz_string") or ""))
        if has_passport_evidence:
            fields["document_type"] = "P"

    # Drop OCR bleed garbage before LLM so Ollama can refill nationality.
    if fields.get("nationality") and not is_plausible_nationality(str(fields["nationality"])):
        fields["nationality"] = None

    # Ollama refinement: fill blanks from spatially sorted OCR (never invents over
    # heuristic/MRZ values). Lazy import avoids circular deps.
    try:
        from app.services.scanx_llm_passport import refine_passport_fields_via_llm

        filled = refine_passport_fields_via_llm(text, existing=fields)
        for key, val in (filled or {}).items():
            if key not in PASSPORT_FIELD_KEYS:
                continue
            if fields.get(key):
                continue
            # Never fill a blank by copying another already-captured field.
            val_s = str(val or "").strip()
            if val_s:
                sibling_hit = False
                for other_key in PASSPORT_FIELD_KEYS:
                    if other_key == key:
                        continue
                    other = str(fields.get(other_key) or "").strip()
                    if other and other.upper() == val_s.upper():
                        sibling_hit = True
                        break
                if sibling_hit:
                    continue
            if key == "nationality":
                demonym, nat_code = resolve_nationality(str(val))
                if not demonym:
                    continue
                fields[key] = demonym
                if nat_code and not fields.get("country_code"):
                    fields["country_code"] = nat_code
                continue
            if key == "country_code":
                code_v = _to_alpha3(str(val))
                if code_v and code_v in _VALID_ALPHA3:
                    fields[key] = code_v
                continue
            if key in {"surname", "given_names", "father_name", "mother_name", "spouse_name"}:
                if not _is_plausible_person_name(str(val)):
                    continue
                fields[key] = _clean_person_name(str(val))
                continue
            if key == "address":
                fields[key] = normalize_multiline_address(str(val))
            else:
                fields[key] = val
    except Exception:
        logger.debug("ScanX passport LLM refine skipped", exc_info=True)

    # Drop LLM/heuristic fills that lack their own label or MRZ evidence.
    # Blank stays blank — never keep a sibling copy or last-page invent.
    for key in ("surname", "given_names"):
        val = str(fields.get(key) or "").strip()
        if not val:
            continue
        if key in from_mrz_keys:
            continue
        if _name_field_independently_supported(
            key, val, fields=fields, labeled=labeled
        ):
            continue
        fields[key] = None
    for key in _FAMILY_NAME_KEYS:
        val = str(fields.get(key) or "").strip()
        if not val:
            continue
        if _family_field_independently_supported(
            key, val, text=text, ocr_blocks=ocr_blocks
        ):
            continue
        # Keep labeled values that already passed the father/mother extractors.
        lab = str(labeled.get(key) or "").strip()
        if lab and lab.upper() == val.upper() and _is_plausible_person_name(lab):
            continue
        fields[key] = None
    if fields.get("mrz_string") and not _is_plausible_mrz_string(str(fields["mrz_string"])):
        fields["mrz_string"] = None
    if fields.get("date_of_birth") and _date_only_in_old_passport_context(
        text or "", str(fields["date_of_birth"])
    ):
        # Prefer labeled/MRZ DOB; clear invents from Old Passport stamp dates.
        if "date_of_birth" not in from_mrz_keys and not labeled.get("date_of_birth"):
            fields["date_of_birth"] = None
        elif labeled.get("date_of_birth") and not _date_only_in_old_passport_context(
            text or "", str(labeled["date_of_birth"])
        ):
            fields["date_of_birth"] = labeled["date_of_birth"]
        elif "date_of_birth" not in from_mrz_keys:
            fields["date_of_birth"] = None
    if (
        fields.get("date_of_birth")
        and "date_of_birth" not in from_mrz_keys
        and not _date_evidenced_in_text(text or "", str(fields["date_of_birth"]))
    ):
        fields["date_of_birth"] = None
    # Nationality / sex / country invents need OCR evidence (combo line, label, MRZ).
    if fields.get("nationality") and "nationality" not in from_mrz_keys:
        nat_u = str(fields["nationality"]).strip().upper()
        if nat_u and not re.search(
            rf"(?i)\b{re.escape(nat_u)}\b|\brepublic\s+of\s+india\b|\bindian\b",
            text or "",
        ):
            if not labeled.get("nationality"):
                fields["nationality"] = None
    if fields.get("country_code") and "country_code" not in from_mrz_keys:
        if not re.search(
            r"(?i)\brepublic\s+of\s+india\b|\bindian\b|\bIND\b|P<IND",
            text or "",
        ) and not labeled.get("country_code") and not labeled.get("nationality"):
            # Bare ",INDIA" in an address line is not nationality evidence.
            if not re.search(r"(?i)\bINDIAN\b", text or ""):
                fields["country_code"] = None
    if fields.get("sex") and "sex" not in from_mrz_keys and not labeled.get("sex"):
        sex_u = str(fields["sex"]).strip().upper()
        if sex_u and not re.search(
            rf"(?i)(?:\bsex\b|\bgender\b).*?\b{re.escape(sex_u)}\b|"
            rf"\b(?:INDIAN|IND)\s+{re.escape(sex_u)}\b|"
            rf"\b{re.escape(sex_u)}\s+\d{{1,2}}[./\-]|"
            rf"\d{{1,2}}[./\-]\d{{1,2}}[./\-]\d{{2,4}}\s+{re.escape(sex_u)}\b",
            text or "",
        ):
            fields["sex"] = None
    if fields.get("document_type") and not any(
        fields.get(k)
        for k in (
            "document_number",
            "surname",
            "given_names",
            "date_of_birth",
            "date_of_expiry",
        )
    ) and not _is_plausible_mrz_string(str(fields.get("mrz_string") or "")):
        fields["document_type"] = None
    if fields.get("place_of_issue") and not labeled.get("place_of_issue"):
        if not _PLACE_OF_ISSUE_LABEL_RE.search(text or ""):
            fields["place_of_issue"] = None
    if fields.get("place_of_birth") and not labeled.get("place_of_birth"):
        if not _PLACE_OF_BIRTH_LABEL_RE.search(text or ""):
            fields["place_of_birth"] = None

    # Value-shape only: label miss must not wipe a plausible OCR/LLM capture.
    if fields.get("spouse_name"):
        kept = retain_if_valid_value(
            "spouse_name",
            fields["spouse_name"],
            shape_ok=lambda v: (
                not _is_blank_spouse_value(v) and _is_plausible_person_name(v)
            ),
        )
        fields["spouse_name"] = kept
        spouse_val = str(fields.get("spouse_name") or "").strip()
        father_val = str(fields.get("father_name") or "").strip()
        mother_val = str(fields.get("mother_name") or "").strip()
        if spouse_val and (
            (father_val and spouse_val.upper() == father_val.upper())
            or (mother_val and spouse_val.upper() == mother_val.upper())
        ):
            fields["spouse_name"] = None

    # Country code is the ISO alpha-3 (IND). Nationality is the printed name (INDIAN).
    code = _to_alpha3(str(fields.get("country_code") or fields.get("issuing_state") or ""))
    if not code:
        _, code_from_nat = resolve_nationality(str(fields.get("nationality") or ""))
        code = code_from_nat
    if code and code in _VALID_ALPHA3:
        fields["country_code"] = code
    elif re.search(r"(?i)republic\s*of\s*india|\bindian\b", text or ""):
        fields["country_code"] = "IND"
        code = "IND"

    demonym, nat_alpha = resolve_nationality(str(fields.get("nationality") or ""))
    if demonym:
        fields["nationality"] = demonym
        if nat_alpha and not fields.get("country_code"):
            fields["country_code"] = nat_alpha
    else:
        # Reject garbage; fall back to demonym from validated country_code.
        fields["nationality"] = demonym_for_country_code(
            str(fields.get("country_code") or "")
        )
    fields.pop("issuing_state", None)

    poi = str(fields.get("place_of_issue") or "").strip()
    if poi:
        poi = _normalize_place_token(poi)
        fields["place_of_issue"] = poi or None
    pob = str(fields.get("place_of_birth") or "").strip()
    if pob:
        fields["place_of_birth"] = _normalize_place_token(pob) or None

    # Prefer visual-zone surname when MRZ surname looks like a place/label.
    mrz_surname = str(fields.get("surname") or "")
    labeled_surname = str(labeled.get("surname") or "")
    if labeled_surname and (
        not mrz_surname
        or re.search(r"(?i)place|birth|issue|nationality", mrz_surname)
        or ("," in mrz_surname)
        or (
            labeled.get("place_of_birth")
            and mrz_surname.upper()
            == str(labeled.get("place_of_birth") or "")
            .upper()
            .split(",")[0]
            .strip()
        )
    ):
        fields["surname"] = labeled_surname
        from_mrz_keys.discard("surname")

    # Prefer the cleaner parent / spouse names (never keep label/OCR junk blobs).
    for nk in ("father_name", "mother_name", "spouse_name"):
        a = str(fields.get(nk) or "").strip()
        b = str(labeled.get(nk) or "").strip()
        a_junk = bool(a and (_PARENT_NAME_JUNK_RE.search(a) or not _is_plausible_person_name(a)))
        b_junk = bool(b and (_PARENT_NAME_JUNK_RE.search(b) or not _is_plausible_person_name(b)))
        if b and not b_junk and (not a or a_junk or len(b.split()) > len(a.split())):
            fields[nk] = b
        elif a_junk:
            fields[nk] = b if b and not b_junk else None
        # Drop residual junk even when labeled is empty.
        if fields.get(nk) and (
            _PARENT_NAME_JUNK_RE.search(str(fields[nk]))
            or not _is_plausible_person_name(str(fields[nk]))
        ):
            fields[nk] = None
        cleaned = _clean_person_name(str(fields[nk]) if fields.get(nk) else None)
        fields[nk] = cleaned if _is_plausible_person_name(cleaned) else None

    # Hard separation: spouse must never equal a parent name.
    spouse_v = str(fields.get("spouse_name") or "").strip().upper()
    if spouse_v and spouse_v in {
        str(fields.get("father_name") or "").strip().upper(),
        str(fields.get("mother_name") or "").strip().upper(),
    }:
        fields["spouse_name"] = None

    # Place of birth must never be a date string.
    if fields.get("place_of_birth") and _looks_like_date_value(str(fields["place_of_birth"])):
        fields["place_of_birth"] = labeled.get("place_of_birth")
        if fields.get("place_of_birth") and _looks_like_date_value(
            str(fields["place_of_birth"])
        ):
            fields["place_of_birth"] = None
    if labeled.get("place_of_birth") and not _looks_like_date_value(
        str(labeled["place_of_birth"])
    ):
        if not fields.get("place_of_birth") or _looks_like_date_value(
            str(fields.get("place_of_birth") or "")
        ):
            fields["place_of_birth"] = labeled["place_of_birth"]

    # Place of issue / birth must not be a signature or the holder's own name.
    holder_given = str(fields.get("given_names") or labeled.get("given_names") or "")
    holder_surname = str(fields.get("surname") or labeled.get("surname") or "")

    def _scrub_holder_place(key: str) -> None:
        cur = str(fields.get(key) or "").strip()
        if not cur:
            return
        if not _is_holder_name_as_place(
            cur, surname=holder_surname, given_names=holder_given
        ) and not _is_nationality_as_place(cur):
            return
        fields[key] = None
        alt = str(labeled.get(key) or "").strip()
        if (
            alt
            and not _is_holder_name_as_place(
                alt, surname=holder_surname, given_names=holder_given
            )
            and not _is_nationality_as_place(alt)
            and (
                _is_issuing_office_candidate(
                    alt, surname=holder_surname, given_names=holder_given
                )
                if key == "place_of_issue"
                else _is_place_candidate(
                    alt, surname=holder_surname, given_names=holder_given
                )
            )
        ):
            fields[key] = _normalize_place_token(alt)

    _scrub_holder_place("place_of_issue")
    _scrub_holder_place("place_of_birth")

    # Issue date must precede expiry (fixes swapped OCR on Date of Issue/Expiry row).
    def _passport_dt(s: str | None):
        from datetime import datetime as _dt

        text_s = str(s or "").strip()
        if not text_s:
            return None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return _dt.strptime(text_s[:10], fmt)
            except ValueError:
                continue
        return None

    # Prefer MRZ expiry over truncated OCR like "03/2031", but never keep a
    # misaligned MRZ date that precedes DOB (common when leading passport letter
    # was dropped from line 2).
    mrz_exp = str(mrz.get("date_of_expiry") or "").strip()
    mrz_dob = str(mrz.get("date_of_birth") or fields.get("date_of_birth") or "").strip()
    mrz_exp_dt, mrz_dob_dt = _passport_dt(mrz_exp), _passport_dt(mrz_dob)
    mrz_exp_ok = bool(mrz_exp_dt and (not mrz_dob_dt or mrz_exp_dt > mrz_dob_dt))
    vis_doi = str(labeled.get("date_of_issue") or "").strip()
    vis_doe = str(labeled.get("date_of_expiry") or "").strip()
    vis_doi_dt, vis_doe_dt = _passport_dt(vis_doi), _passport_dt(vis_doe)
    visual_pair_ok = bool(vis_doi_dt and vis_doe_dt and vis_doi_dt < vis_doe_dt)
    if mrz_exp and mrz_exp_ok and not mrz.get("_mrz_misaligned"):
        # A consistent visual issue/expiry pair wins when MRZ expiry is earlier
        # than the printed issue date (misaligned TD3 line 2).
        if visual_pair_ok and mrz_exp_dt and mrz_exp_dt <= vis_doi_dt:
            fields["date_of_expiry"] = vis_doe
        else:
            fields["date_of_expiry"] = mrz_exp
    elif fields.get("date_of_expiry"):
        exp = str(fields["date_of_expiry"])
        if re.fullmatch(r"\d{1,2}[./\-]\d{4}", exp) and labeled.get("date_of_expiry"):
            fields["date_of_expiry"] = labeled["date_of_expiry"]
        # Drop MRZ-misaligned garbage already in fields (expiry before DOB).
        cur_exp_dt = _passport_dt(str(fields.get("date_of_expiry") or ""))
        cur_dob_dt = _passport_dt(str(fields.get("date_of_birth") or ""))
        if cur_exp_dt and cur_dob_dt and cur_exp_dt <= cur_dob_dt:
            fields["date_of_expiry"] = labeled.get("date_of_expiry") or None

    if visual_pair_ok:
        fields["date_of_issue"] = vis_doi
        cur_exp_dt = _passport_dt(str(fields.get("date_of_expiry") or ""))
        if not cur_exp_dt or cur_exp_dt <= vis_doi_dt:
            fields["date_of_expiry"] = vis_doe

    doi = str(fields.get("date_of_issue") or "").strip()
    doe = str(fields.get("date_of_expiry") or "").strip()
    d_i, d_e = _passport_dt(doi), _passport_dt(doe)
    if d_i and d_e and d_i >= d_e:
        alt = str(labeled.get("date_of_issue") or "").strip()
        alt_dt = _passport_dt(alt)
        if alt_dt and alt_dt < d_e:
            fields["date_of_issue"] = alt
        else:
            fields["date_of_issue"] = None
    # Issue must never equal expiry (common stacked-label OCR bug).
    if (
        fields.get("date_of_issue")
        and fields.get("date_of_expiry")
        and str(fields["date_of_issue"]).strip()
        == str(fields["date_of_expiry"]).strip()
    ):
        fields["date_of_issue"] = None
        lab_doi = str(labeled.get("date_of_issue") or "").strip()
        lab_dt = _passport_dt(lab_doi)
        exp_dt = _passport_dt(str(fields.get("date_of_expiry") or ""))
        if lab_dt and exp_dt and lab_dt < exp_dt:
            fields["date_of_issue"] = lab_doi

    # Drop garbage file numbers (date crumbs fused with label letters).
    if fields.get("file_number") and _is_garbage_file_number(str(fields["file_number"])):
        fields["file_number"] = None
        if labeled.get("file_number") and not _is_garbage_file_number(
            str(labeled["file_number"])
        ):
            fields["file_number"] = labeled["file_number"]

    # Address must not be a bare Place-of-Birth city.
    addr_v = str(fields.get("address") or "").strip()
    if addr_v and _is_ocr_junk_text_value(addr_v):
        fields["address"] = None
        addr_v = ""
    pob_v = str(fields.get("place_of_birth") or "").strip()
    if addr_v and pob_v and addr_v.upper() == pob_v.upper():
        fields["address"] = None
        lab_addr = str(labeled.get("address") or "").strip()
        if (
            lab_addr
            and lab_addr.upper() != pob_v.upper()
            and not _is_ocr_junk_text_value(lab_addr)
        ):
            fields["address"] = lab_addr

    # date_of_issue is visual-zone only — prefer labeled when current missing/invalid.
    if labeled.get("date_of_issue"):
        lab_doi = str(labeled["date_of_issue"]).strip()
        cur_doi = str(fields.get("date_of_issue") or "").strip()
        lab_dt, cur_dt, exp_dt = (
            _passport_dt(lab_doi),
            _passport_dt(cur_doi),
            _passport_dt(str(fields.get("date_of_expiry") or "")),
        )
        # Never adopt a labeled issue that collides with expiry.
        lab_ok = bool(lab_dt and (not exp_dt or lab_dt < exp_dt))
        if not cur_dt and lab_ok:
            fields["date_of_issue"] = lab_doi
        elif exp_dt and cur_dt and cur_dt >= exp_dt and lab_ok:
            fields["date_of_issue"] = lab_doi
        elif not fields.get("date_of_issue") and lab_ok:
            fields["date_of_issue"] = lab_doi
    # Prefer alphanumeric File No. stamps; drop digit-only OCR ghosts unless
    # no better candidate exists from labeled/block extraction.
    fno = str(fields.get("file_number") or "").strip()
    labeled_fno = str(labeled.get("file_number") or "").strip()
    if labeled_fno and _is_garbage_file_number(labeled_fno):
        labeled_fno = ""
    if fno and _is_garbage_file_number(fno):
        fields["file_number"] = None
        fno = ""
    if labeled_fno and (
        not fno
        or (_PASSPORT_NO_SHAPE_RE.match(fno.upper()) and not _PASSPORT_NO_SHAPE_RE.match(labeled_fno.upper()))
        or (re.fullmatch(r"[\d\s]{6,}", fno) and _FILE_NO_SHAPE_RE.match(labeled_fno.upper()))
    ):
        fields["file_number"] = labeled_fno
        fno = labeled_fno
    if fno and _PASSPORT_NO_SHAPE_RE.match(fno.upper()):
        # Never keep passport number as file number when a real stamp exists.
        if labeled_fno and not _PASSPORT_NO_SHAPE_RE.match(labeled_fno.upper()):
            fields["file_number"] = labeled_fno
        else:
            fields["file_number"] = None
    elif fno and re.fullmatch(r"[\d\s]{6,}", fno):
        # Digit-only text OCR under File No is usually a misread of letter+digits.
        if labeled_fno and _FILE_NO_SHAPE_RE.match(labeled_fno.upper()):
            fields["file_number"] = labeled_fno
        else:
            fields["file_number"] = None
    if not fields.get("file_number") and labeled_fno:
        fields["file_number"] = labeled_fno

    if fields.get("place_of_birth") and (
        _is_noise_value(str(fields["place_of_birth"]))
        or _is_nationality_as_place(str(fields["place_of_birth"]))
        or _is_ocr_junk_text_value(str(fields["place_of_birth"]))
    ):
        fields["place_of_birth"] = None
    if fields.get("place_of_issue") and (
        _is_noise_value(str(fields["place_of_issue"]))
        or _is_nationality_as_place(str(fields["place_of_issue"]))
        or _is_postal_address_as_place(str(fields["place_of_issue"]))
        or _is_ocr_junk_text_value(str(fields["place_of_issue"]))
        or not _is_issuing_office_candidate(
            str(fields["place_of_issue"]),
            surname=holder_surname,
            given_names=holder_given,
        )
    ):
        fields["place_of_issue"] = None
        alt_poi = _normalize_place_token(str(labeled.get("place_of_issue") or ""))
        if alt_poi and _is_issuing_office_candidate(
            alt_poi, surname=holder_surname, given_names=holder_given
        ):
            fields["place_of_issue"] = alt_poi[:80]
    # If birth captured the issue label, clear and try swap from labeled.
    if fields.get("place_of_birth") and re.search(
        r"(?i)issue", str(fields["place_of_birth"])
    ):
        fields["place_of_birth"] = None
    if (
        not fields.get("place_of_birth")
        and labeled.get("place_of_birth")
        and not _is_noise_value(labeled["place_of_birth"])
        and not _is_nationality_as_place(str(labeled["place_of_birth"]))
        and not _is_ocr_junk_text_value(str(labeled["place_of_birth"]))
    ):
        fields["place_of_birth"] = labeled["place_of_birth"]
    confidence_scores: dict[str, float] = {}
    for key in PASSPORT_FIELD_KEYS:
        if key in {"mrz_string", "bounding_boxes", "confidence_scores", "is_low_confidence"}:
            continue
        val = fields.get(key)
        if val is None or val == "":
            confidence_scores[key] = 0.0
            continue
        confidence_scores[key] = _confidence_for_field(
            key,
            str(val),
            from_mrz=key in from_mrz_keys,
            ocr_mean=ocr_mean_confidence,
        )

    needles: list[tuple[str, str]] = []
    for key in (
        "surname",
        "given_names",
        "document_number",
        "nationality",
        "father_name",
        "mother_name",
        "spouse_name",
    ):
        if fields.get(key):
            needles.append((key, str(fields[key])))
    bounding_boxes, bounding_box_pages = _boxes_from_ocr_blocks(
        ocr_blocks, needles=needles
    )

    low = False
    for key in _CRITICAL_KEYS:
        conf = confidence_scores.get(key, 0.0)
        if not fields.get(key) or conf < OCR_CONFIDENCE_THRESHOLD:
            low = True
            break
    if mrz.get("_mrz_incomplete"):
        low = True

    fields = _post_validate_passport_fields(
        fields,
        text=text,
        ocr_blocks=ocr_blocks,
        labeled=labeled,
    )
    # Junk text can latch a surname long enough to keep document_type, then
    # the name gate clears the surname and leaves a lone "P".
    if fields.get("document_type") and not any(
        fields.get(k)
        for k in (
            "document_number",
            "surname",
            "given_names",
            "date_of_birth",
            "date_of_expiry",
        )
    ) and not _is_plausible_mrz_string(str(fields.get("mrz_string") or "")):
        fields["document_type"] = None

    # Counsellor-facing dates: SCANX_DATE_FORMAT (default DD-MM-YYYY).
    apply_scanx_date_format_to_fields(fields)

    payload = {
        **{k: fields.get(k) for k in PASSPORT_FIELD_KEYS},
        "bounding_boxes": bounding_boxes,
        "bounding_box_pages": bounding_box_pages,
        "confidence_scores": confidence_scores,
        "is_low_confidence": low,
    }
    if mrz.get("_mrz_incomplete"):
        payload["_mrz_incomplete"] = True
    return _apply_passport_validation_gate(
        payload, source_text=text, ocr_blocks=ocr_blocks
    )


def _verified_line2_authority(
    text: str | None,
    ocr_blocks: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """First TD3 line 2 whose ICAO check digits pass, else None."""
    blobs = [text or ""]
    for blk in ocr_blocks or []:
        if isinstance(blk, dict):
            blobs.append(_block_text(blk))
    seen: set[str] = set()
    for blob in blobs:
        candidates: list[str] = []
        for ln in extract_mrz_lines(blob):
            candidates.append(ln)
        for raw_line in (blob or "").splitlines():
            candidates.append(_normalize_mrz_candidate(raw_line))
        for cand in candidates:
            key = (_normalize_mrz_candidate(cand) + ("<" * 44))[:44]
            if not key or key in seen:
                continue
            seen.add(key)
            fields = _authority_fields_from_line2(cand)
            if fields:
                return fields
    return None


def _separate_cross_filled_family(out: dict[str, Any], text: str | None, ocr_blocks) -> None:
    """Each parent stays on its own label. Spouse never copies a parent or an address."""
    out["father_name"] = _strip_trailing_mother_from_father(
        str(out.get("father_name") or "") or None,
        str(out.get("mother_name") or "") or None,
        text=text,
        ocr_blocks=ocr_blocks,
    )
    out["mother_name"] = _strip_leading_father_portion_from_mother(
        str(out.get("mother_name") or "") or None,
        str(out.get("father_name") or "") or None,
    )
    out["mother_name"] = _strip_trailing_father_from_mother(
        str(out.get("mother_name") or "") or None,
        str(out.get("father_name") or "") or None,
        text=text,
        ocr_blocks=ocr_blocks,
    )
    spouse = str(out.get("spouse_name") or "").strip()
    father_u = str(out.get("father_name") or "").strip().upper()
    mother_u = str(out.get("mother_name") or "").strip().upper()
    if (
        not spouse
        or _is_blank_spouse_value(spouse)
        or not _is_plausible_person_name(spouse)
        or _spouse_value_is_address_like(spouse, str(out.get("address") or ""))
        or (father_u and spouse.upper() == father_u)
        or (mother_u and spouse.upper() == mother_u)
        or not _spouse_supported_by_label(spouse, text, ocr_blocks)
    ):
        out["spouse_name"] = None


_VISUAL_PASSPORT_NO_LABEL_RE = re.compile(
    r"(?i)passport\s*(?:no\.?|number|#)|passpon\s*no\.?|document\s*(?:no\.?|number)"
)
_VISUAL_SEX_LABEL_RE = re.compile(r"(?i)\b(?:sex|sexe|gender|ses)\b")
_VISUAL_DOB_LABEL_RE = re.compile(
    r"(?i)(?:date\s*(?:of|ot|af)\s*(?:birth|burt|birt|blrth|birih|bith)|\bdob\b)"
)
_VISUAL_EXPIRY_LABEL_RE = re.compile(
    r"(?i)(?:\bexpir\w*\b|\bcepir\w*\b|\beapir\w*\b|\be\s+xpiry\b)"
)
_VISUAL_NATIONALITY_LABEL_RE = re.compile(
    r"(?i)\bnationalit\w*\b|\bcitizenship\b|\bcitoyennet\w*\b"
)
_VISUAL_FULL_DATE_RE = re.compile(r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})\b")
_VISUAL_PASSPORT_TOKEN_RE = re.compile(r"\b([A-Z]\d{7})\b")


def _sex_token_on_line(line: str | None) -> str | None:
    """M or F on a sex value line. Other letters are not a sex."""
    text = line or ""
    match = re.search(r"(?i)(?:^|[\s/])([MF])\s*/\s*(?:INDIAN|IND)\b", text)
    if match:
        return match.group(1).upper()
    match = re.search(r"(?i)\b(?:INDIAN|IND)\s+([MF])\b", text)
    if match:
        return match.group(1).upper()
    match = re.search(r"(?i)\b(male|female)\b", text)
    if match:
        return "M" if match.group(1).lower() == "male" else "F"
    match = re.search(r"(?i)(?:^|\s)([MF])(?:\s|$)", text)
    if match:
        return match.group(1).upper()
    return None


def _next_nonempty_line(lines: list[str], index: int) -> str:
    for line in lines[index + 1 : index + 4]:
        if line.strip():
            return line.strip()
    return ""


def _label_anchored_identity_fields(text: str | None) -> dict[str, str | None]:
    """Passport number, DOB, sex, nationality, and expiry from their own labels.

    Used only when TD3 line 2 is missing or its check digits fail. A token on a
    neighboring field is not borrowed. Grammar: letter+7 digits, a real date,
    sex M/F, and a nationality demonym.
    """
    lines = (text or "").splitlines()
    found: dict[str, str | None] = {key: None for key in _MRZ_LINE2_AUTHORITY_KEYS}

    for index, line in enumerate(lines):
        if found["document_number"] or not _VISUAL_PASSPORT_NO_LABEL_RE.search(line):
            continue
        if re.search(r"(?i)old\s*pass", line):
            continue
        window = line
        nxt = _next_nonempty_line(lines, index)
        if nxt and not re.search(r"(?i)old\s*pass", nxt):
            window = f"{line}\n{nxt}"
        match = _VISUAL_PASSPORT_TOKEN_RE.search(window.upper())
        if match:
            found["document_number"] = match.group(1)

    for index, line in enumerate(lines):
        if found["sex"] or not _VISUAL_SEX_LABEL_RE.search(line):
            continue
        for candidate in (line, _next_nonempty_line(lines, index)):
            sex = _sex_token_on_line(candidate)
            if sex in {"M", "F"}:
                found["sex"] = sex
                break

    for index, line in enumerate(lines):
        if found["date_of_birth"] or not _VISUAL_DOB_LABEL_RE.search(line):
            continue
        for candidate in (line, _next_nonempty_line(lines, index)):
            match = _VISUAL_FULL_DATE_RE.search(candidate or "")
            if not match:
                continue
            parsed = _parse_flexible_date(match.group(1))
            if parsed and not _date_only_in_old_passport_context(text or "", parsed):
                found["date_of_birth"] = parsed
                break

    for index, line in enumerate(lines):
        if found["date_of_expiry"] or not _VISUAL_EXPIRY_LABEL_RE.search(line):
            continue
        dates: list[str] = []
        for candidate in (line, _next_nonempty_line(lines, index)):
            for match in _VISUAL_FULL_DATE_RE.finditer(candidate or ""):
                parsed = _parse_flexible_date(match.group(1))
                if parsed and parsed not in dates:
                    dates.append(parsed)
        dates = [item for item in dates if item != found.get("date_of_birth")]
        if not dates:
            continue
        if len(dates) == 1:
            found["date_of_expiry"] = dates[0]
            continue
        _issue, expiry = _ordered_issue_expiry(dates[0], dates[1])
        found["date_of_expiry"] = expiry or dates[-1]

    for index, line in enumerate(lines):
        if found["nationality"] or not _VISUAL_NATIONALITY_LABEL_RE.search(line):
            continue
        for candidate in (line, _next_nonempty_line(lines, index)):
            piece = candidate or ""
            demonym, _code = resolve_nationality(piece)
            if not demonym:
                glue = re.search(
                    r"(?i)\b(?:[A-Z]{1,4}\s*/\s*)?(INDIAN|INDIA)\b",
                    piece,
                )
                if glue:
                    demonym, _code = resolve_nationality(glue.group(1))
            if demonym:
                found["nationality"] = demonym
                break
    return found


def _apply_passport_validation_gate(
    payload: dict[str, Any],
    *,
    source_text: str | None = None,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Last step of the passport pipeline. A value that fails its check is null.

    Callers use ``run_passport_pipeline``. This gate does not guess a replacement.
    When TD3 line 2 check digits pass, passport number, date of birth, expiry,
    sex, and nationality come only from that line. When line 2 is missing or the
    checks fail, those fields stay only if their own visual labels carry a
    strict value. Date of issue is left on the visual path.
    """
    out = dict(payload)
    for key in (
        "place_of_birth",
        "place_of_issue",
        "address",
        "surname",
        "given_names",
        "father_name",
        "mother_name",
        "spouse_name",
    ):
        raw_val = str(out.get(key) or "").strip()
        if raw_val and _is_ocr_junk_text_value(raw_val):
            out[key] = None
    if _address_is_administrative_noise(str(out.get("address") or "")):
        out["address"] = None
    out["date_of_issue"] = _complete_passport_date(str(out.get("date_of_issue") or "") or None)
    authority = _verified_line2_authority(source_text, ocr_blocks)
    if authority:
        for key in _MRZ_LINE2_AUTHORITY_KEYS:
            out[key] = authority.get(key)
        if authority.get("country_code"):
            out["country_code"] = authority["country_code"]
    else:
        # Line 2 absent or check digits failed. Do not rewrite the line.
        # Keep only values that sit on their own visual labels.
        visual = _label_anchored_identity_fields(source_text)
        for key in _MRZ_LINE2_AUTHORITY_KEYS:
            out[key] = visual.get(key)
    _separate_cross_filled_family(out, source_text, ocr_blocks)
    scores = out.get("confidence_scores")
    if not isinstance(scores, dict):
        scores = {}
        out["confidence_scores"] = scores
    for key in _MRZ_LINE2_AUTHORITY_KEYS:
        val = out.get(key)
        scores[key] = (
            _confidence_for_field(key, str(val), from_mrz=True, ocr_mean=None)
            if val
            else 0.0
        )
    low = False
    for key in _CRITICAL_KEYS:
        conf = float(scores.get(key) or 0.0)
        if not out.get(key) or conf < OCR_CONFIDENCE_THRESHOLD:
            low = True
            break
    out["is_low_confidence"] = low
    mrz_val = str(out.get("mrz_string") or "").strip()
    if mrz_val and (
        "\n" not in mrz_val or not _is_plausible_mrz_string(mrz_val)
    ):
        out["mrz_string"] = None
        out["_mrz_incomplete"] = True
    return out


def run_passport_pipeline(
    text: str,
    *,
    ocr_blocks: list[dict[str, Any]] | None = None,
    ocr_mean_confidence: float | None = None,
) -> dict[str, Any]:
    """Single passport extraction entry. Invalid fields come back null."""
    return extract_passport_fields(
        text,
        ocr_blocks=ocr_blocks,
        ocr_mean_confidence=ocr_mean_confidence,
    )


def passport_to_category_items(passport: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten passport biographic/MRZ fields into Field|Value items."""
    items: list[dict[str, str]] = []
    for key in PASSPORT_FIELD_KEYS:
        val = passport.get(key)
        if val is None or str(val).strip() == "":
            continue
        items.append(
            {
                "label": _PASSPORT_FIELD_LABELS.get(key, key),
                "value": str(val).strip(),
                "category": _category_id_for_passport_key(key),
            }
        )
    return items


def _category_id_for_passport_key(key: str) -> str:
    for cat_id, _label, keys in PASSPORT_GROUP_DEFS:
        if key in keys:
            return cat_id
    return "other"


def _format_audit_value(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if key == "is_low_confidence":
        return "true" if bool(value) else "false"
    if key == "confidence_scores" and isinstance(value, dict):
        if not value:
            return None
        parts = [
            f"{k}={round(float(v) * 100)}%"
            for k, v in sorted(value.items())
            if isinstance(v, (int, float)) and float(v) > 0
        ]
        return "; ".join(parts) if parts else None
    if key == "bounding_boxes" and isinstance(value, dict):
        if not value:
            return None
        parts: list[str] = []
        for field, box in value.items():
            if isinstance(box, list) and box:
                parts.append(f"{field}: {len(box)} pts")
        return "; ".join(parts) if parts else None
    if isinstance(value, (dict, list)):
        import json

        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(value)
        return text[:2000] if text else None
    text = str(value).strip()
    return text or None


def passport_to_grouped_categories(
    passport: dict[str, Any],
    *,
    other_items: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build the 5 counsellor tables: Personal / Document / MRZ / Audit / Other."""
    categories: list[dict[str, Any]] = []
    for cat_id, cat_label, keys in PASSPORT_GROUP_DEFS:
        items: list[dict[str, str]] = []
        if cat_id == "audit_ui":
            for key in keys:
                formatted = _format_audit_value(key, passport.get(key))
                if formatted is None:
                    continue
                items.append(
                    {
                        "label": _PASSPORT_FIELD_LABELS.get(key, key),
                        "value": formatted,
                    }
                )
        else:
            for key in keys:
                val = passport.get(key)
                if val is None or str(val).strip() == "":
                    continue
                items.append(
                    {
                        "label": _PASSPORT_FIELD_LABELS.get(key, key),
                        "value": str(val).strip(),
                    }
                )
        if items:
            categories.append({"id": cat_id, "label": cat_label, "items": items})

    extras: list[dict[str, str]] = []
    seen = {
        (i.get("label") or "").strip().lower()
        for cat in categories
        for i in cat.get("items") or []
    }
    for raw in other_items or []:
        if not isinstance(raw, dict):
            continue
        lab = (raw.get("label") or "").strip()
        val = (raw.get("value") or "").strip()
        if not lab or not val:
            continue
        if lab.lower() in _PASSPORT_KNOWN_LABELS or lab.lower() in seen:
            continue
        if lab == "Full text preview":
            continue
        if _is_ocr_junk_other_detail_token(lab) or _is_ocr_junk_other_detail_token(val):
            continue
        extras.append({"label": lab, "value": val})
        seen.add(lab.lower())

    for key, val in passport.items():
        if key.startswith("_") and val is not None and str(val).strip() != "":
            lab = key.lstrip("_").replace("_", " ").title()
            if lab.lower() in seen:
                continue
            raw_val = str(val).strip()
            if _is_ocr_junk_other_detail_token(lab) or _is_ocr_junk_other_detail_token(
                raw_val
            ):
                continue
            # Underscore keys that are themselves OCR garbage blobs
            if _is_ocr_junk_other_detail_token(key.lstrip("_")):
                continue
            extras.append({"label": lab, "value": raw_val})
            seen.add(lab.lower())

    if extras:
        categories.append(
            {"id": "other", "label": "Other Details", "items": extras}
        )
    return categories


def attach_passport_to_fields(
    categorized: dict[str, Any] | None,
    passport: dict[str, Any],
    *,
    text: str | None = None,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge passport payload into extracted_fields_json with the 5 UI groups."""
    base: dict[str, Any] = (
        dict(categorized) if isinstance(categorized, dict) else {"version": 1}
    )
    base["passport"] = passport

    leftover: list[dict[str, str]] = []
    passport_cat_ids = {g[0] for g in PASSPORT_GROUP_DEFS}
    for cat in base.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        # Skip stale passport UI groups — never re-hydrate from a prior extract.
        if str(cat.get("id") or "") in passport_cat_ids:
            continue
        for item in cat.get("items") or []:
            if isinstance(item, dict):
                lab = str(item.get("label") or "")
                val = str(item.get("value") or "")
                if _canonical_key_from_ocr_label(lab):
                    continue
                if _is_ocr_junk_other_detail_token(lab) or _is_ocr_junk_other_detail_token(
                    val
                ):
                    continue
                leftover.append({"label": lab, "value": val})
    for field in base.get("fields") or []:
        if isinstance(field, dict):
            # Skip rows that already map to passport schema keys.
            lab = str(field.get("label") or "")
            val = str(field.get("value") or "")
            if _canonical_key_from_ocr_label(lab):
                continue
            if _is_ocr_junk_other_detail_token(lab) or _is_ocr_junk_other_detail_token(
                val
            ):
                continue
            leftover.append({"label": lab, "value": val})

    passport = hydrate_passport_from_label_items(passport, leftover)
    if passport.get("address"):
        passport["address"] = normalize_multiline_address(str(passport["address"]))
    passport = _post_validate_passport_fields(
        passport, text=text, ocr_blocks=ocr_blocks
    )
    base["passport"] = passport

    grouped = passport_to_grouped_categories(passport, other_items=leftover)
    base["categories"] = grouped

    flat: list[dict[str, str]] = []
    for cat in grouped:
        cat_id = str(cat.get("id") or "other")
        for item in cat.get("items") or []:
            if not isinstance(item, dict):
                continue
            flat.append(
                {
                    "label": str(item.get("label") or ""),
                    "value": str(item.get("value") or ""),
                    "category": cat_id,
                }
            )
    base["fields"] = flat
    base["subjects"] = []
    base["marks"] = []
    return base


# 180° page inversion. A positive score means header / MRZ reads left to right.
_ORIENTATION_CLEAR_MARGIN = 4

_ORIENT_UPRIGHT_LATIN_RES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"REPUBLIC"), 5),
    (re.compile(r"PASSE?PORT"), 4),
)
_ORIENT_REVERSED_LATIN_RES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"CILBUPER"), 5),
    (re.compile(r"TROPESSAP"), 4),
    (re.compile(r"TROPSSAP"), 4),
)
_ORIENT_UPRIGHT_HINDI = ("भारत", "पासपोर्ट", "गणतंत्र")


def _passport_orientation_latin(text: str) -> str:
    folded = (text or "").upper().replace("0", "O").replace("1", "I").replace("|", "I")
    return re.sub(r"[^A-Z<]", "", folded)


def passport_orientation_signal_score(text: str | None) -> int:
    """Higher means the probe reads a passport header or MRZ left to right."""
    raw = str(text or "")
    if not raw.strip():
        return 0
    latin = _passport_orientation_latin(raw)
    score = 0
    for rx, weight in _ORIENT_UPRIGHT_LATIN_RES:
        if rx.search(latin):
            score += weight
    if any(tok in raw for tok in _ORIENT_UPRIGHT_HINDI):
        score += 4
    if re.search(r"P<[A-Z]{3}", latin):
        score += 6
    for rx, weight in _ORIENT_REVERSED_LATIN_RES:
        if rx.search(latin):
            score -= weight
    if re.search(r"[A-Z0-9]{6,}<P", latin) and not re.search(r"P<[A-Z]{3}", latin):
        score -= 6
    return score


def page_already_upright_for_orientation(probe_0: str | None) -> bool:
    """True when the 0° probe already shows a normal passport header or MRZ."""
    return passport_orientation_signal_score(probe_0) >= _ORIENTATION_CLEAR_MARGIN


def choose_passport_page_rotation(probe_0: str | None, probe_180: str | None) -> int:
    """Return 180 only when that probe is clearly more upright than 0°.

    An upright header or ``P<`` MRZ at 0° stays put. Equal or weak probes stay
    at 0° so an already-upright page is not rotated.
    """
    upright = passport_orientation_signal_score(probe_0)
    flipped = passport_orientation_signal_score(probe_180)
    if upright >= _ORIENTATION_CLEAR_MARGIN:
        return 0
    if (
        flipped >= _ORIENTATION_CLEAR_MARGIN
        and flipped >= upright + _ORIENTATION_CLEAR_MARGIN
    ):
        return 180
    return 0


_ORIENT_READABILITY_MIN = 70
_ORIENT_READABILITY_MARGIN = 36
_ORIENT_READABILITY_RATIO = 1.7


def passport_orientation_readability(text: str | None) -> int:
    """Letters in words of four or more. Higher means the probe looks readable."""
    return sum(len(word) for word in re.findall(r"[A-Za-z]{4,}", str(text or "")))


def _region_reads_clearly_better(winner: str | None, loser: str | None) -> bool:
    """True when ``winner`` has clearly more readable words than ``loser``."""
    good = passport_orientation_readability(winner)
    bad = passport_orientation_readability(loser)
    if good < _ORIENT_READABILITY_MIN:
        return False
    if good < bad + _ORIENT_READABILITY_MARGIN:
        return False
    if bad > 0 and good < int(bad * _ORIENT_READABILITY_RATIO):
        return False
    return True


def classify_passport_region_orientation(
    probe: str | None,
    probe_180: str | None = None,
) -> str:
    """``upright``, ``inverted``, or ``none`` from one region's probe text.

    ``probe`` is the region at 0°. ``probe_180`` is the same region after a
    180° turn. A reversed header at 0° is inverted. A region with no header
    that still reads clearly better at 180° is inverted. An upright header
    stays upright.
    """
    score = passport_orientation_signal_score(probe)
    if probe_180 is None:
        if score >= _ORIENTATION_CLEAR_MARGIN:
            return "upright"
        if score <= -_ORIENTATION_CLEAR_MARGIN:
            return "inverted"
        return "none"
    flipped = passport_orientation_signal_score(probe_180)
    if score >= _ORIENTATION_CLEAR_MARGIN and flipped < score + _ORIENTATION_CLEAR_MARGIN:
        return "upright"
    if (
        flipped >= _ORIENTATION_CLEAR_MARGIN
        and flipped >= score + _ORIENTATION_CLEAR_MARGIN
    ):
        return "inverted"
    if score <= -_ORIENTATION_CLEAR_MARGIN and flipped > score:
        return "inverted"
    if _region_reads_clearly_better(probe_180, probe) and score < _ORIENTATION_CLEAR_MARGIN:
        return "inverted"
    if _region_reads_clearly_better(probe, probe_180) and flipped < _ORIENTATION_CLEAR_MARGIN:
        return "upright"
    return "none"


def choose_stacked_canvas_rotation(
    top_probe: str | None,
    bottom_probe: str | None,
    *,
    top_probe_180: str | None = None,
    bottom_probe_180: str | None = None,
) -> dict[str, Any]:
    """Choose a whole-canvas 180° versus rotating one half of a two-page canvas.

    The two probes are the two regions (top then bottom, or left then right).
    When they disagree — one upright, one inverted — only the inverted region
    turns. When they agree, both upright is 0° and both inverted may turn the
    whole canvas 180°. A region that reads clearly better at 180° is inverted
    even when the other region's signal is only an upright header, or is weak.
    An upright region is not rotated. Both regions silent is ``undecided`` so
    the caller can still run the whole-image 0°/180° probe.
    """
    top = classify_passport_region_orientation(top_probe, top_probe_180)
    bottom = classify_passport_region_orientation(bottom_probe, bottom_probe_180)
    if top == "upright" and bottom == "inverted":
        return {"mode": "regional", "top": 0, "bottom": 180}
    if top == "inverted" and bottom == "upright":
        return {"mode": "regional", "top": 180, "bottom": 0}
    if top == "inverted" and bottom == "inverted":
        return {"mode": "whole", "top": 180, "bottom": 180}
    if top == "upright" and bottom == "upright":
        return {"mode": "whole", "top": 0, "bottom": 0}
    if top == "inverted" and bottom == "none":
        return {"mode": "regional", "top": 180, "bottom": 0}
    if top == "none" and bottom == "inverted":
        return {"mode": "regional", "top": 0, "bottom": 180}
    if top == "upright" or bottom == "upright":
        return {"mode": "whole", "top": 0, "bottom": 0}
    return {"mode": "undecided", "top": 0, "bottom": 0}


def crop_bottom_band_png(image_bytes: bytes, *, fraction: float = 0.28) -> bytes | None:
    """Crop the lower band of a page (MRZ zone) as PNG bytes for a second OCR pass."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(__import__("io").BytesIO(image_bytes)) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            if w < 40 or h < 40:
                return None
            top = max(0, int(h * (1.0 - max(0.12, min(0.45, fraction)))))
            band = rgb.crop((0, top, w, h))
            # Upscale band for OCR clarity.
            band = band.resize(
                (max(w, int(w * 1.5)), max(h - top, int((h - top) * 1.5))),
                Image.Resampling.LANCZOS,
            )
            buf = __import__("io").BytesIO()
            band.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        logger.debug("MRZ band crop failed", exc_info=True)
        return None
