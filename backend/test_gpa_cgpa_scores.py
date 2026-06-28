"""Tests for GPA/CGPA score resolution."""

import pytest
from fastapi import HTTPException

from app.schemas.offline_lead import OfflineLeadEducation
from app.services.gpa_cgpa_scores import apply_gpa_cgpa_fields


class FakeScore:
    def __init__(self, code: str, label: str, is_other: bool = False):
        self.code = code
        self.label = label
        self.is_other = is_other


def test_apply_gpa_cgpa_other_requires_custom_text(monkeypatch):
    monkeypatch.setattr(
        "app.services.gpa_cgpa_scores.get_gpa_cgpa_score_by_code",
        lambda db, code: FakeScore("OTHER", "Other", True),
    )

    with pytest.raises(HTTPException) as exc:
        apply_gpa_cgpa_fields(
            None,  # type: ignore[arg-type]
            OfflineLeadEducation(gpa_cgpa_code="OTHER"),
            {},
        )
    assert exc.value.status_code == 400

    payload = apply_gpa_cgpa_fields(
        None,  # type: ignore[arg-type]
        OfflineLeadEducation(gpa_cgpa_code="OTHER", gpa_cgpa="8.2 / 10"),
        {},
    )
    assert payload == {"gpa_cgpa": "8.2 / 10", "gpa_cgpa_code": "OTHER"}


def test_apply_gpa_cgpa_predefined_score(monkeypatch):
    monkeypatch.setattr(
        "app.services.gpa_cgpa_scores.get_gpa_cgpa_score_by_code",
        lambda db, code: FakeScore("CGPA_800_899", "CGPA 8.00 - 8.99"),
    )

    payload = apply_gpa_cgpa_fields(
        None,  # type: ignore[arg-type]
        OfflineLeadEducation(gpa_cgpa_code="CGPA_800_899"),
        {"degree": "BSc"},
    )
    assert payload["gpa_cgpa"] == "CGPA 8.00 - 8.99"
    assert payload["gpa_cgpa_code"] == "CGPA_800_899"
