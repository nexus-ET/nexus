"""Tests for target program and course resolution."""

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.schemas.offline_lead import OfflineLeadCreate
from app.services.target_programs import resolve_study_interest_fields


class FakeCountry:
    def __init__(self, iso2: str, name: str):
        self.iso2 = iso2
        self.name = name


class FakeProgram:
    def __init__(self, code: str, label: str, program_id: int = 1):
        self.id = program_id
        self.code = code
        self.label = label


class FakeCourse:
    def __init__(self, code: str, label: str, program_id: int = 1):
        self.id = 1
        self.code = code
        self.label = label
        self.program_id = program_id


def test_resolve_study_interest_fields_destination_program_and_course(monkeypatch):
    monkeypatch.setattr(
        "app.services.target_programs.get_country_by_iso2",
        lambda db, iso2: FakeCountry("GB", "United Kingdom"),
    )
    monkeypatch.setattr(
        "app.services.target_programs.get_target_program_by_code",
        lambda db, code: FakeProgram("COMPUTER_SCIENCE_IT", "Computer Science & IT"),
    )
    monkeypatch.setattr(
        "app.services.target_programs.get_target_course_by_code",
        lambda db, code: FakeCourse("MSC_DATA_SCIENCE", "MSc Data Science"),
    )

    payload = OfflineLeadCreate(
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
        date_of_birth="2000-01-01",
        location={"city": "London", "state": "England", "country_iso2": "GB"},
        target_destination_iso2="GB",
        target_program_code="COMPUTER_SCIENCE_IT",
        target_course_code="MSC_DATA_SCIENCE",
    )

    result = resolve_study_interest_fields(None, payload)  # type: ignore[arg-type]
    assert result == {
        "target_destination_iso2": "GB",
        "target_destination": "United Kingdom",
        "target_program_code": "COMPUTER_SCIENCE_IT",
        "target_program": "Computer Science & IT",
        "target_course_code": "MSC_DATA_SCIENCE",
        "target_course": "MSc Data Science",
    }


def test_resolve_study_interest_fields_requires_all_fields():
    payload = SimpleNamespace(
        target_destination_iso2="",
        target_program_code="COMPUTER_SCIENCE_IT",
        target_course_code="MSC_DATA_SCIENCE",
    )

    with pytest.raises(HTTPException) as exc:
        resolve_study_interest_fields(None, payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "Target destination" in exc.value.detail
