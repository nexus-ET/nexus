"""Passport OCR extraction: MRZ (TD3) + visual-zone labeled fields.

Produces the counsellor-facing passport schema persisted on
``extracted_document_data`` / ``extracted_fields_json.passport``.

Supports Indian multi-page scans (Page 1 biodata + Page 2 family/address).
"""

from __future__ import annotations

import logging
import re
from datetime import date
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
# TD3 line 2 shape (doc no + nationality + dates) — OCR may drop fillers.
_MRZ_L2_SHAPE_RE = re.compile(
    r"^[A-Z0-9]{6,9}[<0-9A-Z]{1,3}[A-Z]{3}\d{6}[MFX<]\d{6}[A-Z0-9<]*$"
)
_NEXT_FIELD_LABEL_RE = re.compile(
    r"(?i)^(place of|date of|name of|name ot|sex|gender|nationality|surname|"
    r"given|passport|code|type|file|address|old passport|mother|mather|"
    r"father|foter|spouse|legal guardian|lepai|curdian)\b"
)
_NAME_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z.'-]{0,30}$")
# OCR-tolerant page-2 labels (CamScanner often mangles Father/Mother/File/Spouse).
_FATHER_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bf[ao]ther\b|\bfoter\b|\bfother\b|\bguardian\b|\bguardlan\b|\bcurdian\b|"
    r"n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:f[ao]ther|foter|fother|guardian|guardlan)"
    r"(?:\s*/\s*legal\s*(?:guardian|guardlan|curdian))?|"
    r"legal\s*(?:guardian|guardlan|curdian))"
)
_MOTHER_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bmother\b|\bmather\b|\bmothor\b|"
    r"n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:mother|mather|mothor|maches))"
)
_SPOUSE_LABEL_FUZZY_RE = re.compile(
    r"(?i)(?:\bspouse\b|\bspouce\b|"
    r"n(?:ame|ane|eme)\s*(?:of|ot|ol)\s*(?:spouse|spouce))"
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
    r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}[./\-]\d{1,2}[./\-]\d{1,2})"
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
    s = re.sub(r"(?i)\b(?:name\s*(?:of|ot)\s*(?:father|mother|spouse))\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" /|,-")
    # Drop trailing address / spouse / door-number fragments glued onto names.
    s = re.split(
        r"(?i)\b(?:n?ame\s*(?:of|ot)\s*spouse|spouse|d\.?\s*no\.?|door\s*no|"
        r"h\.?\s*no|lane|address|pin\b)\b",
        s,
        maxsplit=1,
    )[0].strip(" /|,-")
    # Passport number tokens (e.g. N4981701) are not part of a parent name.
    s = re.sub(r"\b[A-Z]\d{7}\b", " ", s, flags=re.IGNORECASE)
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
    """True when a normalized OCR line is TD3 line 2 (not the P<… name line)."""
    if not cleaned or cleaned.startswith("P"):
        return False
    if len(cleaned) < 20:
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
    if re.search(r"\d", t):
        return False
    if len(t) > 60:
        return False
    tokens = t.replace("/", " ").split()
    if not tokens or len(tokens) > 6:
        return False
    stop = {"ON", "OF", "OT", "THE", "AND", "OR", "A", "AN", "TO", "NAME", "NO"}
    if len(tokens) == 1 and tokens[0].upper().rstrip(".") in stop:
        return False
    return all(_NAME_TOKEN_RE.match(tok) for tok in tokens)


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
    return _clean_person_name(" ".join(parts) if parts else None)


def _parse_flexible_date(raw: str | None) -> str | None:
    """Parse OCR date text and return SCANX_DATE_FORMAT (default DD-MM-YYYY)."""
    return normalize_scanx_date(raw)


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
        if c.startswith("P"):
            if _looks_like_td3_line1(c):
                candidates.append(c)
            return
        # Never treat a name-line fragment (lots of <<, no dates) as TD3 line 2.
        if _looks_like_td3_line2(c):
            candidates.append(c)

    i_raw = 0
    while i_raw < len(raw_lines):
        cleaned = _normalize_mrz_candidate(raw_lines[i_raw])
        # Pull embedded MRZ tokens out of long OCR lines that also hold dates.
        for m in re.finditer(r"P<[A-Z0-9<]{30,44}", cleaned):
            _add(m.group(0))
        for m in re.finditer(r"[A-Z0-9]{6,9}<[A-Z0-9<]{20,44}", cleaned):
            tok = m.group(0)
            if not tok.startswith("P"):
                _add(tok)
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
    # CamScanner often drops the leading letter of Indian passport numbers in MRZ
    # ("7766566<91ND…" instead of "S7766566<IND…"). Recover from visual-zone hint.
    hint = re.sub(r"[\s\-]", "", (doc_number_hint or "").upper())
    hint_m = re.fullmatch(r"([A-Z])(\d{7})", hint) if hint else None
    if hint_m and re.match(r"^\d{7}<", aligned):
        letter, digits = hint_m.group(1), hint_m.group(2)
        if aligned.startswith(digits):
            # Rebuild a standard TD3 L2 head: Letter+7digits + check + nationality fix.
            rest = aligned[len(digits) :]  # starts with <…
            # Common OCR: "<91ND" instead of "<IND" (check digit + IND mashed).
            if rest.startswith("<") and len(rest) >= 4:
                maybe_nat = rest[1:4]
                if maybe_nat in {"1ND", "9ND", "IND", "1N0", "IN0"}:
                    # Drop the mangled check+nat triplet and reinsert IND after a
                    # recomputed check digit.
                    tail = rest[4:]
                    head = f"{letter}{digits}"
                    check = str(_mrz_check_digit(head))
                    aligned = f"{head}{check}IND{tail}"
                else:
                    aligned = f"{letter}{aligned}"
            else:
                aligned = f"{letter}{aligned}"
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
            and not cand.startswith("P")
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
                and not cand.startswith("P")
                and cand.count("<") >= 2
            ):
                line2 = cand
                break

    if line2:
        out.update(_parse_td3_line2(line2, doc_number_hint=doc_number_hint))
        l1 = (line1 + ("<" * 44))[:44]
        l2 = (line2 + ("<" * 44))[:44]
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
    parts = [
        re.sub(r"\s+", " ", p).strip(" ,;")
        for p in text.split("\n")
    ]
    parts = [p for p in parts if p]
    if not parts:
        return None
    joined = ", ".join(parts)
    joined = re.sub(r"\s*,\s*", ", ", joined)
    joined = re.sub(r"(,\s*){2,}", ", ", joined).strip(" ,")
    return _sanitize_passport_address(joined)


def _sanitize_passport_address(raw: str | None) -> str | None:
    """Drop old-passport / file / PIN-label OCR tails glued onto the address."""
    if raw is None:
        return None
    s = str(raw).strip()
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
    return (s[:400] or None)


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
        # skip past them into street/city lines (spouse bleed).
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
    cleaned = _clean_person_name(val)
    if not cleaned:
        return False
    # Address / place bleed (comma + locality tokens).
    if "," in cleaned:
        return False
    if re.search(
        r"(?i)\b(?:urban|pin|university|room|sadan|lane|street|road|nagar|"
        r"pradesh|nadu|state|india|address|thota|block)\b",
        cleaned,
    ):
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
    if len(tokens) == 1:
        only = tokens[0]
        if len(only) < 5 or _NAME_OCR_CRUMB_RE.match(only):
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
        r"(?i)\b(?:legal|guardian|guardlan|curdian|lepai|name|of|ot|ol|"
        r"father|fother|foter|mother|mather|mothor|spouse|spouce|fn|afy|faf)\b",
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


# OCR often turns Issue → lssue / lssuo; do not require the leading "i".
_PLACE_OF_ISSUE_OCR = r"(?:l?issue|lssue|lssuo|issuc|issuance|issu)"
# OCR-tolerant: Birth → Blrth / Birih / Bith on CamScanner / PDF renders.
_PLACE_OF_BIRTH_LABEL_RE = re.compile(
    r"(?i)\bplace\s*of\s*(?:birth|blrth|birih|bith)\b"
)
_PLACE_OF_ISSUE_LABEL_RE = re.compile(
    rf"(?i)\bplace\s*of[.\s]*{_PLACE_OF_ISSUE_OCR}"
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
_ADDRESS_LABEL_RE = re.compile(r"(?i)\b(?:address|denl\s*/\s*address|qa\s*/\s*address)\b")


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


def _address_from_ocr_text(raw: str) -> str | None:
    """Keep every printed address line after a (possibly bilingual) Address label.

    Labels like ``qan/ Address`` do not start with ``address``, so a start-anchored
    ``_value_after_label`` miss would drop line 1 (e.g. TRIVENI COMPLEX…).
    """
    m = re.search(
        r"(?im)^[^\n]*\b(?:address|residential[ \t]*address)\b[ \t]*[:\-–—/]?[ \t]*(.*)$",
        raw or "",
    )
    if not m:
        return None
    same = (m.group(1) or "").strip()
    lines: list[str] = []
    if (
        same
        and not _is_noise_value(same)
        and not re.match(r"(?i)^(file|fileno|old passport|name of|pin\b)", same)
        and len(same) >= 6
    ):
        lines.append(same)
    for ln in (raw or "")[m.end() :].splitlines()[:12]:
        t = ln.strip()
        if not t:
            if len(lines) >= 3 or any(
                re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", x) for x in lines
            ):
                break
            continue
        if re.match(
            r"(?i)^(old passport|name of|file|fileno|passport|fke|ma\s*3|a3\s*/)",
            t,
        ):
            break
        if _is_noise_value(t):
            continue
        lines.append(t)
        if re.search(r"(?i)\bpin\s*:?\s*\d{6}\b", t):
            break
    lines = _prefer_full_address_lines(lines)
    joined = normalize_multiline_address("\n".join(lines)[:400])
    if joined and len(joined) >= 12:
        return joined
    return None


def _address_from_ocr_blocks(blocks: list[dict[str, Any]] | None) -> str | None:
    """Residential address under the Address label (page-2 / dual-page scans).

    Long address lines have a right-shifted *center* even when left-aligned with
    the Address header. Scoring by center-x then picks line 2 as “below” and
    drops line 1. Collect by left-edge alignment instead.
    """
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
        if not (
            _ADDRESS_LABEL_RE.search(text) or block_is_field_label(text, "address")
        ):
            continue
        label_left = x0 - (w0 / 2.0)
        lines: list[str] = []
        remainder = _ADDRESS_LABEL_RE.sub(" ", text)
        remainder = re.sub(r"(?i)\b(?:qan|denl|qa|den|went)\b", " ", remainder)
        remainder = re.sub(r"[/|:\-–—]+", " ", remainder)
        remainder = re.sub(r"\s+", " ", remainder).strip()
        if remainder and _is_address_line_candidate(remainder):
            lines.append(remainder)
        for page, cy, cx, w, _h, t2 in items:
            if page != page0 or t2 == text:
                continue
            if cy <= y0:
                continue
            left = cx - (w / 2.0)
            # Wide street lines share the label's left edge, not its center.
            if abs(left - label_left) > 180:
                continue
            if any(rx.search(t2) for rx in stop):
                if lines:
                    break
                continue
            if not _is_address_line_candidate(t2) and not re.search(
                r"(?i)\bpin\b|\b\d{6}\b", t2
            ):
                if lines:
                    break
                continue
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
        if joined and len(joined) >= 12:
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
        # ROI is only for garbled-but-present labels. Fully unlabeled pages
        # (CamScanner dropped Father/Mother) must fall through to the
        # unlabeled family-row path — not a mid-band name guess.
        if not idxs:
            return None
        for cand in values_in_field_roi(
            items, field_key, is_value=_is_parent_name_candidate
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
    if not father or not mother:
        label_father = [
            (cx, cy)
            for page, cy, cx, _w, _h, text in items
            if _FATHER_LABEL_FUZZY_RE.search(text) and not _MOTHER_LABEL_FUZZY_RE.search(text)
        ]
        label_mother = [
            (cx, cy)
            for page, cy, cx, _w, _h, text in items
            if _MOTHER_LABEL_FUZZY_RE.search(text)
        ]
        candidates = [
            (cx, cy, text)
            for page, cy, cx, _w, _h, text in items
            if _is_parent_name_candidate(text)
        ]
        if candidates and (label_father or label_mother):
            split_x: float | None = None
            if label_father and label_mother:
                split_x = (
                    sum(x for x, _ in label_father) / len(label_father)
                    + sum(x for x, _ in label_mother) / len(label_mother)
                ) / 2.0
            y_floor = min(
                [y for _, y in label_father] + [y for _, y in label_mother],
                default=0.0,
            )
            left: list[tuple[float, str]] = []
            right: list[tuple[float, str]] = []
            for cx, cy, text in candidates:
                if cy < y_floor - 5:
                    continue
                if split_x is None or cx <= split_x:
                    left.append((cy, text))
                else:
                    right.append((cy, text))
            left.sort(key=lambda t: t[0])
            right.sort(key=lambda t: t[0])
            if not father and left:
                father = _clean_person_name(left[0][1])
            if not mother and right:
                mother = _clean_person_name(right[0][1])
            if (not father or not mother) and left and not right:
                left_names = [n for _, t in left if (n := _clean_person_name(t))]
                if not father and left_names:
                    father = left_names[0]
                if not mother and len(left_names) > 1:
                    mother = left_names[1]

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
            r"(?i)\b(?:blok|block|h\.?\s*no|d\.?\s*no|room|road|street|lane|nagar|oad)\b",
            t,
        ):
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
            or re.search(r"(?i)\b(?:blok|block)\b", blob)
        ):
            continue
        names: list[str] = []
        addr: list[str] = []
        for text in texts:
            if _addr_piece(text):
                addr.append(re.sub(r"\s+", " ", text).strip(" ,"))
                continue
            if (
                len(names) < 3
                and _is_plausible_person_name(text)
                and len(text.split()) >= 2
                and "," not in text
            ):
                cleaned = _clean_person_name(text)
                if cleaned:
                    names.append(cleaned)
                continue
            if _addr_piece(text):
                addr.append(re.sub(r"\s+", " ", text).strip(" ,"))
        if len(names) < 3 or len(addr) < 2:
            continue
        out: dict[str, str] = {
            "father_name": names[0],
            "mother_name": names[1],
            "spouse_name": names[2],
        }
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
    if _passport_has_spouse_label(text, blocks):
        return True
    unlabeled = _unlabeled_family_row_from_blocks(blocks)
    spouse = unlabeled.get("spouse_name")
    return bool(spouse and _is_plausible_person_name(spouse))


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
        r"(?:surname|family[ \t]*name|last[ \t]*name|/surname)"
        r"(?:[ \t]*/[ \t]*nom)?",
        r"(?:given[ \t]*names?|first[ \t]*names?|forenames?|prenoms?|"
        r"place[ \t]*of[ \t]*birth|date[ \t]*of[ \t]*birth|sex|nationality|"
        r"passport|place[ \t]*of[ \t]*issue)",
    )
    surname = _name_from_block(surname_block) or _clean_person_name(
        _value_after_label(
            raw,
            r"(?:surname|family[ \t]*name|last[ \t]*name|/surname)"
            r"(?:[ \t]*/[ \t]*nom)?",
        )
    )
    # Reject values that are clearly the next field's label or a place string.
    if surname and (
        _is_noise_value(surname)
        or re.search(r"(?i)place of|birth|issue|nationality", surname)
        or "," in surname
    ):
        surname = None
    if surname:
        found["surname"] = surname
        # Next uppercase token line is often given names when label is missing.
        if "given_names" not in found:
            idx = raw.upper().find(surname.upper())
            if idx >= 0:
                after = raw[idx + len(surname) :]
                for ln in after.splitlines()[:4]:
                    cand = _clean_person_name(ln.strip())
                    if not cand:
                        continue
                    if cand.upper() == surname.upper():
                        continue
                    if re.search(r"\d", cand):
                        continue
                    if _NEXT_FIELD_LABEL_RE.match(cand) or re.search(
                        r"(?i)place of|date of|nationality|sex\b", cand
                    ):
                        break
                    found["given_names"] = cand
                    break

    given = _value_after_label(
        raw,
        r"(?:given[ \t]*names?|first[ \t]*names?|forenames?|prenoms?)",
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
        r"place[ \t]*of[ \t]*(?:birth|blrth|birih|bith)|lieu[ \t]*de[ \t]*naissance",
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

    # Biodata Place of Issue only — skip "Old Passport … Place of Issue" stamps.
    poi = None
    for poi_m in re.finditer(
        rf"(?im)^[^\n]*\bplace\s*of[.\s]*{_PLACE_OF_ISSUE_OCR}"
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
            found.pop("place_of_birth", None)

    # Birth place sometimes appears as "CITY, STATE" away from labels.
    if "place_of_birth" not in found:
        m = re.search(
            r"(?im)^([A-Z][A-Za-z .]{2,40},\s*[A-Z][A-Za-z ]{3,40})$",
            raw,
        )
        if m and not _is_noise_value(m.group(1)):
            found["place_of_birth"] = m.group(1).strip()[:80]

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
                found[key] = iso
                continue
        # Label on one line, date on next (common Indian layout).
        val = _value_after_label(raw, label)
        iso = _parse_flexible_date(val)
        if iso:
            found[key] = iso
        elif val:
            # Date may share the line with OCR junk — pull first date token.
            dm = re.search(_DATE_CAPTURE, val)
            if dm:
                iso = _parse_flexible_date(dm.group(1))
                if iso:
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
        r"name[ \t]*(?:of|ot)[ \t]*(?:father|foter|fother)"
        r"(?:[ \t]*/[ \t]*legal[ \t]*(?:guardian|guardlan|curdian))?|"
        r"father(?:'s)?[ \t]*name|foter|fother|name[ \t]*of[ \t]*guardian|"
        r"(?:legal[ \t]*)?(?:guardian|guardlan|curdian)|"
        r"reme[ \t]*of[ \t]*foter|lepai[ \t]*curdian"
    )
    mother_label = (
        r"name[ \t]*(?:of|ot)[ \t]*(?:mother|mather|mothor)|"
        r"mother(?:'s)?[ \t]*name|mather|name[ \t]*of[ \t]*maches"
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
    father = _name_from_block(father_block) or _person_name_after_label(
        raw,
        father_label,
    )
    if father and re.search(r"(?i)guardian|guardlan|lega|canrdian|parer|poner|foter|lepai", father):
        father = None
    if not father:
        # Do not let IGNORECASE apply to the name capture — OCR crumbs like
        # "on" / "Name" would otherwise match as continuation lines.
        fm = re.search(
            r"(?s)(?:[Ff]ather|[Ff]oter|[Gg]uardian|[Pp]arer|[Cc]urdian)[^\n]{0,60}\n"
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
    mother = _name_from_block(mother_block) or _person_name_after_label(
        raw,
        mother_label,
    )
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
        addr_tail = fam_line.group(4)
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
        for key in ("father_name", "mother_name", "spouse_name", "address"):
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


def _post_validate_passport_fields(
    fields: dict[str, Any],
    *,
    text: str | None = None,
    ocr_blocks: list[dict[str, Any]] | None = None,
    labeled: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Shared final gate: strip label/passport-no bleed from names, blank spouse, DOI OCR."""
    out = dict(fields) if isinstance(fields, dict) else {}

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

    # Universal non-destructive rule: never clear a field solely because its
    # label was garbled/missing. Value-shape / blank / parent-bleed still clear junk.
    if out.get("spouse_name"):
        kept = retain_if_valid_value(
            "spouse_name",
            out["spouse_name"],
            shape_ok=lambda v: (
                not _is_blank_spouse_value(v) and _is_plausible_person_name(v)
            ),
        )
        out["spouse_name"] = kept
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
        doi = (labeled or {}).get("date_of_issue")
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

    return out


def extract_passport_fields(
    text: str,
    *,
    ocr_blocks: list[dict[str, Any]] | None = None,
    ocr_mean_confidence: float | None = None,
) -> dict[str, Any]:
    """Return passport schema dict with confidence_scores / bounding_boxes / flags."""
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

    if fields.get("address"):
        fields["address"] = normalize_multiline_address(str(fields["address"]))

    if not fields.get("document_type"):
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
            if key in {"father_name", "mother_name", "spouse_name"}:
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
    elif re.search(r"(?i)republic\s*of\s*india|\bindian\b|\bindia\b", text or ""):
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
    pob_v = str(fields.get("place_of_birth") or "").strip()
    if addr_v and pob_v and addr_v.upper() == pob_v.upper():
        fields["address"] = None
        lab_addr = str(labeled.get("address") or "").strip()
        if lab_addr and lab_addr.upper() != pob_v.upper():
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
    ):
        fields["place_of_birth"] = None
    if fields.get("place_of_issue") and (
        _is_noise_value(str(fields["place_of_issue"]))
        or _is_nationality_as_place(str(fields["place_of_issue"]))
        or _is_postal_address_as_place(str(fields["place_of_issue"]))
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
    ):
        fields["place_of_birth"] = labeled["place_of_birth"]
    # Drop garbage document numbers from false MRZ line-2 matches.
    doc_no = str(fields.get("document_number") or "")
    if doc_no and not re.fullmatch(r"[A-Z0-9]{6,12}", doc_no):
        fields["document_number"] = None
    elif doc_no and re.search(r"(?i)ROOM|PIN|UNI|ADDR|SADAN", doc_no):
        fields["document_number"] = labeled.get("document_number") or None
    if not fields.get("document_number") and labeled.get("document_number"):
        fields["document_number"] = labeled["document_number"]
    # Prefer Indian passport shape when available.
    if labeled.get("document_number") and re.fullmatch(
        r"[A-Z]\d{7}", labeled["document_number"]
    ):
        fields["document_number"] = labeled["document_number"]
        from_mrz_keys.discard("document_number")

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
    return payload


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
    passport = _post_validate_passport_fields(passport)
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
