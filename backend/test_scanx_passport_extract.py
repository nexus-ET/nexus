"""ScanX passport field extraction — label leakage, blank spouse, DOI OCR."""

from __future__ import annotations

from unittest.mock import patch

from app.services.ocr_cleaner import _blocks_look_like_passport
from app.services.scanx_field_extract import extract_labeled_fields
from app.services.scanx_llm_passport import _parse_passport_payload
from app.services.scanx_embeddings import _ocr_line_is_noise
from app.services.scanx_label_map import (
    LABEL_FUZZY_THRESHOLD,
    block_is_field_label,
    match_passport_field_label,
)
from app.services.scanx_jobs import document_looks_like_passport
from app.services.scanx_passport import (
    attach_passport_to_fields,
    extract_passport_fields,
    _clean_person_name,
    _is_garbage_file_number,
    _is_ocr_junk_text_value,
    native_pdf_text_needs_ocr,
    _is_plausible_person_name,
    _post_validate_passport_fields,
    strip_non_passport_comments,
    text_has_enough_passport_evidence,
    _tidy_passport_address,
)
from app.services.scanx_type_classify import classify_document_type


def _extract(text: str, blocks=None):
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value={},
    ):
        return extract_passport_fields(text, ocr_blocks=blocks)


INDIAN_PAGE2_OCR = """
REPUBLIC OF INDIA
Type / Country Code / Passport No.
P IND S7766566
REGURI
ANIRUDH
Nationality / Sex / Date of Birth
INDIAN M 16/12/1999
Place of Birth
KARIMNAGAR,TELANGANA
Place of.lssuo
HYDERABAD
Date of lssue ww Onof sptry
22/11/2018 21/11/2028
P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<
7766566<91ND9912164M2811213<<<<<<<<<<<<<<<8
afy / Name of Father / Legal Guardlan S7766566
ANIL KUMAR REGURI
Name of Mothor
SRILATHA REGURI
Name of Spouse
went / Address
H NO:3-78/1,VELICHAL
RAMADUGU,KARIMNAGAR
PIN:505451,TELANGANA,INDIA
"""

ARAVIND_ISSUE_OCR = """
REPUBLIC OF INDIA
Surname
ANNADURAI
Given Name(s)
ARAVIND BHARATHI
Date of Birth
15/08/1985
Place of Birth
ERODE,TAMIL NADU
Place of Issue
CHENNAI
Date of issue
15/03/2021
Date of Expiry
14/03/2031
Passport No.
U9663905
P<INDANNADURAI<<ARAVIND<BHARATHI<<<<<<<<<<<<
U9663905<8IND8508155M3103142<<<<<<<<<<<<<<<
"""


def test_indian_page2_father_is_name_not_label_or_passport_number():
    result = _extract(INDIAN_PAGE2_OCR)
    assert result.get("father_name") == "ANIL KUMAR REGURI"
    assert "guardlan" not in str(result.get("father_name") or "").lower()
    assert "S7766566" not in str(result.get("father_name") or "")
    assert result.get("mother_name") == "SRILATHA REGURI"
    assert result.get("document_number") == "S7766566"


def test_blank_spouse_stays_empty_despite_went_address_ocr():
    result = _extract(INDIAN_PAGE2_OCR)
    assert not result.get("spouse_name")


def test_date_of_issue_from_lssue_ocr_variant():
    result = _extract(INDIAN_PAGE2_OCR)
    assert result.get("date_of_issue") == "22-11-2018"
    assert result.get("date_of_expiry") is None


def test_generic_fields_do_not_emit_father_label_remnant():
    fields = extract_labeled_fields(INDIAN_PAGE2_OCR)
    father_vals = [
        f.get("value")
        for f in fields
        if "father" in (f.get("label") or "").lower()
    ]
    assert not any(
        "guardlan" in str(v).lower() or "S7766566" in str(v) for v in father_vals
    )
    spouse_vals = [
        f.get("value")
        for f in fields
        if "spouse" in (f.get("label") or "").lower()
    ]
    assert not any(str(v).strip().lower() in {"went", "went / address"} for v in spouse_vals)


def test_aravind_style_date_of_issue_still_extracts():
    result = _extract(ARAVIND_ISSUE_OCR)
    assert result.get("date_of_issue") == "15-03-2021"
    assert result.get("surname") == "ANNADURAI"
    assert "ARAVIND" in str(result.get("given_names") or "").upper()
    assert result.get("document_number") == "U9663905"


def test_clean_person_name_drops_label_leakage_and_garbage_tokens():
    assert _clean_person_name("fn afy Guardlan") is None
    assert _clean_person_name("/ Legal Guardlan S7766566") is None
    assert _clean_person_name("went") is None
    assert not _is_plausible_person_name("went")
    assert _clean_person_name("ANIL KUMAR REGURI") == "ANIL KUMAR REGURI"


def test_llm_payload_parser_rejects_junk_names():
    parsed = _parse_passport_payload(
        '{"father_name":"/ Legal Guardlan S7766566","spouse_name":"went",'
        '"mother_name":"SRILATHA REGURI","date_of_issue":"22/11/2018"}'
    )
    assert "father_name" not in parsed
    assert "spouse_name" not in parsed
    assert parsed.get("mother_name") == "SRILATHA REGURI"
    assert parsed.get("date_of_issue") in {"22-11-2018", "22/11/2018"}


def test_attach_passport_does_not_surface_generic_father_junk():
    passport = _extract(INDIAN_PAGE2_OCR)
    categorized = {
        "version": 1,
        "fields": [
            {"label": "Father's Name", "value": "/ Legal Guardlan S7766566"},
            {"label": "Spouse Name", "value": "went"},
        ],
        "categories": [
            {
                "id": "identity",
                "label": "Identity",
                "items": [
                    {"label": "Father's Name", "value": "/ Legal Guardlan S7766566"},
                    {"label": "Spouse Name", "value": "went"},
                ],
            }
        ],
    }
    out = attach_passport_to_fields(categorized, passport)
    assert out["passport"].get("father_name") == "ANIL KUMAR REGURI"
    assert not out["passport"].get("spouse_name")
    other_vals = [
        item.get("value")
        for cat in out.get("categories") or []
        for item in cat.get("items") or []
    ]
    assert not any("Guardlan" in str(v) for v in other_vals)
    assert not any(str(v).strip().lower() == "went" for v in other_vals)


def test_post_validate_strips_junk_names_and_recovers_doi():
    out = _post_validate_passport_fields(
        {
            "father_name": "/ Legal Guardlan S7766566",
            "spouse_name": "went",
            "mother_name": "SRILATHA REGURI",
            "date_of_issue": None,
        },
        text=INDIAN_PAGE2_OCR,
    )
    assert out.get("father_name") is None
    assert not out.get("spouse_name")
    assert out.get("mother_name") == "SRILATHA REGURI"
    assert out.get("date_of_issue") == "22-11-2018"


def test_ocr_cleaner_detects_passport_pages():
    class _Blk:
        def __init__(self, raw: str):
            self.raw_ocr_text = raw
            self.cleaned_text = raw

    assert _blocks_look_like_passport(
        [_Blk("P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<")]
    )
    assert not _blocks_look_like_passport(
        [_Blk("TAMIL NADU HIGHER SECONDARY COURSE CERTIFICATE")]
    )


THREE_LINE_ADDRESS_OCR = """
REPUBLIC OF INDIA
Name of Father / Legal Guardian
SANDEEP PANJABRAO DHUMALE
Name of Mother
DEEPA SANDEEP DHUMALE
Name of Spouse
qan/ Address
TRIVENI COMPLEX,ABOVE SBI BRANCH
RUKHMINI NAGAR,AMRAVATI CITY
PIN:444606,MAHARASHTRA,INDIA
File No.
NG1063937171819
"""


def _box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_three_line_address_keeps_first_line():
    result = _extract(THREE_LINE_ADDRESS_OCR)
    addr = (result.get("address") or "").upper()
    assert "TRIVENI COMPLEX" in addr
    assert "RUKHMINI NAGAR" in addr
    assert "444606" in addr
    # Wide line-1 boxes must not lose the first line to center-x scoring.
    blocks = [
        {
            "text": "qan/ Address",
            "cleaned_text": "qan/ Address",
            "bounding_box": _box(161, 964, 324, 55),
            "page_index": 1,
        },
        {
            "text": "TRIVENI COMPLEX,ABOVE SBI BRANCH",
            "cleaned_text": "TRIVENI COMPLEX,ABOVE SBI BRANCH",
            "bounding_box": _box(188, 1035, 1558, 92),
            "page_index": 1,
        },
        {
            "text": "RUKHMINI NAGAR,AMRAVATI CITY",
            "cleaned_text": "RUKHMINI NAGAR,AMRAVATI CITY",
            "bounding_box": _box(186, 1218, 1364, 93),
            "page_index": 1,
        },
        {
            "text": "PIN:444606,MAHARASHTRA,INDIA",
            "cleaned_text": "PIN:444606,MAHARASHTRA,INDIA",
            "bounding_box": _box(187, 1398, 1360, 91),
            "page_index": 1,
        },
    ]
    spatial = _extract("qan/ Address\n", blocks)
    spatial_addr = (spatial.get("address") or "").upper()
    assert "TRIVENI COMPLEX" in spatial_addr
    assert "RUKHMINI NAGAR" in spatial_addr
    assert "444606" in spatial_addr


def test_file_no_parsed_from_synthetic_ocr():
    result = _extract(THREE_LINE_ADDRESS_OCR)
    assert result.get("file_number") == "NG1063937171819"
    assert not _ocr_line_is_noise("NG1063937171819")
    fileno_ocr = THREE_LINE_ADDRESS_OCR.replace("File No.", "FILENO")
    assert _extract(fileno_ocr).get("file_number") == "NG1063937171819"


def test_pita_no_dates_rejected_as_file_number():
    junk = "Pita No. 22/11/2018 21/11/2028"
    assert _is_garbage_file_number(junk)
    result = _extract(
        INDIAN_PAGE2_OCR + "\nPita No.\n22/11/2018 21/11/2028\n"
    )
    fno = str(result.get("file_number") or "")
    assert "PITA" not in fno.upper()
    assert "22/11/2018" not in fno
    assert "21/11/2028" not in fno
    parsed = _parse_passport_payload(
        '{"file_number":"Pita No. 22/11/2018 21/11/2028"}'
    )
    assert "file_number" not in parsed
    out = _post_validate_passport_fields({"file_number": junk})
    assert not out.get("file_number")


ARAVIND_UNLABELED_FAMILY_OCR = """
REPUBLIC OF INDIA
SUNDARAM ANNADURAI
VENKATRAMAN NAGALAKSHMI
LAKXMI ARAVIND
BLOK A OAD
BLOCK 3/C1, JAINS GREEN ACRES. 91 DARGA ROAD
ZAMEEN PALLAVARAM,CHENNAI
PIN:600043,TAMIL NADU,INDIA
"""


def _aravind_family_blocks():
    """Page-2 blocks with garbled labels (no readable Spouse/Father text)."""
    return [
        {
            "page": 1,
            "order": 0,
            "text": "SUNDARAM ANNADURAI",
            "cleaned_text": "SUNDARAM ANNADURAI",
            "bounding_box": _box(100, 200, 400, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 1,
            "text": "o / e e",
            "cleaned_text": "o / e e",
            "bounding_box": _box(80, 210, 60, 30),
            "conf": 0.4,
        },
        {
            "page": 1,
            "order": 2,
            "text": "VENKATRAMAN NAGALAKSHMI",
            "cleaned_text": "VENKATRAMAN NAGALAKSHMI",
            "bounding_box": _box(100, 260, 420, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 3,
            "text": "nod w/",
            "cleaned_text": "nod w/",
            "bounding_box": _box(80, 270, 60, 30),
            "conf": 0.5,
        },
        {
            "page": 1,
            "order": 4,
            "text": "LAKXMI ARAVIND",
            "cleaned_text": "LAKXMI ARAVIND",
            "bounding_box": _box(100, 320, 380, 40),
            "conf": 0.995,
        },
        {
            "page": 1,
            "order": 5,
            "text": "BLOK A OAD",
            "cleaned_text": "BLOK A OAD",
            "bounding_box": _box(100, 380, 200, 40),
            "conf": 0.75,
        },
        {
            "page": 1,
            "order": 6,
            "text": "BLOCK 3/C1, JAINS GREEN ACRES. 91 DARGA ROAD",
            "cleaned_text": "BLOCK 3/C1, JAINS GREEN ACRES. 91 DARGA ROAD",
            "bounding_box": _box(100, 390, 900, 45),
            "conf": 0.95,
        },
        {
            "page": 1,
            "order": 7,
            "text": "ZAMEEN PALLAVARAM,CHENNAI",
            "cleaned_text": "ZAMEEN PALLAVARAM,CHENNAI",
            "bounding_box": _box(100, 450, 500, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 8,
            "text": "PIN:600043,TAMIL NADU,INDIA",
            "cleaned_text": "PIN:600043,TAMIL NADU,INDIA",
            "bounding_box": _box(100, 510, 520, 40),
            "conf": 0.99,
        },
    ]


def test_spouse_lakxmi_aravind_kept_all_caps_two_tokens():
    assert _is_plausible_person_name("LAKXMI ARAVIND")
    result = _extract(ARAVIND_UNLABELED_FAMILY_OCR, _aravind_family_blocks())
    assert result.get("spouse_name") is None
    assert result.get("father_name") == "SUNDARAM ANNADURAI"
    assert result.get("mother_name") == "VENKATRAMAN NAGALAKSHMI"


def test_address_prefers_full_block_line_over_blok_crumb():
    result = _extract(ARAVIND_UNLABELED_FAMILY_OCR, _aravind_family_blocks())
    addr = (result.get("address") or "").upper()
    assert "BLOCK 3/C1" in addr
    assert "JAINS GREEN ACRES" in addr
    assert "DARGA ROAD" in addr
    assert "BLOK A OAD" not in addr


def test_garbage_spouse_went_still_rejected():
    assert not _is_plausible_person_name("went")
    result = _extract(INDIAN_PAGE2_OCR)
    assert not result.get("spouse_name")


def test_garbled_spouse_label_keeps_lakxmi_aravind_via_post_validate():
    """Failed spouse-label match must not wipe a valid captured name."""
    out = _post_validate_passport_fields(
        {
            "father_name": "SUNDARAM ANNADURAI",
            "mother_name": "VENKATRAMAN NAGALAKSHMI",
            "spouse_name": "LAKXMI ARAVIND",
        },
        text="REPUBLIC OF INDIA\nnod w/\nBLOK A OAD\n",
        ocr_blocks=None,
    )
    assert out.get("spouse_name") == "LAKXMI ARAVIND"


def test_garbled_father_label_keeps_plausible_father_name():
    blocks = [
        {
            "page": 1,
            "order": 0,
            "text": "Nane ot Foter / Lepai Curdian",
            "cleaned_text": "Nane ot Foter / Lepai Curdian",
            "bounding_box": _box(80, 180, 420, 35),
            "conf": 0.55,
        },
        {
            "page": 1,
            "order": 1,
            "text": "SUNDARAM ANNADURAI",
            "cleaned_text": "SUNDARAM ANNADURAI",
            "bounding_box": _box(100, 230, 400, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 2,
            "text": "Name of Mother",
            "cleaned_text": "Name of Mother",
            "bounding_box": _box(80, 280, 300, 35),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 3,
            "text": "VENKATRAMAN NAGALAKSHMI",
            "cleaned_text": "VENKATRAMAN NAGALAKSHMI",
            "bounding_box": _box(100, 330, 420, 40),
            "conf": 0.99,
        },
    ]
    ocr = (
        "REPUBLIC OF INDIA\n"
        "Nane ot Foter / Lepai Curdian\n"
        "SUNDARAM ANNADURAI\n"
        "Name of Mother\n"
        "VENKATRAMAN NAGALAKSHMI\n"
    )
    result = _extract(ocr, blocks)
    assert result.get("father_name") == "SUNDARAM ANNADURAI"
    # Post-validate must not clear father just because the label was garbled.
    out = _post_validate_passport_fields(
        {"father_name": "SUNDARAM ANNADURAI"},
        text="Nane ot Foter / Lepai Curdian\n",
    )
    assert out.get("father_name") == "SUNDARAM ANNADURAI"


def test_fuzzy_spouse_label_sp0use_and_spouce_anchor():
    assert match_passport_field_label("Sp0use") == "spouse_name"
    assert match_passport_field_label("Name of Spouce") == "spouse_name"
    assert block_is_field_label("Sp0use", "spouse_name")
    assert block_is_field_label("Name of Spouce", "spouse_name")
    # Confusables: Pita No. must not become File No.; Spouse != Father.
    assert match_passport_field_label("Pita No.") != "file_number"
    assert match_passport_field_label("Spouse") != "father_name"
    assert LABEL_FUZZY_THRESHOLD == 82

    blocks = [
        {
            "page": 1,
            "order": 0,
            "text": "Name of Spouce",
            "cleaned_text": "Name of Spouce",
            "bounding_box": _box(80, 300, 280, 35),
            "conf": 0.7,
        },
        {
            "page": 1,
            "order": 1,
            "text": "LAKXMI ARAVIND",
            "cleaned_text": "LAKXMI ARAVIND",
            "bounding_box": _box(100, 350, 380, 40),
            "conf": 0.7931,
        },
    ]
    result = _extract(
        "REPUBLIC OF INDIA\nName of Spouce\nLAKXMI ARAVIND\n",
        blocks,
    )
    assert result.get("spouse_name") == "LAKXMI ARAVIND"


def test_garbage_went_still_rejected_universal():
    assert not _is_plausible_person_name("went")
    out = _post_validate_passport_fields({"spouse_name": "went", "father_name": "went"})
    assert not out.get("spouse_name")
    assert not out.get("father_name")
    result = _extract(INDIAN_PAGE2_OCR)
    assert not result.get("spouse_name")


def test_pita_no_dates_still_rejected_as_file_number():
    junk = "Pita No. 22/11/2018 21/11/2028"
    assert _is_garbage_file_number(junk)
    assert match_passport_field_label("Pita No.") != "file_number"
    out = _post_validate_passport_fields({"file_number": junk})
    assert not out.get("file_number")


def test_by_order_never_father_keeps_lakxmi_spouse():
    """Cover-note 'BY ORDER' must not be a person name; spouse shape still kept."""
    assert not _is_plausible_person_name("BY ORDER")
    assert not _is_plausible_person_name("BY ORDER OF")
    assert _clean_person_name("BY ORDER") is None
    assert _clean_person_name("BY ORDER OF") is None
    assert not block_is_field_label("BY ORDER OF", "father_name")
    assert not block_is_field_label(
        "THESE ARE TO REQUEST AND REQUIRE IN THE NAME", "father_name"
    )
    assert block_is_field_label(
        "Name of Father / Legal Guardian", "father_name"
    )

    cover_and_family = (
        "REPUBLIC OF INDIA\n"
        "OR SHE MAY STAND IN NEED.\n"
        "BY ORDER OF\n"
        "THE PRESIDENT OF THE REPUBLIC OF INDIA\n"
        "SUNDARAM ANNADURAI\n"
        "VENKATRAMAN NAGALAKSHMI\n"
        "Name of Spouce\n"
        "LAKXMI ARAVIND\n"
        "BLOCK 3/C1, JAINS GREEN ACRES\n"
        "PIN:600043,TAMIL NADU,INDIA\n"
    )
    blocks = [
        {
            "page": 0,
            "order": 0,
            "text": "BY ORDER OF",
            "cleaned_text": "BY ORDER OF",
            "bounding_box": _box(100, 100, 200, 30),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 1,
            "text": "OR SHE MAY STAND IN NEED.",
            "cleaned_text": "OR SHE MAY STAND IN NEED.",
            "bounding_box": _box(100, 140, 400, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 0,
            "text": "SUNDARAM ANNADURAI",
            "cleaned_text": "SUNDARAM ANNADURAI",
            "bounding_box": _box(100, 200, 400, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 1,
            "text": "VENKATRAMAN NAGALAKSHMI",
            "cleaned_text": "VENKATRAMAN NAGALAKSHMI",
            "bounding_box": _box(100, 260, 420, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 2,
            "text": "Name of Spouce",
            "cleaned_text": "Name of Spouce",
            "bounding_box": _box(80, 300, 280, 35),
            "conf": 0.7,
        },
        {
            "page": 1,
            "order": 3,
            "text": "LAKXMI ARAVIND",
            "cleaned_text": "LAKXMI ARAVIND",
            "bounding_box": _box(100, 350, 380, 40),
            "conf": 0.99,
        },
        {
            "page": 1,
            "order": 4,
            "text": "BLOCK 3/C1, JAINS GREEN ACRES",
            "cleaned_text": "BLOCK 3/C1, JAINS GREEN ACRES",
            "bounding_box": _box(100, 400, 500, 40),
            "conf": 0.95,
        },
        {
            "page": 1,
            "order": 5,
            "text": "PIN:600043,TAMIL NADU,INDIA",
            "cleaned_text": "PIN:600043,TAMIL NADU,INDIA",
            "bounding_box": _box(100, 450, 420, 40),
            "conf": 0.99,
        },
    ]
    result = _extract(cover_and_family, blocks)
    assert result.get("father_name") != "BY ORDER"
    assert result.get("father_name") != "BY ORDER OF"
    assert "ORDER" not in str(result.get("father_name") or "").upper()
    assert result.get("father_name") == "SUNDARAM ANNADURAI"
    assert result.get("mother_name") == "VENKATRAMAN NAGALAKSHMI"
    assert result.get("spouse_name") == "LAKXMI ARAVIND"
    # Garbled spouse/father labels must not wipe a valid spouse via post-validate.
    out = _post_validate_passport_fields(
        {
            "father_name": "BY ORDER",
            "spouse_name": "LAKXMI ARAVIND",
        },
        text="BY ORDER OF\nName of Spouce\n",
    )
    assert not out.get("father_name")
    assert out.get("spouse_name") == "LAKXMI ARAVIND"


def test_city_place_of_issue_survives_parent_name_junk_filter():
    """Cities are rejected as person names but must remain valid places of issue.

    CamScanner layout: Date of Issue / CHENNAI / Place of lssue / birth city.
    """
    assert not _is_plausible_person_name("CHENNAI")
    assert not _is_plausible_person_name("BY ORDER")
    assert _clean_person_name("BY ORDER") is None

    kept = _post_validate_passport_fields(
        {
            "place_of_issue": "CHENNAI",
            "place_of_birth": "ERODE,TAMIL NADU",
            "father_name": "BY ORDER",
            "mother_name": "VENKATRAMAN NAGALAKSHMI",
            "spouse_name": "LAKXMI ARAVIND",
        }
    )
    assert kept.get("place_of_issue") == "CHENNAI"
    assert not kept.get("father_name")
    assert kept.get("mother_name") == "VENKATRAMAN NAGALAKSHMI"
    assert kept.get("spouse_name") == "LAKXMI ARAVIND"

    linear = (
        "REPUBLIC OF INDIA\n"
        "15/03/2021 a Rrea/ Date of Issue CHENNAI Place of lssue "
        "ERODE,TAMIL NADU Place of Birth 15/08/1985\n"
        "ARAVIND BHARATHI\n"
        "ANNADURAI\n"
    )
    blocks = [
        {
            "page": 1,
            "order": 0,
            "text": "CHENNAI",
            "cleaned_text": "CHENNAI",
            "bounding_box": _box(430, 870, 80, 30),
            "conf": 0.95,
        },
        {
            "page": 1,
            "order": 1,
            "text": "Place of Birth",
            "cleaned_text": "Place of Birth",
            "bounding_box": _box(540, 900, 140, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 2,
            "text": "a Rrea/ Date of Issue",
            "cleaned_text": "a Rrea/ Date of Issue",
            "bounding_box": _box(360, 940, 160, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 3,
            "text": "Place of lssue",
            "cleaned_text": "Place of lssue",
            "bounding_box": _box(380, 942, 140, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 4,
            "text": "ERODE,TAMIL NADU",
            "cleaned_text": "ERODE,TAMIL NADU",
            "bounding_box": _box(480, 970, 200, 30),
            "conf": 0.95,
        },
    ]
    result = _extract(linear, blocks)
    assert result.get("place_of_issue") == "CHENNAI"
    assert "ERODE" in str(result.get("place_of_birth") or "").upper()
    assert result.get("father_name") != "CHENNAI"
    assert result.get("father_name") != "BY ORDER"


def test_hr_indian_rejected_as_place_of_birth_when_city_present():
    """PDF OCR puts nationality (HR/INDIAN) above Place of Birth; city below must win.

    JPEG scans already keep CHENNAI / ERODE,TAMIL NADU — do not regress those.
    """
    from app.services.scanx_passport import _is_nationality_as_place, _is_place_candidate

    assert _is_nationality_as_place("HR/INDIAN")
    assert _is_nationality_as_place("HA/INDIAN")
    assert _is_nationality_as_place("M/INDIAN")
    assert _is_nationality_as_place("INDIAN")
    assert _is_nationality_as_place("IND")
    assert not _is_nationality_as_place("CHENNAI")
    assert not _is_nationality_as_place("ERODE, TAMIL NADU")
    assert not _is_place_candidate("HR/INDIAN")
    assert _is_place_candidate("JALGOAN,MAHARASHTRA")

    text = (
        "REPUBLIC OF INDIA\n"
        "DHUMALE\n"
        "SAMRUDDHI SANDEEP\n"
        "HR/INDIAN F 30/09/1998\n"
        "Place of Birth\n"
        "JALGOAN,MAHARASHTRA\n"
        "Place of Issue\n"
        "NAGPUR\n"
        "Date of Issue 01/08/2019 Date of Expiry 31/07/2029\n"
    )
    # Geometry mimics PDF RapidOCR: nationality just above the birth label,
    # real city slightly below-right (would previously win via "above").
    blocks = [
        {
            "page": 0,
            "order": 0,
            "text": "HR/INDIAN",
            "cleaned_text": "HR/INDIAN",
            "bounding_box": _box(700, 1320, 450, 80),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 1,
            "text": "G e/ Place of Birth",
            "cleaned_text": "G e/ Place of Birth",
            "bounding_box": _box(700, 1420, 445, 50),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 2,
            "text": "JALGOAN,MAHARASHTRA",
            "cleaned_text": "JALGOAN,MAHARASHTRA",
            "bounding_box": _box(720, 1490, 680, 70),
            "conf": 0.95,
        },
        {
            "page": 0,
            "order": 3,
            "text": "Place of Issue",
            "cleaned_text": "Place of Issue",
            "bounding_box": _box(980, 1570, 280, 40),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 4,
            "text": "NAGPUR",
            "cleaned_text": "NAGPUR",
            "bounding_box": _box(900, 1630, 160, 40),
            "conf": 0.95,
        },
    ]
    result = _extract(text, blocks)
    pob = str(result.get("place_of_birth") or "").upper()
    assert "INDIAN" not in pob
    assert "JALGOAN" in pob or "MAHARASHTRA" in pob
    assert result.get("place_of_issue") == "NAGPUR"

    jpeg_style = _extract(
        "Surname\nANNADURAI\nPlace of Birth\nERODE, TAMIL NADU\n"
        "Place of Issue\nCHENNAI\n",
        [
            {
                "page": 0,
                "order": 0,
                "text": "Place of Birth",
                "cleaned_text": "Place of Birth",
                "bounding_box": _box(100, 400, 160, 30),
                "conf": 0.9,
            },
            {
                "page": 0,
                "order": 1,
                "text": "ERODE, TAMIL NADU",
                "cleaned_text": "ERODE, TAMIL NADU",
                "bounding_box": _box(100, 450, 220, 30),
                "conf": 0.95,
            },
            {
                "page": 0,
                "order": 2,
                "text": "Place of Issue",
                "cleaned_text": "Place of Issue",
                "bounding_box": _box(100, 520, 160, 30),
                "conf": 0.9,
            },
            {
                "page": 0,
                "order": 3,
                "text": "CHENNAI",
                "cleaned_text": "CHENNAI",
                "bounding_box": _box(100, 490, 120, 30),
                "conf": 0.95,
            },
        ],
    )
    assert "ERODE" in str(jpeg_style.get("place_of_birth") or "").upper()
    assert jpeg_style.get("place_of_issue") == "CHENNAI"


def test_long_city_place_of_issue_not_mrz_rejected():
    """VISAKHAPATNAM (13 letters) must not be treated as an MRZ crumb.

    Vishu Priya PDF OCR: city sits below Place of issue; given name above and
    signature to the left previously blanked place_of_issue after geometry
    latched onto VISHNUPRIYA.
    """
    from app.services.scanx_passport import (
        _is_holder_name_as_place,
        _is_place_candidate,
    )

    assert _is_place_candidate("VISAKHAPATNAM")
    assert _is_place_candidate("CHENNAI")
    assert _is_place_candidate("PRODDATUR,ANDHRA PRADESH")
    assert not _is_place_candidate("P<INDMARTHALA<<VISHNUPRIYA<<<<<<<<<<<<<<<<<<")
    assert not _is_place_candidate("U1861386<31ND9910230")
    assert not _is_place_candidate(
        "VISHNUPRIYA", given_names="VISHNUPRIYA", surname="MARTHALA"
    )
    assert _is_holder_name_as_place(
        "VISHNUPRIYA", given_names="VISHNUPRIYA", surname="MARTHALA"
    )
    assert _is_holder_name_as_place(
        "MARTHALA", given_names="VISHNUPRIYA", surname="MARTHALA"
    )

    text = (
        "REPUBLIC OF INDIA\n"
        "MARTHALA\n"
        "VISHNUPRIYA\n"
        "Date of Birth\n"
        "23/10/1999 F\n"
        "Place of Birth\n"
        "PRODDATUR,ANDHRA PRADESH\n"
        "Place of issue\n"
        "VISAKHAPATNAM\n"
        "M.Vishnu priya e/Date of issue aa/ Date of Expiny\n"
        "26/12/2019 25/12/2029\n"
        "P<INDMARTHALA<<VISHNUPRIYA<<<<<<<<<<<<<<<<<<\n"
    )
    blocks = [
        {
            "page": 0,
            "order": 0,
            "text": "VISHNUPRIYA",
            "cleaned_text": "VISHNUPRIYA",
            "bounding_box": _box(759, 1183, 381, 51),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 1,
            "text": "zer/ Place of Birth",
            "cleaned_text": "zer/ Place of Birth",
            "bounding_box": _box(755, 1389, 348, 41),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 2,
            "text": "PRODDATUR,ANDHRA PRADESH",
            "cleaned_text": "PRODDATUR,ANDHRA PRADESH",
            "bounding_box": _box(756, 1443, 833, 57),
            "conf": 0.95,
        },
        {
            "page": 0,
            "order": 3,
            "text": "Place of issue",
            "cleaned_text": "Place of issue",
            "bounding_box": _box(754, 1515, 474, 50),
            "conf": 0.9,
        },
        {
            "page": 0,
            "order": 4,
            "text": "VISAKHAPATNAM",
            "cleaned_text": "VISAKHAPATNAM",
            "bounding_box": _box(760, 1578, 456, 54),
            "conf": 0.95,
        },
        {
            "page": 0,
            "order": 5,
            "text": "M.Vishnu priya",
            "cleaned_text": "M.Vishnu priya",
            "bounding_box": _box(143, 1568, 584, 143),
            "conf": 0.8,
        },
        {
            "page": 0,
            "order": 6,
            "text": "e/Date of issue",
            "cleaned_text": "e/Date of issue",
            "bounding_box": _box(753, 1647, 461, 49),
            "conf": 0.9,
        },
    ]
    result = _extract(text, blocks)
    assert result.get("place_of_issue") == "VISAKHAPATNAM"
    pob = str(result.get("place_of_birth") or "").upper()
    assert "PRODDATUR" in pob
    assert "INDIAN" not in pob
    assert result.get("given_names") == "VISHNUPRIYA"
    assert result.get("place_of_issue") != result.get("given_names")


def test_place_of_issue_rejects_pin_address_prefers_office_city():
    """Issuing office is the city beside Place of Issue — not the address PIN line.

    Venugopal-style dual-page OCR: PIN sits above the Old Passport stamp that
    embeds "Place of Issue"; biodata has VISAKHAPATNAM under the real label.
    Address may still keep the PIN line.
    """
    from app.services.scanx_passport import (
        _is_issuing_office_candidate,
        _is_place_candidate,
        _is_postal_address_as_place,
    )

    pin = "PIN:522002,ANDHRA PRADESH,INDIA"
    assert _is_postal_address_as_place(pin)
    assert not _is_issuing_office_candidate(pin)
    assert _is_place_candidate("PRODDATUR,ANDHRA PRADESH")
    assert not _is_issuing_office_candidate("PRODDATUR,ANDHRA PRADESH")
    assert _is_issuing_office_candidate("VISAKHAPATNAM")
    assert _is_issuing_office_candidate("1 VISAKHAPATNAM")

    text = (
        "REPUBLIC OF INDIA\n"
        "qa /Address\n"
        "D.NO.27-7-11,4TH LANE\n"
        "KANNAVARI THOTA,GUNTUR\n"
        "PIN:522002,ANDHRA PRADESH,INDIA\n"
        "Old Passport No. with Date and Place of Issue\n"
        "File No.\n"
        "VS2068930943915\n"
        "Surname\n"
        "PAMIDI\n"
        "VENU GOPAL\n"
        "INDIAN M 07/10/1994\n"
        "Place of Birth\n"
        "TANGUTUR, ANDHRA PRADESH\n"
        "Place of Issue\n"
        "1 VISAKHAPATNAM\n"
        "Date of Issue 26/11/2015 Date of Expiry 25/11/2025\n"
    )
    blocks = [
        {
            "page": 0,
            "order": 0,
            "text": "PIN:522002,ANDHRA PRADESH,INDIA",
            "cleaned_text": "PIN:522002,ANDHRA PRADESH,INDIA",
            "bounding_box": _box(100, 200, 400, 30),
            "conf": 0.95,
        },
        {
            "page": 0,
            "order": 1,
            "text": "Old Passport No. with Date and Place of Issue",
            "cleaned_text": "Old Passport No. with Date and Place of Issue",
            "bounding_box": _box(100, 250, 500, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 2,
            "text": "Place of Birth",
            "cleaned_text": "Place of Birth",
            "bounding_box": _box(100, 400, 160, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 3,
            "text": "TANGUTUR, ANDHRA PRADESH",
            "cleaned_text": "TANGUTUR, ANDHRA PRADESH",
            "bounding_box": _box(100, 450, 280, 30),
            "conf": 0.95,
        },
        {
            "page": 1,
            "order": 4,
            "text": "Place of Issue",
            "cleaned_text": "Place of Issue",
            "bounding_box": _box(100, 520, 160, 30),
            "conf": 0.9,
        },
        {
            "page": 1,
            "order": 5,
            "text": "1 VISAKHAPATNAM",
            "cleaned_text": "1 VISAKHAPATNAM",
            "bounding_box": _box(100, 570, 200, 30),
            "conf": 0.95,
        },
    ]
    result = _extract(text, blocks)
    assert result.get("place_of_issue") == "VISAKHAPATNAM"
    assert "PIN" not in str(result.get("place_of_issue") or "").upper()
    assert "522002" not in str(result.get("place_of_issue") or "")
    pob = str(result.get("place_of_birth") or "").upper()
    assert "TANGUTUR" in pob
    addr = str(result.get("address") or "").upper()
    assert "522002" in addr or "PIN" in addr


# --- Blank holder-name fields must stay blank (no sibling copy) ---

GIVEN_ONLY_OCR = """
REPUBLIC OF INDIA
Surname
Given Name(s)
SAMRIDDHI
Nationality / Sex / Date of Birth
INDIAN F 01/01/2000
Place of Birth
DELHI
P<IND<<SAMRIDDHI<<<<<<<<<<<<<<<<<<<<<<<
S1234567<8IND0001014F3001011<<<<<<<<<<<<<<<0
"""

SURNAME_ONLY_OCR = """
REPUBLIC OF INDIA
Surname
ANNADURAI
Given Name(s)
Nationality / Sex / Date of Birth
INDIAN M 15/08/1985
Place of Birth
ERODE,TAMIL NADU
P<INDANNADURAI<<<<<<<<<<<<<<<<<<<<<<<<<<<
U9663905<8IND8508155M3103142<<<<<<<<<<<<<<<
"""


def test_given_name_only_keeps_surname_blank():
    """Surname label empty + MRZ empty family → do not copy given into surname."""
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value={"surname": "SAMRIDDHI"},
    ):
        result = extract_passport_fields(GIVEN_ONLY_OCR)
    assert result.get("given_names") == "SAMRIDDHI"
    assert not result.get("surname")


def test_surname_only_keeps_given_name_blank():
    """Given Name label empty + MRZ empty given → do not copy surname into given."""
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value={"given_names": "ANNADURAI"},
    ):
        result = extract_passport_fields(SURNAME_ONLY_OCR)
    assert result.get("surname") == "ANNADURAI"
    assert not result.get("given_names")


def test_post_validate_rejects_surname_copied_from_given():
    out = _post_validate_passport_fields(
        {
            "surname": "SAMRIDDHI",
            "given_names": "SAMRIDDHI",
            "mrz_string": (
                "P<IND<<SAMRIDDHI<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
                "S1234567<8IND0001014F3001011<<<<<<<<<<<<<<<0"
            ),
        },
        labeled={"given_names": "SAMRIDDHI"},
    )
    assert out.get("given_names") == "SAMRIDDHI"
    assert not out.get("surname")


def test_post_validate_rejects_given_copied_from_surname():
    out = _post_validate_passport_fields(
        {
            "surname": "ANNADURAI",
            "given_names": "ANNADURAI",
            "mrz_string": (
                "P<INDANNADURAI<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
                "U9663905<8IND8508155M3103142<<<<<<<<<<<<<<<"
            ),
        },
        labeled={"surname": "ANNADURAI"},
    )
    assert out.get("surname") == "ANNADURAI"
    assert not out.get("given_names")


def test_post_validate_keeps_matching_names_when_both_independently_in_mrz():
    out = _post_validate_passport_fields(
        {
            "surname": "SMITH",
            "given_names": "SMITH",
            "mrz_string": (
                "P<INDSMITH<<SMITH<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
                "U9663905<8IND8508155M3103142<<<<<<<<<<<<<<<"
            ),
        },
        labeled={},
    )
    assert out.get("surname") == "SMITH"
    assert out.get("given_names") == "SMITH"


# --- Family fields must not copy holder given/surname (Dona Joice shape) ---

DONA_JOICE_FATHER_CROSSFILL_OCR = """
REPUBLIC OF INDIA
Surname
ADAIKALA JAYARAJ
Given Name(s)
DONA JOICE
Nationality / Sex / Date of Birth
INDIAN F 10/06/1990
Place of Birth
TRICHY,TAMIL NADU
P<INDADAIKALA<JAYARAJ<<DONA<JOICE<<<<<<<<<<<
Z3181865<8IND9006104F2505211<<<<<<<<<<<<<<<4
OBSERVATION
MISCELLANEOUS SERVICE
Nere of Pathvet / Legas Gusrdian
Z3181865
ADAIKALA JAYARAJ
Name of Mother
JOSEPHINE ANUNCIA
Address
4,MAIN ROAD,GABRIELPURAM
"""

# Page-0 biodata given name + page-1 mother label only (father label OCR unrecognised).
# Left/right fallback previously invented father=DONA JOICE from page 0.
DONA_JOICE_OCR_BLOCKS = [
    {
        "page_index": 0,
        "reading_order_index": 0,
        "text": "Surame",
        "bounding_box": [[1000.0, 1740.0], [1280.0, 1740.0], [1280.0, 1780.0], [1000.0, 1780.0]],
    },
    {
        "page_index": 0,
        "reading_order_index": 1,
        "text": "ADAIKALA JAYARAJ",
        "bounding_box": [[998.0, 1773.0], [1528.0, 1779.0], [1527.0, 1836.0], [997.0, 1830.0]],
    },
    {
        "page_index": 0,
        "reading_order_index": 2,
        "text": "e / Ghven Nama(a)",
        "bounding_box": [[1000.0, 1837.0], [1469.0, 1849.0], [1468.0, 1905.0], [999.0, 1893.0]],
    },
    {
        "page_index": 0,
        "reading_order_index": 3,
        "text": "DONA JOICE",
        "bounding_box": [[997.0, 1899.0], [1335.0, 1903.0], [1334.0, 1961.0], [996.0, 1957.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 0,
        "text": "anfyeow / Nere of Pathvet / Legas Gusrdian",
        "bounding_box": [[544.0, 1742.0], [1370.0, 1731.0], [1370.0, 1775.0], [545.0, 1785.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 1,
        "text": "Z3181865",
        "bounding_box": [[1688.0, 1776.0], [1909.0, 1772.0], [1910.0, 1827.0], [1689.0, 1830.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 2,
        "text": "ADAIKALA JAYARAJ",
        "bounding_box": [[326.0, 1815.0], [873.0, 1809.0], [873.0, 1869.0], [326.0, 1875.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 3,
        "text": "Name of Mother",
        "bounding_box": [[326.0, 1880.0], [873.0, 1875.0], [873.0, 1925.0], [326.0, 1930.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 4,
        "text": "JOSEPHINE",
        "bounding_box": [[326.0, 1935.0], [600.0, 1930.0], [600.0, 1985.0], [326.0, 1990.0]],
    },
    {
        "page_index": 1,
        "reading_order_index": 5,
        "text": "ANUNCIA",
        "bounding_box": [[610.0, 1935.0], [900.0, 1930.0], [900.0, 1985.0], [610.0, 1990.0]],
    },
]


def test_father_not_copied_from_holder_given_when_father_label_garbled():
    """Dona Joice: garbled Father label must not invent father from given name."""
    result = _extract(DONA_JOICE_FATHER_CROSSFILL_OCR, blocks=DONA_JOICE_OCR_BLOCKS)
    assert result.get("given_names") == "DONA JOICE"
    assert result.get("surname") == "ADAIKALA JAYARAJ"
    assert result.get("father_name") != "DONA JOICE"
    assert result.get("mother_name") == "JOSEPHINE ANUNCIA"


def test_dona_joice_garbled_father_label_reads_name_beside_label():
    """Garbled Father/Legal Guardian OCR still yields the name next to that label."""
    result = _extract(DONA_JOICE_FATHER_CROSSFILL_OCR, blocks=DONA_JOICE_OCR_BLOCKS)
    assert result.get("given_names") == "DONA JOICE"
    assert result.get("father_name") == "ADAIKALA JAYARAJ"
    assert result.get("father_name") != "DONA JOICE"
    assert result.get("mother_name") == "JOSEPHINE ANUNCIA"


def test_koushik_junk_place_of_birth_stored_blank():
    """Structural OCR junk (symbols/braces) must blank place of birth."""
    junk = r"fi*t{qf wqlq\FnN'ttc{$"
    assert _is_ocr_junk_text_value(junk)
    assert not _is_ocr_junk_text_value("ERODE,TAMIL NADU")
    assert not _is_ocr_junk_text_value("VISAKHAPATNAM")
    out = _post_validate_passport_fields({"place_of_birth": junk})
    assert not out.get("place_of_birth")
    text = (
        "REPUBLIC OF INDIA\n"
        "Surname\nKOUSHIK\n"
        "Given Name(s)\nTEST\n"
        "Place of Birth\n"
        f"{junk}\n"
        "Place of Issue\nHYDERABAD\n"
    )
    result = _extract(text)
    assert not result.get("place_of_birth")


def test_post_validate_rejects_father_equal_to_given_without_father_label():
    out = _post_validate_passport_fields(
        {
            "surname": "ADAIKALA JAYARAJ",
            "given_names": "DONA JOICE",
            "father_name": "DONA JOICE",
            "mother_name": "JOSEPHINE ANUNCIA",
        },
        text=(
            "Surname\nADAIKALA JAYARAJ\n"
            "Given Name(s)\nDONA JOICE\n"
            "Name of Mother\nJOSEPHINE ANUNCIA\n"
        ),
        ocr_blocks=[
            {
                "page_index": 0,
                "reading_order_index": 0,
                "text": "DONA JOICE",
                "bounding_box": [
                    [997.0, 1899.0],
                    [1335.0, 1903.0],
                    [1334.0, 1961.0],
                    [996.0, 1957.0],
                ],
            },
            {
                "page_index": 1,
                "reading_order_index": 0,
                "text": "Name of Mother",
                "bounding_box": [
                    [326.0, 1880.0],
                    [873.0, 1875.0],
                    [873.0, 1925.0],
                    [326.0, 1930.0],
                ],
            },
            {
                "page_index": 1,
                "reading_order_index": 1,
                "text": "JOSEPHINE ANUNCIA",
                "bounding_box": [
                    [326.0, 1935.0],
                    [900.0, 1930.0],
                    [900.0, 1985.0],
                    [326.0, 1990.0],
                ],
            },
        ],
        labeled={"father_name": "DONA JOICE", "given_names": "DONA JOICE"},
    )
    assert out.get("given_names") == "DONA JOICE"
    assert not out.get("father_name")
    assert out.get("mother_name") == "JOSEPHINE ANUNCIA"


def test_post_validate_keeps_father_equal_surname_when_father_label_reads_it():
    """Shared family token / full surname as father is OK when Father label yields it."""
    text = (
        "Surname\nADAIKALA JAYARAJ\n"
        "Given Name(s)\nDONA JOICE\n"
        "Name of Father / Legal Guardian\nADAIKALA JAYARAJ\n"
        "Name of Mother\nJOSEPHINE ANUNCIA\n"
    )
    out = _post_validate_passport_fields(
        {
            "surname": "ADAIKALA JAYARAJ",
            "given_names": "DONA JOICE",
            "father_name": "ADAIKALA JAYARAJ",
        },
        text=text,
        labeled={},
    )
    assert out.get("father_name") == "ADAIKALA JAYARAJ"
    assert out.get("given_names") == "DONA JOICE"


def test_post_validate_keeps_father_sharing_token_but_not_exact_given():
    out = _post_validate_passport_fields(
        {
            "surname": "ADAIKALA JAYARAJ",
            "given_names": "DONA JOICE",
            "father_name": "JOICE ADAIKALA",
        },
        text=(
            "Given Name(s)\nDONA JOICE\n"
            "Name of Father / Legal Guardian\nJOICE ADAIKALA\n"
        ),
        labeled={},
    )
    assert out.get("father_name") == "JOICE ADAIKALA"


def test_file_number_not_copied_from_passport_number():
    """Existing gate: passport number must not become file_number."""
    text = (
        "REPUBLIC OF INDIA\n"
        "Surname\nANNADURAI\n"
        "Given Name(s)\nARAVIND BHARATHI\n"
        "Passport No.\nU9663905\n"
        "File No.\nU9663905\n"
        "P<INDANNADURAI<<ARAVIND<BHARATHI<<<<<<<<<<<<\n"
        "U9663905<8IND8508155M3103142<<<<<<<<<<<<<<<\n"
    )
    result = _extract(text)
    assert result.get("document_number") == "U9663905"
    assert result.get("file_number") != "U9663905"


def test_td3_line2_starting_with_p_kept_with_line1():
    """Doc numbers starting with P are TD3 line 2 by shape, not dropped as line 1."""
    from app.services.scanx_passport import (
        _looks_like_td3_line1,
        _looks_like_td3_line2,
        extract_mrz_lines,
        parse_td3_mrz,
    )

    line1 = "P<IND<<SREEJA<SIVADAS<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "P7396691<2IND9411243F2701220<<<<<<<<<<<<<<<8"
    assert _looks_like_td3_line1(line1)
    assert not _looks_like_td3_line2(line1)
    assert _looks_like_td3_line2(line2)
    assert not _looks_like_td3_line1(line2)

    text = (
        "REPUBLIC OF INDIA\n"
        f"{line1}\n"
        f"{line2}\n"
    )
    lines = extract_mrz_lines(text)
    assert any(_looks_like_td3_line1(ln) for ln in lines)
    assert any(_looks_like_td3_line2(ln) for ln in lines)

    mrz = parse_td3_mrz(lines)
    assert "\n" in str(mrz.get("mrz_string") or "")
    assert mrz.get("document_number") == "P7396691"
    assert mrz.get("date_of_birth")
    assert mrz.get("date_of_expiry")
    assert mrz.get("sex") == "F"

    result = _extract(text)
    assert result.get("document_number") == "P7396691"
    assert result.get("date_of_birth")
    assert result.get("date_of_expiry")
    ms = str(result.get("mrz_string") or "")
    assert "P<IND" in ms
    assert "P7396691" in ms
    assert "\n" in ms


def test_td3_line1_p_angle_bracket_still_line1():
    """Regression: classic P<… name lines remain line 1, not line 2."""
    from app.services.scanx_passport import (
        _looks_like_td3_line1,
        _looks_like_td3_line2,
        extract_mrz_lines,
        parse_td3_mrz,
    )

    line1 = "P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "S7766566<8IND9912164M2811213<<<<<<<<<<<<<<<8"
    assert _looks_like_td3_line1(line1)
    assert not _looks_like_td3_line2(line1)
    lines = extract_mrz_lines(f"{line1}\n{line2}")
    mrz = parse_td3_mrz(lines)
    assert mrz.get("surname") == "REGURI"
    assert mrz.get("given_names") == "ANIRUDH"
    assert mrz.get("document_number") == "S7766566"
    assert mrz.get("document_type") == "P"


def test_empty_ocr_does_not_invent_document_type_p():
    """Timeout / empty extract must not look like a passport was read."""
    result = _extract("")
    assert result.get("document_type") in (None, "")
    assert result.get("document_number") in (None, "")
    assert result.get("surname") in (None, "")
    assert result.get("mrz_string") in (None, "")


# --- Audited OCR shapes (structural; not filename-keyed) ---

LAST_PAGE_FATHER_BEFORE_LABEL_OCR = """
VISA
BHUPAL SINGH MANRAL Re/t 3ra /Name of Father/Legal Guardian 26356517
KAMLA MANRAL
aods po aw/ geh h
ga/ Address
61933,ANAND BAGH
HALDWANI,NAINITAL
PIN:263139,UTTARAKHAND,INDIA
J8599525 Old Passpo No.wit Dat and uce of u 20/10/2011
Fie No. DEHRADUN
DLA075091045220

BHUPAL SINGH MANRAL Ra/t 3ra /Name of Father/Legal Guardion 26356517
Name of Mother
KAMLA MANRAL
Address
61933,ANAND BAGH
HALDWANI,NAINITAL
PIN:263139,UTTARAKHAND,INDIA
J8599525 Old Passport No with Date and Pace of isue 20/10/2011
Fle No. DEHRADUN
DLA075091045220
"""

GARBLED_FATHER_MOTHER_ADDRESS_OCR = """
H TURIGU REPUBLIC OF INDIA
Surame IND Z3181865
ADAIKALA JAYARAJ
DONA JOICE
Nationalty for / Sex Lste ot Bi
INDIAN F 10/06/1990
Place of Bre
TRICHY,TAMIL NADU
TRICHY
Date af etie mus iia / Date at Capiry
22/05/2015 21/05/2025
P<INDADAIKALA<JAYARAJ<<DONA<JOICE<<<<<<<<<<<

SOBSSRVATION
m anfyeow / Nere of Pathvet / Legas Gusrdian
Z3181865
ADAIKALA JAYARAJ
Name of Mother
JOSEPHINE ANUNCIA
qm / Addiese
4,MAIN ROAD,GABRIELPURAM,VALADY (PO)
LALGUDI TALUK,TRICHY RURAL
PIN:621218,TAMIL NADU,INDIA
TR2068479308915
"""

SYMBOL_SOUP_PASSPORT_OCR = """
e . $ P lm e frlc IN o D ae q tl R *m * r 4 /r r r N t*o D m rA m N y U q 2 rgq . tC f q 9 . I p 7 ass g por 2 t No O .
SFF?/S'urnsne
IEDI
fi*t{qf wqlq\\FnN'ttc{$
t{M-*S(
wR&roa*grtr
$*ref r1*x
rF{ RfFf/Phi*of8tslh
iftil/ Adrhess
t 6 -,6..rl*d i t}*t *I $*l} f, A *6ftt *****'$*$"* $ tr **G*-n
YJ6S626t{56t{11 19
"""

EMPTY_SURNAME_MRZ_COMBO_OCR = """
HRTURIG REPUBLIC OF INDIA
Type Country Code qqié / Passport No.
a/Surname
SREEJA SIVADAS
H/INDIAN F 24/11/1994
Place of Birth
MUMBAI,MAHARASHTRA
Place of Issue
MUMBAI
23/01/2017 22/01/2027
P<IND<<SREEJA<SIVADAS<<<<<<<<<<<<<<<<<<<<<<<

Name of Father/ Legal Guardian
SIVADASAN KALATHIL P7396691
Name of Mother
SUBHASHINI DAS
ame of Spouse
qa /Address
D 8O5 NAVJYOTIRLINGSOCIETY,OFF FILM CITY ROAD
INSIDE RIDDHI GARDENS MALAD EAST,MUMBAI
PIN:400097,MAHARASHTRA,INDIA
Si$a 4./ File No.
B01060579482617
"""


def test_last_page_father_name_before_label_not_into_given():
    """Name left of Father label is father; do not invent given/surname/DOB."""
    bad_llm = {
        "surname": "MANRAL",
        "given_names": "BHUPAL SINGH",
        "father_name": "KAMLA MANRAL",
        "sex": "M",
        "date_of_birth": "20-10-2011",
        "place_of_birth": "HALDWANI,NAINITAL",
        "place_of_issue": "DEHRADUN",
        "nationality": "INDIAN",
        "document_type": "P",
        "country_code": "IND",
    }
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value=bad_llm,
    ):
        result = extract_passport_fields(LAST_PAGE_FATHER_BEFORE_LABEL_OCR)
    assert result.get("father_name") == "BHUPAL SINGH MANRAL"
    assert result.get("mother_name") == "KAMLA MANRAL"
    assert not result.get("given_names")
    assert not result.get("surname")
    assert not result.get("date_of_birth")
    assert not result.get("place_of_birth")
    assert result.get("document_number") is None


def test_garbled_father_label_and_addiese_keeps_mother():
    """Garbled Father label + Addiese address still yield father/mother/dates."""
    result = _extract(GARBLED_FATHER_MOTHER_ADDRESS_OCR)
    assert result.get("surname") == "ADAIKALA JAYARAJ"
    assert result.get("given_names") == "DONA JOICE"
    assert result.get("father_name") == "ADAIKALA JAYARAJ"
    assert result.get("mother_name") == "JOSEPHINE ANUNCIA"
    assert result.get("sex") == "F"
    assert result.get("date_of_birth") is None
    assert result.get("date_of_issue") == "22-05-2015"
    assert result.get("date_of_expiry") is None
    assert result.get("place_of_issue") is None
    assert "GABRIELPURAM" in str(result.get("address") or "")


def test_symbol_soup_ocr_stays_blank_even_with_llm_junk():
    """Symbol-soup OCR must not invent document_type P or junk MRZ."""
    bad_llm = {
        "nationality": "INDIAN",
        "document_type": "P",
        "country_code": "IND",
        "mrz_string": "wR&roa*grtr$*ref r1*x",
        "date_of_birth": "20-10-2011",
        "surname": "KOUSHIK",
    }
    with patch(
        "app.services.scanx_llm_passport.refine_passport_fields_via_llm",
        return_value=bad_llm,
    ):
        result = extract_passport_fields(SYMBOL_SOUP_PASSPORT_OCR)
    assert not result.get("document_type")
    assert not result.get("mrz_string")
    assert not result.get("surname")
    assert not result.get("date_of_birth")
    assert not result.get("date_of_issue")
    assert not result.get("nationality")
    assert native_pdf_text_needs_ocr(SYMBOL_SOUP_PASSPORT_OCR)


def test_garbled_place_of_issue_and_short_surname_and_father_crumb():
    """Pace ofsue, four-letter surname, and Rre/ before the father label."""
    text = """
34T/Surname
MUDI
KOWSHIK
Place of Birth
KAVALI,ANDHRA PRADESH
Pace ofsue
VIJAYAWADA
BHUPALSINGH MANRAL Rre/ ft 3ras t/Name of Father/Legal Guardion
KAMLA MANRAL
Name of Mother
"""
    result = _extract(text)
    assert result.get("surname") == "MUDI"
    assert result.get("place_of_issue") == "VIJAYAWADA"
    assert result.get("father_name") == "BHUPALSINGH MANRAL"


def test_pace_of_birth_tssue_mother_spouse_crumb_and_door_slash():
    """Pace of Birth, Place of tssue, spouse-label crumb, and 6/933 door."""
    text = """
we pang/tupt /Sex
30/06/1995 M
Pace of Birth
HALDWANI,UTTARAKHAND
Place of tssue
DELHI
Name of Mother
KAMLA MANRAL
ame of Spove
Address
61933,ANAND BAGH
HALDWANI,NAINITAL
PIN:263139,UTTARAKHAND,INDIA
"""
    result = _extract(text)
    assert result.get("place_of_birth") == "HALDWANI, UTTARAKHAND"
    assert result.get("place_of_issue") == "DELHI"
    assert result.get("mother_name") == "KAMLA MANRAL"
    assert result.get("sex") == "M"
    assert result.get("date_of_birth") is None
    assert str(result.get("address") or "").startswith("61933")


def test_attach_keeps_father_equal_surname_with_label_text():
    """attach_passport_to_fields must not wipe father==surname when OCR supports it."""
    passport = {
        "surname": "ADAIKALA JAYARAJ",
        "given_names": "DONA JOICE",
        "father_name": "ADAIKALA JAYARAJ",
        "mother_name": "JOSEPHINE ANUNCIA",
        "document_type": "P",
    }
    text = (
        "Surname\nADAIKALA JAYARAJ\n"
        "Given Name(s)\nDONA JOICE\n"
        "Name of Father / Legal Guardian\nADAIKALA JAYARAJ\n"
        "Name of Mother\nJOSEPHINE ANUNCIA\n"
    )
    out = attach_passport_to_fields({"version": 1}, passport, text=text)
    assert out["passport"].get("father_name") == "ADAIKALA JAYARAJ"
    assert out["passport"].get("given_names") == "DONA JOICE"


def test_empty_mrz_surname_combo_line_fills_sex_dob():
    """Empty MRZ family name stays blank. Sex, DOB, and number need a valid line 2."""
    result = _extract(EMPTY_SURNAME_MRZ_COMBO_OCR)
    assert result.get("given_names") == "SREEJA SIVADAS"
    assert not result.get("surname")
    assert result.get("father_name") == "SIVADASAN KALATHIL"
    assert result.get("mother_name") == "SUBHASHINI DAS"
    assert result.get("sex") is None
    assert result.get("date_of_birth") is None
    assert result.get("document_number") is None
    assert not result.get("spouse_name")


def test_glued_city_state_garbled_places_and_address_prefix():
    """City+state glue, garbled labels, and a real door slash stay intact."""
    s_passport = (
        "Place of Birth\nMUMBAIMAHARASHTRA\nPlace of Issue\nMUMBAI\n"
    )
    dona = (
        "enr/ Place of 6\nTRICHY, TAMIL NADU\n"
        "An/ uardian\nZ3181865\nADAIKALA JAYARAJ\n"
        "Name ot Mother\nJOSEPHINE ANUNCIA\nNama Spouse\n"
        "qm / Addrese\n148/4,MAIN ROAD,GABRIELPURAM\n"
        "A. Q TRICHY mr thfa / Date of Eapiry\n"
    )
    anirudh = "Place ot.lssue\nR.L. HYDERABAD sa dal Dnte of iaptry\n"
    aravind = (
        "Date of issue CHENNAI an8 t 87 em/ Piace of ssue "
        "ERODE,TAMIL NADU Place of Birth\n"
        "BLOCK 3/C1,JAINS GREEN ACRES,91,DARGA ROAD 22/12/2011\n"
        "ZAMEEN PALLAVARAM,CHENNAI\n"
    )
    vishu = "om o mq. Name of Mathe\nLAKSHNI KANTHAMMA MARTHALA\n"
    assert _extract(s_passport).get("place_of_birth") == "MUMBAI, MAHARASHTRA"
    dona_out = _extract(dona)
    assert dona_out.get("place_of_birth") == "TRICHY, TAMIL NADU"
    assert dona_out.get("father_name") == "ADAIKALA JAYARAJ"
    assert dona_out.get("place_of_issue") is None
    assert dona_out.get("mother_name") == "JOSEPHINE ANUNCIA"
    assert str(dona_out.get("address") or "").startswith("148/4")
    assert _extract(anirudh).get("place_of_issue") == "HYDERABAD"
    aravind_out = _extract(aravind)
    assert aravind_out.get("place_of_birth") == "ERODE, TAMIL NADU"
    assert aravind_out.get("place_of_issue") == "CHENNAI"
    assert "22/12/2011" not in str(aravind_out.get("address") or "")
    assert _extract(vishu).get("mother_name") == "LAKSHNI KANTHAMMA MARTHALA"


def test_paired_dates_on_one_line_fill_issue_and_expiry():
    """Issue and expiry share one OCR row even when the expiry word is garbled."""
    dona = "Date af issse mus a sifa / Dete of Cepiry\n22/05/2015 21/05/2025\n"
    anirudh = "Date of lssue\n22/11/2018 21/11/2028\n"
    vishu = "Pafe/Date of issue\n26/12/2019 25/12/2029\n"
    aravind = "15/03/2021 ant a at ra/ Date of issue CHENNAI\n"
    assert _extract(dona).get("date_of_issue") == "22-05-2015"
    assert _extract(dona).get("date_of_expiry") == "21-05-2025"
    assert _extract(anirudh).get("date_of_issue") == "22-11-2018"
    assert _extract(anirudh).get("date_of_expiry") is None
    assert _extract(vishu).get("date_of_issue") == "26-12-2019"
    assert _extract(vishu).get("date_of_expiry") is None
    assert _extract(aravind).get("date_of_issue") == "15-03-2021"


REPEATED_STAMP_LOCALITY_OCR = """
S1972613
OTA Z Advocpte & Netary B. BHAVANY RY BALLM
Waraban Girmagipet, T.S. INDIA
NOTARY Advecate & ALLMY B. BHAVANY BALLM
Warargat Urban Gragmagipet, 1 S.UA 1
Warar gal Urban Girmegipet, T.S.INDIA
Advocate & Notary Girmagipet, Warangal Urban T.S. INDIA
Girmagipet, Warangal Urban Telangana State-INDIA
Warangal Urban Girmagipet, T.S. INDIA 2
Girmagipel, Warargal Urban
Warar gat Urban 1 S. INDIA
"""


def test_repeated_stamp_locality_keeps_one_line_and_passport_number():
    """Notary stamps are comments. Keep the passport number; do not store the stamp town."""
    result = _extract(REPEATED_STAMP_LOCALITY_OCR)
    assert result.get("document_number") is None
    assert not result.get("address")
    assert "Girmagipet" not in str(result.get("address") or "")
    assert not result.get("surname")
    assert not result.get("given_names")
    assert not result.get("spouse_name")
    assert not result.get("father_name")
    assert not result.get("mother_name")
    assert not result.get("date_of_birth")
    assert not result.get("date_of_issue")
    assert not result.get("date_of_expiry")
    assert not result.get("mrz_string")
    mashed = (
        "Warangal Urban Girmagipet, T.S. INDIA 2, Warar gat Urban 1 S. INDIA, "
        "Girmagipel, Warargal Urban, Waranga: Urban Girmagipet, BALLM, "
        "Girmagipet, Warangal Urban, T.S. INDIA"
    )
    assert not _tidy_passport_address(mashed)
    stripped = strip_non_passport_comments(REPEATED_STAMP_LOCALITY_OCR)
    assert "S1972613" in stripped
    assert "NOTARY" not in stripped.upper()
    assert "Girmagipet" not in stripped
    # A stamp town plus a passport number is not enough to call the page a passport
    # when no biodata labels or MRZ remain. Filename is not the rule.
    assert not text_has_enough_passport_evidence(REPEATED_STAMP_LOCALITY_OCR)
    assert not document_looks_like_passport(
        document_type_id="UNKNOWN",
        original_filename="notes.pdf",
        extracted_text=REPEATED_STAMP_LOCALITY_OCR,
    )
    assert (
        classify_document_type(
            REPEATED_STAMP_LOCALITY_OCR,
            filename="notes.pdf",
        ).document_type_id
        != "PASSPORT"
    )


NOTARY_STAMPED_PASSPORT_OCR = """
REPUBLIC OF INDIA
PASSPORT
Surname
KULKARNI
Given Names
ANIL KUMAR
Nationality INDIAN
Date of Birth
04/08/1992
Passport No.
Z1234567
Place of Birth
HYDERABAD, TELANGANA
Address
12 LAKE VIEW ROAD
PIN:500001, TELANGANA, INDIA
NOTARY Advocate B.A.LL.M TRUE COPY
Certified copy verified
STAMP DUTY
ATTESTED Attorney
Girmagipet, Warangal Urban Telangana State-INDIA
Advocate & Notary Girmagipet, Warangal Urban T.S. INDIA
Warangal Urban Girmagipet, T.S. INDIA
"""


def test_notary_comments_do_not_block_passport_scan_or_fill_fields():
    """A stamped passport is still a passport. Stamp text is not surname, date, or address."""
    result = _extract(NOTARY_STAMPED_PASSPORT_OCR)
    assert result.get("surname") == "KULKARNI"
    assert result.get("given_names") == "ANIL KUMAR"
    assert result.get("document_number") == "Z1234567"
    assert result.get("date_of_birth") == "04-08-1992"
    assert result.get("place_of_birth") == "HYDERABAD, TELANGANA"
    assert result.get("nationality") == "INDIAN"
    address = result.get("address") or ""
    assert "LAKE VIEW" in address
    assert "Girmagipet" not in address
    assert "NOTARY" not in address.upper()
    assert not result.get("spouse_name")
    assert text_has_enough_passport_evidence(NOTARY_STAMPED_PASSPORT_OCR)
    assert document_looks_like_passport(
        document_type_id="UNKNOWN",
        original_filename="notes.pdf",
        extracted_text=NOTARY_STAMPED_PASSPORT_OCR,
    )
    classified = classify_document_type(
        NOTARY_STAMPED_PASSPORT_OCR,
        filename="notes.pdf",
    )
    assert classified.document_type_id == "PASSPORT"


BLANK_SPOUSE_SCHOOL_ADDRESS_OCR = """
a/Surns.me
CHILUKURI
PARASHAR
Nationality f / Sex Grinao ate of Birth
H/INDIAN M 31/10/1996
Place of Birth
KODAD, TELANGANA
Place of Issue
7 BENGALURU
Date of Issue ifta fafa/ Date of Expiry
23/11/2017 22/11/2027
P<INDCHILUKURI<<PARASHAR<<<<<<<<<<<<<<<<<<<<
R6974694<81ND9610312M2711221<<<<<<<<<<<<<<<6
arm /Name of Father /Legal Guardian
LAXMINARAYANA PRASAD CHILUKURI R6974694
Name of Mother
VARALAKSHMI CHILUKURI
Name of Spouse
qa / Address
E-2O2 AMRITA SCHOOL OF ENGINEERING
MATHURA BLK,KASAVANAHALLI,BENGALURU
PIN:560035,KARNATAKA,INDIA
da =./ File No.
BN2060700767317
"""


def test_blank_spouse_label_does_not_take_school_address():
    """Spouse cell is empty; the next lines are the address, not a person."""
    assert not _is_plausible_person_name("qa E-2O2 AMRITA SCHOOL OF ENGINEERING")
    result = _extract(BLANK_SPOUSE_SCHOOL_ADDRESS_OCR)
    assert result.get("spouse_name") is None
    assert result.get("surname") == "CHILUKURI"
    assert result.get("given_names") == "PARASHAR"
    assert result.get("father_name") == "LAXMINARAYANA PRASAD CHILUKURI"
    assert result.get("mother_name") == "VARALAKSHMI CHILUKURI"
    assert result.get("sex") == "M"
    assert result.get("date_of_birth") == "31-10-1996"
    assert result.get("place_of_birth") == "KODAD, TELANGANA"
    assert result.get("place_of_issue") == "BENGALURU"
    assert result.get("date_of_issue") == "23-11-2017"
    assert result.get("date_of_expiry") == "22-11-2027"
    assert result.get("document_number") == "R6974694"
    assert result.get("file_number") == "BN2060700767317"
    assert result.get("nationality") == "INDIAN"
    address = result.get("address") or ""
    assert address == (
        "E-2O2 AMRITA SCHOOL OF ENGINEERING, MATHURA BLK, KASAVANAHALLI, "
        "BENGALURU, PIN:560035, KARNATAKA, INDIA"
    )
    assert "AMRITA SCHOOL OF ENGINEERING" not in str(result.get("spouse_name") or "")


def _centered_box(cx: float, cy: float, w: float, h: float):
    return _box(cx - w / 2.0, cy - h / 2.0, w, h)


def _ocr_blk(page: int, order: int, text: str, cx: float, cy: float, w: float, h: float):
    return {
        "page_index": page,
        "reading_order_index": order,
        "text": text,
        "cleaned_text": text,
        "bounding_box": _centered_box(cx, cy, w, h),
    }


# Snippets from a re-scan whose OCR garbles Place of Birth / Place of Issue,
# leaves the spouse cell empty, and stores the street line only in boxes.
# The notary town is repeated as a stamp, not as the residential address.
GARBLED_BIRTH_ISSUE_AND_STAMP_OCR = """
REPUBLIC OF INDIA
PASSPORT
03/07/2018 HYDERABAD on PARKAL, TELANGANA e/ Puce ot Burth HRAINDIAN
w we ant Rrfa / Date of Issue
Pteca oftssué
Advocate & Notary BALLM
B. BHAVANY Advocate & Notary Girmagipet, Warangal Urban T.S. INDIA
Girmagipet, Warangal Urban Telangana State-INDIA
Warangal Urban Girmagipet, T.S. INDIA
NOTATAL B Bhaoay Girmagipet, Waranga B. BHAVANY Advocate & Nota ATTESTCO
"""


def _rotated_family_and_place_blocks():
    """Boxes copied from the rotated scan: street centers sit above Address."""
    return [
        _ocr_blk(0, 0, "e/ Puce ot Burth", 453.0, 699.0, 24.0, 188.0),
        _ocr_blk(0, 1, "PARKAL, TELANGANA", 422.5, 729.8, 33.0, 266.0),
        _ocr_blk(0, 2, "HYDERABAD", 363.5, 756.0, 29.0, 142.0),
        _ocr_blk(0, 3, "w we ant Rrfa / Date of Issue", 334.5, 812.0, 25.0, 246.0),
        _ocr_blk(0, 4, "Pteca oftssué", 393.5, 886.0, 19.0, 112.0),
        _ocr_blk(1, 0, "BANDI SADANANDAM GOUD", 900.0, 700.0, 40.0, 280.0),
        _ocr_blk(1, 1, "mo 0 suen / e", 860.0, 710.0, 30.0, 80.0),
        _ocr_blk(1, 2, "BANDI RANI", 900.0, 780.0, 40.0, 180.0),
        _ocr_blk(1, 3, "esnads s/ bl b u", 860.0, 800.0, 30.0, 90.0),
        _ocr_blk(1, 4, "Address", 1058.5, 1108.0, 25.0, 110.0),
        _ocr_blk(1, 5, "HOUSE NUMBER 19-87 PITTAWADA", 1093.5, 954.0, 43.0, 432.0),
        _ocr_blk(1, 6, "VILLAGE AND MANDAL PARKAL,WARANGAL RURAL", 1149.5, 862.5, 55.0, 617.0),
        _ocr_blk(1, 7, "PIN:506164,TELANGANA,INDIA", 1212.5, 965.2, 51.0, 411.0),
        _ocr_blk(1, 8, "B Bhaoay", 1109.5, 1524.0, 355.0, 184.0),
        _ocr_blk(1, 9, "B. BHAVANY", 1108.0, 1589.0, 250.0, 56.0),
        _ocr_blk(1, 10, "Advocate & Nota", 1000.0, 1600.0, 200.0, 40.0),
        _ocr_blk(1, 11, "Girmagipet, Waranga", 1077.0, 1682.0, 272.0, 48.0),
    ]


def test_garbled_place_labels_keep_street_and_drop_stamp_spouse():
    """Birth/issue come from their labels. Stamp text is not spouse or address."""
    result = _extract(
        GARBLED_BIRTH_ISSUE_AND_STAMP_OCR,
        _rotated_family_and_place_blocks(),
    )
    assert result.get("place_of_birth") == "PARKAL, TELANGANA"
    assert result.get("place_of_issue") == "HYDERABAD"
    assert not result.get("spouse_name")
    address = result.get("address") or ""
    assert address.upper().startswith("HOUSE NUMBER 19-87 PITTAWADA")
    assert "VILLAGE AND MANDAL PARKAL" in address.upper()
    assert "506164" in address
    assert "GIRMAGIPET" not in address.upper()
    assert "WARANGAL RURAL" in address.upper()
    parts = [part.strip().upper() for part in address.split(",")]
    assert "WARANGA" not in parts


# Visual zone reads 5 as 6 in two positions. The MRZ line and a repeated
# token contain the other reading. A 6 that no other token shows as 5 stays 6.
MRZ_SUPPORTED_PASSPORT_NUMBER_OCR = """
REPUBLIC OF INDIA
Type Country Code / Passport No.
Surname
SAMPLE
Given Name(s)
HOLDER NAME
Nationality Sex Date of Birth
INDIAN M 05/02/1998
Name of Father / Legal Guardian T6253261
FATHER PERSON
Name of Mother
MOTHER PERSON
File No.
VJ667766612345
PIN:521110
P<INDSAMPLE<<HOLDER<<<<<<<<<<<<<<<<<<<<<<<<<<
T5253251<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""


ONLY_VISUAL_PASSPORT_NUMBER_OCR = """
REPUBLIC OF INDIA
Type Country Code / Passport No.
Surname
SAMPLE
Given Name(s)
HOLDER NAME
Nationality Sex Date of Birth
INDIAN M 05/02/1998
Name of Father / Legal Guardian T6253261
FATHER PERSON
Name of Mother
MOTHER PERSON
File No.
VJ667766612345
PIN:521110
P<INDSAMPLE<<HOLDER<<<<<<<<<<<<<<<<<<<<<<<<<<
T6253261<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""


ONE_DIGIT_MRZ_PASSPORT_NUMBER_OCR = """
REPUBLIC OF INDIA
Surname
SAMPLE
Given Name(s)
HOLDER NAME
Name of Father / Legal Guardian T6253261
FATHER PERSON
File No.
VJ667766612345
P<INDSAMPLE<<HOLDER<<<<<<<<<<<<<<<<<<<<<<<<<<
T5253261<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""


def test_mrz_passport_number_wins_when_that_token_is_in_ocr():
    """Prefer the MRZ token over a visual 5→6 misread. Do not rewrite other 6s."""
    result = _extract(MRZ_SUPPORTED_PASSPORT_NUMBER_OCR)
    assert result.get("document_number") == "T5253251"
    assert result.get("file_number") != "T5253251"
    assert "666" in str(result.get("file_number") or "VJ667766612345")


def test_visual_passport_number_stays_when_ocr_never_has_the_other_token():
    """A lone visual reading is kept. 6 is not globally replaced with 5."""
    result = _extract(ONLY_VISUAL_PASSPORT_NUMBER_OCR)
    assert result.get("document_number") == "T6253261"
    assert "T5253251" not in str(result.get("document_number") or "")


def test_mrz_digit_is_taken_only_where_that_token_shows_it():
    """A line 2 that fails check digits does not supply a passport number."""
    result = _extract(ONE_DIGIT_MRZ_PASSPORT_NUMBER_OCR)
    assert result.get("document_number") is None
    assert result.get("date_of_birth") is None
    assert result.get("date_of_expiry") is None
    assert result.get("sex") is None
    assert result.get("nationality") is None


TRAILING_MOTHER_ON_FATHER_OCR = """
REPUBLIC OF INDIA
Surname
NIMMAGADDA
Given Name(s)
GIRIJA RANI
Legal Guardian
SRINIVASA RAO NIMMAGADDA R8531797
CHANDRAKALA NIMMAGADDA
Name of Spouse
qa / Address
154 SAMPLE LANE
"""


def test_trailing_mother_name_stripped_when_mother_label_is_separate():
    """Father keeps only the guardian value. Mother stays on her own label."""
    blocks = [
        _ocr_blk(1, 0, "Name of Father / Legal Guardian", 200, 100, 220, 18),
        _ocr_blk(1, 1, "SRINIVASA RAO NIMMAGADDA", 210, 140, 240, 18),
        _ocr_blk(1, 2, "/Name of Mother", 200, 200, 160, 18),
        _ocr_blk(1, 3, "CHANDRAKALA NIMMAGADDA", 210, 240, 220, 18),
    ]
    result = _extract(TRAILING_MOTHER_ON_FATHER_OCR, blocks)
    assert result.get("father_name") == "SRINIVASA RAO NIMMAGADDA"
    assert result.get("mother_name") == "CHANDRAKALA NIMMAGADDA"
    assert result.get("father_name") != result.get("mother_name")


def test_father_not_split_without_independent_mother_label():
    """A second name line stays on father when no mother label owns it."""
    text = """
REPUBLIC OF INDIA
Surname
NIMMAGADDA
Given Name(s)
GIRIJA RANI
Legal Guardian
SRINIVASA RAO NIMMAGADDA
CHANDRAKALA NIMMAGADDA
Name of Spouse
"""
    result = _extract(text)
    assert result.get("mother_name") in (None, "")
    assert "SRINIVASA RAO NIMMAGADDA" in str(result.get("father_name") or "")
    assert result.get("father_name") != "CHANDRAKALA NIMMAGADDA"


VERIFIED_MRZ_BEATS_VISUAL_OCR = """
REPUBLIC OF INDIA
Passport No.
T6253261
Nationality
INDIAN
Sex
F
Date of Birth
01/01/1980
Date of Expiry
01/01/2030
Date of Issue
02/02/2020
Place of Birth
HYDERABAD, TELANGANA
P<INDSAMPLE<<HOLDER<<<<<<<<<<<<<<<<<<<<<<<<<<
T5253251<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""


def test_verified_mrz_line2_discards_conflicting_visual_number():
    """Check-digit-valid line 2 wins. The printed top-half number is discarded."""
    result = _extract(VERIFIED_MRZ_BEATS_VISUAL_OCR)
    assert result.get("document_number") == "T5253251"
    assert result.get("date_of_birth") == "05-02-1998"
    assert result.get("date_of_expiry") == "12-05-2029"
    assert result.get("sex") == "M"
    assert result.get("nationality") == "INDIAN"
    assert result.get("date_of_issue") == "02-02-2020"
    assert result.get("place_of_birth") == "HYDERABAD, TELANGANA"


MISSING_MRZ_LINE2_OCR = """
REPUBLIC OF INDIA
Surname
SAMPLE
Given Name(s)
HOLDER NAME
Passport No.
T6253261
Nationality
INDIAN
Sex
M
Date of Birth
05/02/1998
Date of Expiry
12/05/2029
Date of Issue
02/02/2020
Place of Birth
HYDERABAD, TELANGANA
Place of Issue
HYDERABAD
"""


def test_missing_mrz_line2_uses_own_visual_labels():
    """No TD3 line 2: number, DOB, expiry, sex, and nationality come from labels."""
    result = _extract(MISSING_MRZ_LINE2_OCR)
    assert result.get("document_number") == "T6253261"
    assert result.get("date_of_birth") == "05-02-1998"
    assert result.get("date_of_expiry") == "12-05-2029"
    assert result.get("sex") == "M"
    assert result.get("nationality") == "INDIAN"
    assert result.get("surname") == "SAMPLE"
    assert "HOLDER" in str(result.get("given_names") or "")
    assert result.get("date_of_issue") == "02-02-2020"
    assert result.get("place_of_birth") == "HYDERABAD, TELANGANA"
    assert result.get("place_of_issue") == "HYDERABAD"


ADDRESS_BLOCK_WITH_NOTARY_TAIL_OCR = """
Name of Spouse

qa / Address
FIRST LINE HOUSE 12 MG ROAD
SECOND LINE ANNA NAGAR
PIN:600001, TAMIL NADU, INDIA
NOTARY Advocate ATTESTED TRUE COPY
Name of Father / Legal Guardian
RAVI KUMAR IYER
P<INDSAMPLE<<HOLDER<<<<<<<<<<<<<<<<<<<<<<<<<<
T5253251<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""


def test_address_block_keeps_line1_stops_before_mrz_and_drops_notary():
    result = _extract(ADDRESS_BLOCK_WITH_NOTARY_TAIL_OCR)
    address = str(result.get("address") or "")
    assert address.upper().startswith("FIRST LINE HOUSE 12 MG ROAD")
    assert "SECOND LINE ANNA NAGAR" in address.upper()
    assert "600001" in address
    assert "NOTARY" not in address.upper()
    assert "RAVI KUMAR" not in address.upper()
    assert "P<IND" not in address.upper()
    assert result.get("spouse_name") is None


BLANK_SPOUSE_NEXT_ROW_OCR = """
Name of Father / Legal Guardian
RAVI KUMAR IYER
Name of Mother
MEENA IYER
Name of Spouse

qa / Address
12 LAKE VIEW ROAD
PIN:500001, TELANGANA, INDIA
"""


def test_blank_spouse_stays_null_when_next_line_is_address_or_parent():
    result = _extract(BLANK_SPOUSE_NEXT_ROW_OCR)
    assert result.get("spouse_name") is None
    assert result.get("father_name") == "RAVI KUMAR IYER"
    assert result.get("mother_name") == "MEENA IYER"
    assert "LAKE VIEW" in str(result.get("address") or "").upper()
    parent_next = """
Name of Father / Legal Guardian
RAVI KUMAR IYER
Name of Spouse
RAVI KUMAR IYER
Name of Mother
MEENA IYER
"""
    parent_hit = _extract(parent_next)
    assert parent_hit.get("spouse_name") is None
    assert parent_hit.get("father_name") == "RAVI KUMAR IYER"
    mother_hit = _extract(
        "Name of Mother\nMEENA IYER\nName of Spouse\nMEENA IYER\n"
    )
    assert mother_hit.get("spouse_name") is None
    assert mother_hit.get("mother_name") == "MEENA IYER"


FUZZY_ISSUE_LABEL_OCR = """
Place of Birth
ERODE, TAMIL NADU
Piace of ssue
CHENNAI
Date of issse
15/03/2021
Advocate & Notary
GIRMAGIPET
"""


def test_fuzzy_place_and_date_of_issue_labels_use_grammar():
    result = _extract(FUZZY_ISSUE_LABEL_OCR)
    assert result.get("place_of_birth") == "ERODE, TAMIL NADU"
    assert result.get("place_of_issue") == "CHENNAI"
    assert result.get("date_of_issue") == "15-03-2021"
    assert "GIRMAGIPET" not in str(result.get("place_of_issue") or "")
    assert "GIRMAGIPET" not in str(result.get("place_of_birth") or "")
    unlabeled_city = _extract("Place of Birth\nMUMBAI, MAHARASHTRA\nGIRMAGIPET\n")
    assert unlabeled_city.get("place_of_issue") is None


def test_notary_lines_are_stripped_before_field_parse():
    text = """
Place of Issue
VISAKHAPATNAM
Address
12 LAKE VIEW ROAD
PIN:500001, ANDHRA PRADESH, INDIA
NOTARY Advocate GIRMAGIPET ATTESTED TRUE COPY
Girmagipet, Warangal Urban T.S. INDIA
Advocate & Notary Girmagipet
"""
    stripped = strip_non_passport_comments(text)
    assert "NOTARY" not in stripped.upper()
    assert "Girmagipet" not in stripped
    result = _extract(text)
    assert result.get("place_of_issue") == "VISAKHAPATNAM"
    address = str(result.get("address") or "")
    assert "LAKE VIEW" in address.upper()
    assert "GIRMAGIPET" not in address.upper()
    assert "NOTARY" not in address.upper()


def test_address_drops_label_prefix_and_keeps_clean_door_number():
    """Label crumbs before the street are not part of the address.

    ``e, Address,`` and a पता / Address header stay out. A door line that
    already starts at D.NO is unchanged, including Address in the middle.
    """
    prefixed = """
पता / Address
Name of Spouse
File No
e, Address, 12-1-47/1, SOMAJIGUDA, HYDERABAD
PIN:500082, TELANGANA, INDIA
"""
    prefixed_addr = str(_extract(prefixed).get("address") or "")
    assert prefixed_addr.startswith("12-1-47/1")
    assert "पता" not in prefixed_addr
    assert not prefixed_addr.lower().startswith("e")
    assert not prefixed_addr.upper().startswith("ADDRESS")

    clean = """
Address
D.NO:12-1-47/1, NEAR ADDRESS OFFICE, HYDERABAD
PIN:500082, TELANGANA, INDIA
"""
    clean_addr = str(_extract(clean).get("address") or "")
    assert clean_addr.startswith("D.NO:12-1-47/1")
    assert "ADDRESS OFFICE" in clean_addr.upper()
    assert "पता" not in clean_addr
    assert not clean_addr.upper().startswith("ADDRESS")


def test_address_header_and_barcode_noise_is_null():
    """Document headers and barcode dumps are not a street. The field is null.

    A normal PIN line may still end with INDIA. Label crumbs are stripped
    before that decision.
    """
    from app.services.scanx_passport import _address_is_administrative_noise

    assert _tidy_passport_address("REPUBLIC OF INDIA") is None
    assert _tidy_passport_address("e, Address, REPUBLIC OF INDIA") is None
    assert _tidy_passport_address("REPUBLlC 0F lNDIA") is None
    assert _tidy_passport_address("पति या पत्नी") is None
    assert _tidy_passport_address("पती या पत्नी") is None
    assert _tidy_passport_address("MISCELLANEOUS SERVICE") is None
    assert _tidy_passport_address("MISCELLANEOUS SERVlCE") is None
    assert _tidy_passport_address("MlSCELLANEOUS SERVICE") is None
    assert _tidy_passport_address("483920174839201748") is None
    assert _tidy_passport_address("*483920174839*") is None
    assert _address_is_administrative_noise("12 MG ROAD पति या पत्नी")
    assert _tidy_passport_address("12 MG ROAD पति या पत्नी") is None

    kept = "D.NO:12-1-47/1, SOMAJIGUDA, HYDERABAD, PIN:500082, TELANGANA, INDIA"
    assert _tidy_passport_address(kept) == kept
    assert not _address_is_administrative_noise(kept)

    for header in (
        "Address\nREPUBLIC OF INDIA\n",
        "Address\nपति या पत्नी\n",
        "Address\nMISCELLANEOUS SERVICE\n",
    ):
        assert not _extract(header).get("address")


def test_valid_mrz_line2_fills_core_fields_when_visual_is_garbage():
    """A check-digit-valid TD3 line 2 still supplies the five core fields.

    Scrambled visual text does not fill them, and it does not drop the line.
    """
    text = """
xq9 @@ scrambled visual half
Passport No
ZZ9999999
Nationality
CANADIAN
Sex
F
Date of Birth
01/01/1970
Date of Expiry
01/01/2001
not-a-street
T5253251<4IND9802056M2905121<<<<<<<<<<<<<<<0
"""
    result = _extract(text)
    assert result.get("document_number") == "T5253251"
    assert result.get("date_of_birth") == "05-02-1998"
    assert result.get("date_of_expiry") == "12-05-2029"
    assert result.get("sex") == "M"
    assert result.get("nationality") == "INDIAN"


def test_choose_passport_page_rotation_from_header_signals():
    """180° only when that probe reads the header or MRZ left to right."""
    from app.services.scanx_passport import (
        choose_passport_page_rotation,
        page_already_upright_for_orientation,
        passport_orientation_signal_score,
    )

    upright = (
        "REPUBLIC OF INDIA\n"
        "PASSPORT\n"
        "भारत\n"
        "P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<\n"
    )
    reversed_hdr = (
        "AIDNI FO CILBUPER\n"
        "TROPSSAP\n"
        + "P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<"[::-1]
        + "\n"
    )
    assert passport_orientation_signal_score(upright) > 0
    assert passport_orientation_signal_score(reversed_hdr) < 0
    assert page_already_upright_for_orientation(upright)
    assert not page_already_upright_for_orientation(reversed_hdr)
    assert not page_already_upright_for_orientation("")
    assert choose_passport_page_rotation(upright, reversed_hdr) == 0
    assert choose_passport_page_rotation(reversed_hdr, upright) == 180
    assert choose_passport_page_rotation("", "") == 0
    assert choose_passport_page_rotation(upright, upright) == 0
    assert choose_passport_page_rotation("xyz", "भारत\nपासपोर्ट") == 180


def test_stacked_canvas_rotates_only_the_inverted_half():
    """One image with two passport pages: turn the upside-down half only."""
    from app.services.scanx_passport import choose_stacked_canvas_rotation

    upright = (
        "REPUBLIC OF INDIA\n"
        "PASSPORT\n"
        "भारत\n"
        "P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<\n"
    )
    reversed_hdr = (
        "AIDNI FO CILBUPER\n"
        "TROPSSAP\n"
        + "P<INDREGURI<<ANIRUDH<<<<<<<<<<<<<<<<<<<<<<<<"[::-1]
        + "\n"
    )
    mixed = choose_stacked_canvas_rotation(upright, reversed_hdr)
    assert mixed["mode"] == "regional"
    assert mixed["top"] == 0
    assert mixed["bottom"] == 180

    other_way = choose_stacked_canvas_rotation(reversed_hdr, upright)
    assert other_way["mode"] == "regional"
    assert other_way["top"] == 180
    assert other_way["bottom"] == 0

    agreed_up = choose_stacked_canvas_rotation(upright, upright)
    assert agreed_up["mode"] == "whole"
    assert agreed_up["top"] == 0
    assert agreed_up["bottom"] == 0

    agreed_down = choose_stacked_canvas_rotation(reversed_hdr, reversed_hdr)
    assert agreed_down["mode"] == "whole"
    assert agreed_down["top"] == 180
    assert agreed_down["bottom"] == 180

    silent_bottom = choose_stacked_canvas_rotation(reversed_hdr, "")
    assert silent_bottom["mode"] == "regional"
    assert silent_bottom["top"] == 180
    assert silent_bottom["bottom"] == 0
    assert choose_stacked_canvas_rotation("", "")["mode"] == "undecided"


def test_half_that_reads_better_at_180_rotates_even_when_other_signal_is_weak():
    """An address page with no header still turns when 180° is clearly more readable.

    Observed on a side-by-side open passport: the bio page at 0° has REPUBLIC
    and a P< MRZ, while the address page at 0° is short garbage with no
    reversed header (CILBUPER / TROPSSAP). That 0°-only score is ``none``, so
    the old rule left the whole canvas at 0° next to the upright page. The
    address page at 180° is a longer place-name line (NAGAR, SCHOOL, GUNTUR,
    ANDHRA) and must rotate by itself. The upright page stays at 0°.
    """
    from app.services.scanx_passport import (
        choose_stacked_canvas_rotation,
        classify_passport_region_orientation,
    )

    upright_0 = (
        "REPUBLIC OF INDIA\n"
        "PASSPORT\n"
        "P<INDTENALI<<GOPI<REDDY<<<<<<<<<<<<<<<<<<<<<\n"
    )
    upright_180 = "AIDNI FO CILBUPER\n" + upright_0[::-1]
    weak_0 = "PGIA NARATUR KUEUAR\nRefre GE MISCELLANEOUS SERVICE\n"
    address_180 = (
        "THERUPATHI REDDY TENALI\n"
        "KRISHNA KUMARI TENALI\n"
        "PRAKASH NAGAR NEAR SWAMI SCHOOL\n"
        "NARASAROPET GUNTUR\n"
        "ANDHRA PRADESH INDIA\n"
    )

    assert classify_passport_region_orientation(weak_0) == "none"
    assert classify_passport_region_orientation(upright_0) == "upright"
    legacy = choose_stacked_canvas_rotation(upright_0, weak_0)
    assert legacy["mode"] == "whole"
    assert legacy["top"] == 0
    assert legacy["bottom"] == 0

    fixed = choose_stacked_canvas_rotation(
        upright_0,
        weak_0,
        top_probe_180=upright_180,
        bottom_probe_180=address_180,
    )
    assert fixed["mode"] == "regional"
    assert fixed["top"] == 0
    assert fixed["bottom"] == 180
    assert classify_passport_region_orientation(weak_0, address_180) == "inverted"
    assert classify_passport_region_orientation(upright_0, upright_180) == "upright"

    other_side = choose_stacked_canvas_rotation(
        weak_0,
        upright_0,
        top_probe_180=address_180,
        bottom_probe_180=upright_180,
    )
    assert other_side["mode"] == "regional"
    assert other_side["top"] == 180
    assert other_side["bottom"] == 0


def test_rotate_stacked_halves_turns_only_the_bottom():
    """A midpoint split rotates the bottom half and leaves the top pixel put."""
    import numpy as np

    from app.services.scanx_image_enhance import rotate_stacked_halves

    cv2 = __import__("cv2")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[0, 0] = (0, 0, 255)
    img[4, 0] = (255, 0, 0)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    stitched = rotate_stacked_halves(bytes(buf), top_degrees=0, bottom_degrees=180)
    assert stitched
    decoded = cv2.imdecode(np.frombuffer(stitched, np.uint8), cv2.IMREAD_COLOR)
    assert int(decoded[0, 0, 2]) == 255
    assert int(decoded[7, 7, 0]) == 255
    assert int(decoded[4, 0].sum()) == 0


def test_vertical_gutter_rotates_only_the_right_half():
    """A side-by-side canvas turns the right region and leaves the left pixel put."""
    import numpy as np

    from app.services.scanx_image_enhance import (
        locate_passport_spread_cut,
        rotate_spread_halves,
    )

    cv2 = __import__("cv2")
    img = np.full((80, 200, 3), 255, dtype=np.uint8)
    img[:, :90] = 30
    img[:, 110:] = 30
    img[0, 0] = (0, 0, 255)
    img[0, 199] = (255, 0, 0)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    raw = bytes(buf)
    located = locate_passport_spread_cut(raw)
    assert located is not None
    assert located["axis"] == "vertical"
    assert 90 <= int(located["cut"]) <= 110
    stitched = rotate_spread_halves(
        raw,
        axis="vertical",
        cut=int(located["cut"]),
        first_degrees=0,
        second_degrees=180,
    )
    assert stitched
    decoded = cv2.imdecode(np.frombuffer(stitched, np.uint8), cv2.IMREAD_COLOR)
    assert int(decoded[0, 0, 2]) == 255
    assert tuple(int(v) for v in decoded[0, -1]) != (255, 0, 0)
    blues = np.where(
        (decoded[:, :, 0] == 255)
        & (decoded[:, :, 1] == 0)
        & (decoded[:, :, 2] == 0)
    )
    assert blues[0].size == 1
    assert int(blues[0][0]) > 40
    assert int(blues[1][0]) >= int(located["cut"])


def test_rotate_image_bytes_180_moves_corner_pixel():
    """180° rotation is a pixel flip. No scan fixture and no OCR."""
    import numpy as np

    from app.services.scanx_image_enhance import rotate_image_bytes_180

    cv2 = __import__("cv2")
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[0, 0] = (0, 0, 255)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    rotated = rotate_image_bytes_180(bytes(buf))
    assert rotated
    decoded = cv2.imdecode(np.frombuffer(rotated, np.uint8), cv2.IMREAD_COLOR)
    assert int(decoded[7, 7, 2]) == 255
    assert int(decoded[0, 0].sum()) == 0


PLACE_GF_BIRTH_OCR = """
REPUBLIC OF INDIA
Place gf Birth
NARASAROPET, ANDHRA PRADESH
Place of Issue
VIJAYAWADA
"""


def test_place_gf_birth_label_uses_city_state_not_the_street():
    """OCR ``Place gf Birth`` is the birth label. The value is city, state."""
    result = _extract(PLACE_GF_BIRTH_OCR)
    assert result.get("place_of_birth") == "NARASAROPET, ANDHRA PRADESH"
    assert result.get("place_of_issue") == "VIJAYAWADA"
    street = _extract(
        "Place gf Birth 12-1-47/1 PRAKASH NAGAR NEAR SWAMI SCHOOL\n"
        "NARASAROPET, ANDHRA PRADESH\n"
        "Place of Issue\n"
        "VIJAYAWADA\n"
    )
    assert street.get("place_of_birth") == "NARASAROPET, ANDHRA PRADESH"
    assert "NAGAR" not in str(street.get("place_of_birth") or "")
    assert street.get("place_of_issue") == "VIJAYAWADA"
    assert street.get("place_of_issue") != street.get("place_of_birth")


MOTHER_STARTS_WITH_FATHER_OCR = """
Name of Father / Legal Guardian
THIRUPATHI REDDY TENALI
Name of Mother
THIRUPATHI REDDY TENALI KRISHNA KUMARI
"""


def test_mother_prefix_that_is_the_father_name_is_stripped():
    """Mother keeps her own label value, without the father name in front."""
    full = _extract(MOTHER_STARTS_WITH_FATHER_OCR)
    assert full.get("father_name") == "THIRUPATHI REDDY TENALI"
    assert full.get("mother_name") == "KRISHNA KUMARI"
    portion = _extract(
        "Name of Father / Legal Guardian\n"
        "THIRUPATHI REDDY TENALI\n"
        "Name of Mother\n"
        "TENALI KRISHNA KUMARI TENALI\n"
    )
    assert portion.get("father_name") == "THIRUPATHI REDDY TENALI"
    assert portion.get("mother_name") == "KRISHNA KUMARI TENALI"
    assert not str(portion.get("mother_name") or "").upper().startswith("TENALI")
    untouched = _extract(
        "Name of Father / Legal Guardian\n"
        "ANIL KUMAR REGURI\n"
        "Name of Mother\n"
        "SRILATHA REGURI\n"
    )
    assert untouched.get("mother_name") == "SRILATHA REGURI"


def test_address_leading_ntr_indian_and_place_gf_birth_are_stripped():
    """Junk at the absolute start is dropped. A clean street is left as written."""
    junk = """
Address
NTR/INDIAN, Place gf Birth 12-1-47/1 PRAKASH NAGAR NEAR SWAMI SCHOOL
NARASAROPET, GUNTUR
PIN:522601, ANDHRA PRADESH, INDIA
"""
    address = str(_extract(junk).get("address") or "")
    assert address.upper().startswith("12-1-47/1")
    assert not address.upper().startswith("NTR")
    assert "PLACE GF BIRTH" not in address.upper()
    assert "PRAKASH NAGAR" in address.upper()
    clean = "D.NO:12-1-47/1, NEAR ADDRESS OFFICE, HYDERABAD, PIN:500082, TELANGANA, INDIA"
    assert _tidy_passport_address(clean) == clean
    assert _tidy_passport_address(
        "NTR/INDIAN, Place gf Birth 12-1-47/1 PRAKASH NAGAR"
    ).upper().startswith("12-1-47/1")

