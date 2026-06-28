"""Tests for WhatsApp intake study-interest parsing."""

from app.services.admissions_intake_flow import _extract_study_interest


def test_extract_study_interest_fashion_germany():
    interest = _extract_study_interest("I want to study fashion design in Germany")
    assert interest.get("country") == "Germany"
    assert "fashion design" in (interest.get("program") or "").lower()


def test_extract_study_interest_simple_country():
    interest = _extract_study_interest("Interested in Canada")
    assert interest.get("country") == "Canada"


def test_extract_study_interest_usa_ms_in_robotics():
    interest = _extract_study_interest("Usa MS in Robotics")
    assert interest.get("country") == "USA"
    assert interest.get("program") == "MS in Robotics"


def test_extract_study_interest_mba_in_germany():
    interest = _extract_study_interest("MBA in Germany")
    assert interest.get("country") == "Germany"
    assert interest.get("program") == "MBA"


def test_normalize_country_name_usa_aliases():
    from app.services.admissions_intake_flow import _normalize_country_name

    assert _normalize_country_name("Usa") == "USA"
    assert _normalize_country_name("u.s.a.") == "USA"
