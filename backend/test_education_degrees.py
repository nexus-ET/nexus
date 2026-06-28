"""Tests for education degree resolution."""

import pytest
from fastapi import HTTPException

from app.schemas.offline_lead import OfflineLeadEducation
from app.services.education_degrees import resolve_education_payload


class FakeDegree:
    def __init__(self, code: str, label: str, is_other: bool = False):
        self.code = code
        self.label = label
        self.is_other = is_other


class FakeScore:
    def __init__(self, code: str, label: str, is_other: bool = False):
        self.code = code
        self.label = label
        self.is_other = is_other


def _patch_degree_and_gpa(monkeypatch, degree: FakeDegree, score: FakeScore | None = None):
    monkeypatch.setattr(
        "app.services.education_degrees.get_education_degree_by_code",
        lambda db, code: degree,
    )
    if score is not None:
        monkeypatch.setattr(
            "app.services.gpa_cgpa_scores.get_gpa_cgpa_score_by_code",
            lambda db, code: score,
        )


def test_resolve_education_payload_requires_degree_and_major(monkeypatch):
    _patch_degree_and_gpa(
        monkeypatch,
        FakeDegree("BACHELORS_DEGREE", "Bachelor's Degree (BA/BS/B.Tech)"),
    )

    with pytest.raises(HTTPException) as exc:
        resolve_education_payload(
            None,  # type: ignore[arg-type]
            OfflineLeadEducation(degree_code="BACHELORS_DEGREE"),
        )
    assert exc.value.status_code == 400
    assert "Major" in exc.value.detail


def test_resolve_education_payload_other_requires_custom_text(monkeypatch):
    _patch_degree_and_gpa(
        monkeypatch,
        FakeDegree("OTHER", "Other", True),
        FakeScore("CGPA_800_899", "CGPA 8.00 - 8.99"),
    )

    with pytest.raises(HTTPException) as exc:
        resolve_education_payload(None, OfflineLeadEducation(degree_code="OTHER"))  # type: ignore[arg-type]
    assert exc.value.status_code == 400

    payload = resolve_education_payload(
        None,  # type: ignore[arg-type]
        OfflineLeadEducation(
            degree_code="OTHER",
            degree="Custom Diploma",
            major="Physics",
            university="ABC University",
            graduation_year=2020,
            gpa_cgpa_code="CGPA_800_899",
        ),
    )
    assert payload == {
        "degree": "Custom Diploma",
        "degree_code": "OTHER",
        "major": "Physics",
        "university": "ABC University",
        "graduation_year": 2020,
        "gpa_cgpa": "CGPA 8.00 - 8.99",
        "gpa_cgpa_code": "CGPA_800_899",
    }


def test_resolve_education_payload_predefined_degree(monkeypatch):
    _patch_degree_and_gpa(
        monkeypatch,
        FakeDegree("BACHELORS_DEGREE", "Bachelor's Degree (BA/BS/B.Tech)"),
        FakeScore("CGPA_800_899", "CGPA 8.00 - 8.99"),
    )

    payload = resolve_education_payload(
        None,  # type: ignore[arg-type]
        OfflineLeadEducation(
            degree_code="BACHELORS_DEGREE",
            major="Computer Science",
            university="ABC University",
            graduation_year=2022,
            gpa_cgpa_code="CGPA_800_899",
        ),
    )
    assert payload == {
        "degree": "Bachelor's Degree (BA/BS/B.Tech)",
        "degree_code": "BACHELORS_DEGREE",
        "major": "Computer Science",
        "university": "ABC University",
        "graduation_year": 2022,
        "gpa_cgpa": "CGPA 8.00 - 8.99",
        "gpa_cgpa_code": "CGPA_800_899",
    }


def test_resolve_education_payload_requires_university_and_gpa(monkeypatch):
    _patch_degree_and_gpa(
        monkeypatch,
        FakeDegree("BACHELORS_DEGREE", "Bachelor's Degree (BA/BS/B.Tech)"),
    )

    with pytest.raises(HTTPException) as exc:
        resolve_education_payload(
            None,  # type: ignore[arg-type]
            OfflineLeadEducation(
                degree_code="BACHELORS_DEGREE",
                major="Physics",
                graduation_year=2022,
            ),
        )
    assert exc.value.status_code == 400
    assert "University" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        resolve_education_payload(
            None,  # type: ignore[arg-type]
            OfflineLeadEducation(
                degree_code="BACHELORS_DEGREE",
                major="Physics",
                university="ABC University",
            ),
        )
    assert exc.value.status_code == 400
    assert "Graduation year" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        resolve_education_payload(
            None,  # type: ignore[arg-type]
            OfflineLeadEducation(
                degree_code="BACHELORS_DEGREE",
                major="Physics",
                university="ABC University",
                graduation_year=2022,
            ),
        )
    assert exc.value.status_code == 400
    assert "GPA/CGPA" in exc.value.detail
