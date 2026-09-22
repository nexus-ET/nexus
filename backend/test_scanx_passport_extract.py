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
from app.services.scanx_passport import (
    attach_passport_to_fields,
    extract_passport_fields,
    _clean_person_name,
    _is_garbage_file_number,
    _is_plausible_person_name,
    _post_validate_passport_fields,
)


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
    assert result.get("date_of_expiry") == "21-11-2028"


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
    assert result.get("spouse_name") == "LAKXMI ARAVIND"
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
