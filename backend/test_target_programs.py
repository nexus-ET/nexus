"""Tests for target study-interest resolution."""

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.models.education_major import EducationMajor
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.schemas.offline_lead import OfflineLeadCreate
from app.services.target_programs import resolve_study_interest_fields


class FakeCountry:
    def __init__(self, iso2: str, name: str):
        self.iso2 = iso2
        self.name = name


class FakeLevel:
    def __init__(self, level_id: int = 2, name: str = "Undergraduate"):
        self.id = level_id
        self.name = name


class FakeMajor:
    def __init__(self, major_id: int, label: str):
        self.id = major_id
        self.label = label
        self.is_active = True
        self.program_id = None


class FakeProgram:
    def __init__(self, code: str, name: str, level_id: int = 2, program_id: str = "p1"):
        self.id = program_id
        self.code = code
        self.name = name
        self.level_id = level_id
        self.is_active = True


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def query(self, *entities):
        entity = entities[0]
        if entity is EducationMajor:
            return FakeQuery([FakeMajor(3, "Business Administration")])
        if entity is ProgramEducationMajorMapping.education_major_id:
            return FakeQuery([(3,)])
        if entity is ProgramEducationMajorMapping.id:
            return FakeQuery([1])
        if entity is Program:
            return FakeQuery([])
        return FakeQuery([])


def _base_payload(**overrides):
    data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "phone_country_iso2": "IN",
        "phone_local": "9876543210",
        "date_of_birth": "2000-01-01",
        "location": {"city": "London", "state": "England", "country_iso2": "GB"},
        "target_destination_iso2s": ["GB", "CA"],
        "target_level_id": 2,
        "target_major_ids": [3],
        "target_program_codes": ["BBA"],
    }
    data.update(overrides)
    return OfflineLeadCreate(**data)


def test_resolve_study_interest_fields_cascades(monkeypatch):
    monkeypatch.setattr(
        "app.services.target_programs.get_country_by_iso2",
        lambda db, iso2: FakeCountry(iso2, "United Kingdom" if iso2 == "GB" else "Canada"),
    )
    monkeypatch.setattr(
        "app.services.levels.get_level",
        lambda db, level_id: FakeLevel(level_id),
    )
    monkeypatch.setattr(
        "app.services.qualification_programs.get_qualification_program_by_code",
        lambda db, code: FakeProgram("BBA", "Bachelor of Business Administration"),
    )

    result = resolve_study_interest_fields(FakeSession(), _base_payload())
    assert result["target_destination_iso2s"] == ["GB", "CA"]
    assert result["target_destination_iso2"] == "GB"
    assert "United Kingdom" in str(result["target_destination"])
    assert result["target_level_id"] == 2
    assert result["target_major_ids"] == [3]
    assert result["target_majors"] == ["Business Administration"]
    assert result["target_program_codes"] == ["BBA"]
    assert result["target_programs"] == ["Bachelor of Business Administration"]
    assert result["target_course_code"] is None


def test_resolve_study_interest_fields_requires_destination():
    payload = SimpleNamespace(
        target_destination_iso2s=[],
        target_destination_iso2="",
        target_level_id=2,
        target_major_ids=[1],
        target_program_codes=["BBA"],
    )
    with pytest.raises(HTTPException) as exc:
        resolve_study_interest_fields(None, payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert "Target destination" in exc.value.detail


def test_offline_lead_create_rejects_too_many_destinations():
    with pytest.raises(Exception):
        _base_payload(
            target_destination_iso2s=["GB", "CA", "US", "AU", "DE", "FR", "IT"]
        )
