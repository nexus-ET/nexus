"""Tests for Express Leads capture."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.express_lead import ExpressLeadCreate
from app.services.express_leads_service import (
    EXPRESS_SOURCE,
    _express_email,
    check_express_lead_duplicates,
    create_express_lead,
)


def test_express_email_generated_when_missing():
    assert _express_email(None, "+918754545407").startswith("express_")
    assert _express_email("  Ada@Example.com  ", "+1") == "ada@example.com"


def test_express_create_schema_accepts_major_ids():
    payload = ExpressLeadCreate(
        first_name="Ada",
        last_name="Khan",
        email="ada@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
        target_major_ids=[3, 1, 3],
    )
    assert payload.target_major_ids == [3, 1]


def test_express_create_schema_allows_optional_study_fields():
    payload = ExpressLeadCreate(
        first_name="Ada",
        last_name="Khan",
        email="ada@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
    )
    assert payload.email == "ada@example.com"
    assert payload.target_destination_iso2s == []
    assert payload.target_major_ids == []


def test_express_create_schema_rejects_short_phone():
    with pytest.raises(ValidationError):
        ExpressLeadCreate(
            first_name="Ada",
            last_name="Khan",
            email="ada@example.com",
            phone_country_iso2="IN",
            phone_local="12345",
        )


def test_express_create_schema_requires_email():
    with pytest.raises(ValidationError):
        ExpressLeadCreate(
            first_name="Ada",
            last_name="Khan",
            phone_country_iso2="IN",
            phone_local="9876543210",
        )


def test_check_express_duplicates_returns_match(monkeypatch):
    existing = SimpleNamespace(
        id=42,
        full_name="Ada Khan",
        email="ada@example.com",
        phone_number="+919876543210",
        stage="AI_ACTIVE",
        is_human_locked=False,
        source="EXPRESS",
    )

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return existing

    class FakeSession:
        def query(self, model):
            return FakeQuery()

    monkeypatch.setattr(
        "app.services.express_leads_service.get_country_by_iso2",
        lambda db, iso2: SimpleNamespace(dial_code="91", name="India"),
    )
    monkeypatch.setattr(
        "app.services.express_leads_service.find_lead_by_phone",
        lambda db, phone: existing,
    )

    result = check_express_lead_duplicates(
        FakeSession(),  # type: ignore[arg-type]
        email="ada@example.com",
        phone_country_iso2="IN",
        phone_local="9876543210",
    )
    assert result["email_match"]["id"] == 42
    assert result["email_match"]["matched_on"] == "email"
    assert result["phone_match"]["page_path"] == "/offline-leads"
    assert result["phone_match"]["page_label"] == "Offline Leads"
    assert result["phone_match"]["prospects_path"] == "/prospects/42"
    assert result["phone_match"]["source_label"] == "Express Lead"


def test_create_express_lead_rejects_duplicate_phone(monkeypatch):
    existing = SimpleNamespace(
        id=7,
        full_name="Existing Student",
        email="exist@example.com",
        phone_number="+919999999999",
        stage="HANDOFF",
        is_human_locked=True,
        source="FACEBOOK_LEAD",
    )

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return existing

    class FakeSession:
        def query(self, model):
            return FakeQuery()

        def add(self, obj):
            raise AssertionError("Must not create a duplicate lead")

    monkeypatch.setattr(
        "app.services.express_leads_service.get_country_by_iso2",
        lambda db, iso2: SimpleNamespace(dial_code="91", name="India"),
    )
    monkeypatch.setattr(
        "app.services.express_leads_service.find_lead_by_phone",
        lambda db, phone: existing,
    )

    payload = ExpressLeadCreate(
        first_name="New",
        last_name="Person",
        email="new@example.com",
        phone_country_iso2="IN",
        phone_local="9999999999",
    )
    with pytest.raises(HTTPException) as exc:
        create_express_lead(FakeSession(), payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    assert "Existing Student" in exc.value.detail["message"]
    assert "phone" in exc.value.detail["message"].lower()
    assert exc.value.detail["matches"][0]["page_path"] == "/handoffs"
    assert exc.value.detail["matches"][0]["matched_on"] == "both"
    assert exc.value.detail["matches"][0]["email"] == "exist@example.com"
    assert exc.value.detail["matches"][0]["phone_number"] == "+919999999999"


def test_check_express_duplicates_falls_back_to_students_master(monkeypatch):
    master = SimpleNamespace(
        id=88,
        lead_id=None,
        first_name="Priya",
        middle_name="",
        last_name="Shah",
        email="priya@example.com",
        phone_number="+919111111111",
        phone_local="9111111111",
        phone_number_secondary=None,
        phone_local_secondary=None,
        target_destination_iso2="CA",
        major="Computer Science",
        university=None,
        created_at=None,
    )

    class EmptyQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeSession:
        def query(self, model):
            return EmptyQuery()

    monkeypatch.setattr(
        "app.services.express_leads_service.get_country_by_iso2",
        lambda db, iso2: SimpleNamespace(dial_code="91", name="India"),
    )
    monkeypatch.setattr(
        "app.services.express_leads_service.find_lead_by_phone",
        lambda db, phone: None,
    )
    monkeypatch.setattr(
        "app.services.express_leads_service._find_email_students_master",
        lambda db, email: master,
    )
    monkeypatch.setattr(
        "app.services.express_leads_service._find_phone_students_master",
        lambda db, phone, local: None,
    )

    result = check_express_lead_duplicates(
        FakeSession(),  # type: ignore[arg-type]
        email="priya@example.com",
        phone_country_iso2="IN",
        phone_local="9111111111",
    )
    assert result["email_match"]["record_kind"] == "students_master"
    assert result["email_match"]["students_master_id"] == 88
    assert result["email_match"]["full_name"] == "Priya Shah"
    assert result["email_match"]["page_label"] == "Students Master"
    assert result["phone_match"] is None


def test_create_express_lead_rejects_students_master_phone(monkeypatch):
    master = SimpleNamespace(
        id=9,
        lead_id=15,
        first_name="Ravi",
        middle_name=None,
        last_name="Mehta",
        email="ravi@example.com",
        phone_number="+918888888888",
        phone_local="8888888888",
        phone_number_secondary=None,
        phone_local_secondary=None,
        target_destination_iso2="GB",
        major=None,
        university=None,
        created_at=None,
    )

    class EmptyQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeSession:
        def query(self, model):
            return EmptyQuery()

        def add(self, obj):
            raise AssertionError("Must not create a duplicate students-master phone")

    monkeypatch.setattr(
        "app.services.express_leads_service.get_country_by_iso2",
        lambda db, iso2: SimpleNamespace(dial_code="91", name="India"),
    )
    monkeypatch.setattr(
        "app.services.express_leads_service.find_lead_by_phone",
        lambda db, phone: None,
    )
    monkeypatch.setattr(
        "app.services.express_leads_service._find_email_students_master",
        lambda db, email: None,
    )
    monkeypatch.setattr(
        "app.services.express_leads_service._find_phone_students_master",
        lambda db, phone, local: master,
    )

    payload = ExpressLeadCreate(
        first_name="New",
        last_name="Person",
        email="brandnew@example.com",
        phone_country_iso2="IN",
        phone_local="8888888888",
    )
    with pytest.raises(HTTPException) as exc:
        create_express_lead(FakeSession(), payload)  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    assert exc.value.detail["matches"][0]["record_kind"] == "students_master"
    assert exc.value.detail["matches"][0]["students_master_id"] == 9
    assert exc.value.detail["matches"][0]["lead_id"] == 15
    assert "Ravi Mehta" in exc.value.detail["message"]


def test_express_source_constant():
    assert EXPRESS_SOURCE == "EXPRESS"
