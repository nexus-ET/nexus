"""Tests for WhatsApp intake study-interest parsing."""

from app.services.admissions_intake_flow import _extract_study_interest


def test_extract_study_interest_fashion_germany():
    interest = _extract_study_interest("I want to study fashion design in Germany")
    assert interest.get("country") == "Germany"
    assert "fashion design" in (interest.get("program") or "").lower()


def test_extract_study_interest_simple_country():
    interest = _extract_study_interest("Interested in Canada")
    assert interest.get("country") == "Canada"
