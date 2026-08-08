"""Tests for Full-Time Study Years lookup and education resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas.offline_lead import OfflineLeadEducation
from app.services.education_degrees import resolve_education_payload
from app.services.full_time_study_years import (
    DEFAULT_FULL_TIME_STUDY_YEARS,
    require_full_time_study_years,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def options(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows_by_model: dict):
        self.rows_by_model = rows_by_model

    def query(self, model):
        return _FakeQuery(self.rows_by_model.get(model, []))


def test_default_study_years_seed_shape():
    codes = [item["code"] for item in DEFAULT_FULL_TIME_STUDY_YEARS]
    assert codes == ["10", "12", "13", "14", "15", "16", "17+", "17+", "18+", "18+"]
    assert DEFAULT_FULL_TIME_STUDY_YEARS[0]["label"] == "10 - High School"
    assert DEFAULT_FULL_TIME_STUDY_YEARS[-1]["label"] == "18+ - Doctoral / Research"
    level_codes = [item["level_code"] for item in DEFAULT_FULL_TIME_STUDY_YEARS]
    assert level_codes == [
        "FOUNDATIONAL",
        "FOUNDATIONAL",
        "FOUNDATIONAL",
        "UNDERGRAD",
        "UNDERGRAD",
        "UNDERGRAD",
        "GRADUATE",
        "INTEGRATED",
        "DOCTORAL",
        "INTEGRATED",
    ]
    integrated = [
        item for item in DEFAULT_FULL_TIME_STUDY_YEARS if item["level_code"] == "INTEGRATED"
    ]
    assert [item["code"] for item in integrated] == ["17+", "18+"]
    assert [item["label"] for item in integrated] == [
        "17+ - Master's / Postgraduate",
        "18+ - Doctoral / Research",
    ]


def test_require_full_time_study_years_accepts_valid_code(monkeypatch):
    from app.models.full_time_study_year import FullTimeStudyYear
    from app.services import full_time_study_years as service

    row = SimpleNamespace(
        code="16",
        label="16 - 4-Year Bachelor's",
        is_active=True,
        level_id=2,
    )
    db = _FakeSession({FullTimeStudyYear: [row]})

    monkeypatch.setattr(
        service,
        "get_full_time_study_year_by_code",
        lambda _db, code, level_id=None: row if code == "16" else None,
    )
    assert require_full_time_study_years(db, "16").code == "16"
    assert require_full_time_study_years(db, "16").level_id == 2


def test_require_full_time_study_years_rejects_invalid(monkeypatch):
    from app.services import full_time_study_years as service

    monkeypatch.setattr(
        service,
        "get_full_time_study_year_by_code",
        lambda _db, code, level_id=None: None,
    )
    with pytest.raises(HTTPException) as exc:
        require_full_time_study_years(_FakeSession({}), "99")
    assert exc.value.status_code == 400


def test_resolve_education_payload_with_program(monkeypatch):
    from app.services import education_degrees as edu_service
    from app.services import qualification_programs as program_service

    program = SimpleNamespace(code="BENG", name="Bachelor of Engineering (BEng)", level_id=2)
    study_year = SimpleNamespace(code="16", level_id=2)

    monkeypatch.setattr(
        program_service,
        "require_qualification_program",
        lambda db, code, level_id=None: program,
    )
    monkeypatch.setattr(
        edu_service,
        "require_qualification_program",
        lambda db, code, level_id=None: program,
    )
    monkeypatch.setattr(
        edu_service,
        "require_full_time_study_years",
        lambda db, code, level_id=None: study_year,
    )
    monkeypatch.setattr(
        edu_service,
        "apply_gpa_cgpa_fields",
        lambda db, education, payload: {
            **payload,
            "gpa_cgpa_code": "GPA_300_349",
            "gpa_cgpa": "GPA 3.00 - 3.49",
        },
    )

    result = resolve_education_payload(
        _FakeSession({}),
        OfflineLeadEducation(
            program_code="BENG",
            level_id=2,
            full_time_study_years="16",
            major="Civil Engineering",
            university="Test University",
            graduation_year=2024,
            gpa_cgpa_code="GPA_300_349",
        ),
    )

    assert result is not None
    assert result["program_code"] == "BENG"
    assert result["program"] == "Bachelor of Engineering (BEng)"
    assert result["full_time_study_years"] == "16"
    assert result["level_id"] == 2
    assert result["major"] == "Civil Engineering"
