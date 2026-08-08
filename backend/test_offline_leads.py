"""Tests for offline leads listing and creation."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.offline_lead import OfflineLeadCreate
from app.services.offline_leads_service import (
    OFFLINE_SOURCE,
    build_offline_lead_list_item,
    check_offline_lead_duplicates,
    create_offline_lead,
    update_offline_lead,
)

REQUIRED_OFFLINE_FIELDS = {
    "location": {"city": "Bengaluru", "state": "Karnataka", "country_iso2": "IN"},
    "target_destination_iso2s": ["GB"],
    "target_level_id": 2,
    "target_major_ids": [3],
    "target_program_codes": ["BBA"],
}


def test_offline_email_generated_when_missing():
    from app.services.offline_leads_service import _offline_email

    payload = SimpleNamespace(email=None)
    assert _offline_email(payload, "+918754545407").startswith("offline_")


def test_offline_lead_create_rejects_future_and_underage_dob():
    base = {
        "first_name": "Young",
        "last_name": "Student",
        "email": "young@example.com",
        "phone_country_iso2": "IN",
        "phone_local": "9876543210",
    }

    with pytest.raises(ValidationError):
        OfflineLeadCreate(**base, date_of_birth=date.today() + timedelta(days=1))

    with pytest.raises(ValidationError):
        OfflineLeadCreate(**base, date_of_birth=date.today() - timedelta(days=365 * 10))


def test_check_offline_lead_duplicates_detects_email_and_phone(monkeypatch):
    class FakeCountry:
        dial_code = "91"

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return (99,)

    monkeypatch.setattr(
        "app.services.offline_leads_service.get_country_by_iso2",
        lambda db, iso2: FakeCountry(),
    )

    db = SimpleNamespace(query=lambda model: FakeQuery())

    result = check_offline_lead_duplicates(
        db,  # type: ignore[arg-type]
        email="dup@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
    )
    assert result == {"email_taken": True, "phone_taken": True}


def test_check_offline_lead_duplicates_excludes_current_lead(monkeypatch):
    class FakeCountry:
        dial_code = "91"

    filters: list[str] = []

    class FakeQuery:
        def filter(self, *args, **kwargs):
            filters.append(str(args))
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        "app.services.offline_leads_service.get_country_by_iso2",
        lambda db, iso2: FakeCountry(),
    )

    db = SimpleNamespace(query=lambda model: FakeQuery())

    result = check_offline_lead_duplicates(
        db,  # type: ignore[arg-type]
        email="unique@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
        exclude_lead_id=5,
    )
    assert result == {"email_taken": False, "phone_taken": False}
    assert any("5" in item for item in filters)


def test_build_offline_lead_list_item_maps_fields():
    lead = SimpleNamespace(
        id=1,
        full_name="Jane Doe",
        email="jane@example.com",
        phone_number="+911234567890",
        stage=SimpleNamespace(value="AI_ACTIVE"),
        is_human_locked=False,
        source=OFFLINE_SOURCE,
        preferred_country="UK",
        academic_summary="MSc CS",
        current_location="London, England, United Kingdom",
        additional_data={
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_country_iso2": "GB",
            "date_of_birth": "2000-01-15",
            "education": {"degree": "BSc", "university": "ABC", "graduation_year": 2022},
            "location": {
                "city": "London",
                "state": "England",
                "country_iso2": "GB",
                "country": "United Kingdom",
            },
            "target_course": "MSc CS",
        },
        created_at=None,
    )
    item = build_offline_lead_list_item(lead)  # type: ignore[arg-type]
    assert item["full_name"] == "Jane Doe"
    assert item["first_name"] == "Jane"
    assert item["status_label"] == "AI Active"
    assert item["degree"] == "BSc"
    assert item["city"] == "London"
    assert item["age"] == pytest.approx(26, abs=1)


def test_create_offline_lead_rejects_duplicate_phone(monkeypatch):
    class FakeCountry:
        dial_code = "91"

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return (99,)

    class FakeSession:
        call_count = 0

        def query(self, model):
            self.call_count += 1
            return FakeQuery()

        def add(self, obj):
            pass

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    monkeypatch.setattr(
        "app.services.offline_leads_service.get_country_by_iso2",
        lambda db, iso2: FakeCountry(),
    )

    payload = OfflineLeadCreate(
        first_name="Dup",
        last_name="Phone",
        phone_country_iso2="IN",
        phone_local="9999999999",
        email="dup@example.com",
        date_of_birth="2000-01-01",
        **REQUIRED_OFFLINE_FIELDS,
    )

    with pytest.raises(HTTPException) as exc:
        create_offline_lead(FakeSession(), payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 409


def test_update_offline_lead_rejects_duplicate_phone_for_other_lead(monkeypatch):
    class FakeCountry:
        dial_code = "91"

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return (99,)

    class FakeLead:
        id = 1
        full_name = "Existing Lead"
        email = "existing@example.com"
        phone_number = "+919999999999"
        preferred_country = None
        academic_summary = None
        current_location = None
        additional_data = {"entry_type": "offline"}

    class FakeSession:
        def query(self, model):
            return FakeQuery()

        def commit(self):
            pass

        def refresh(self, obj):
            pass

    monkeypatch.setattr(
        "app.services.offline_leads_service.get_country_by_iso2",
        lambda db, iso2: FakeCountry(),
    )
    monkeypatch.setattr(
        "app.services.offline_leads_service.get_offline_lead",
        lambda db, lead_id: FakeLead(),
    )

    payload = OfflineLeadCreate(
        first_name="Updated",
        last_name="Lead",
        phone_country_iso2="IN",
        phone_local="8888888888",
        email="updated@example.com",
        date_of_birth="2000-01-01",
        **REQUIRED_OFFLINE_FIELDS,
    )

    with pytest.raises(HTTPException) as exc:
        update_offline_lead(FakeSession(), 1, payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 409
