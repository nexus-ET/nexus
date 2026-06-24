"""Tests for idempotent Meta lead ingestion (save_lead)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.lead import Lead, LeadChannel, LeadStage
from app.services.lead_sync_errors import format_lead_sync_error, sanitize_stored_sync_error
from app.services.leads import (
    INITIAL_DELTA_LOOKBACK_SECONDS,
    build_lead_data_from_meta,
    format_no_new_leads_delta_message,
    normalize_lead_row,
    normalize_meta_field_key,
    parse_meta_field_data,
    resolve_delta_sync_cursor,
    save_lead,
    split_meta_contact_fields,
)
from app.services.facebook_leads import LeadgenWebhookEvent


def test_normalize_lead_row_requires_leadgen_id() -> None:
    with pytest.raises(ValueError, match="leadgen_id"):
        normalize_lead_row({"full_name": "Test"})


def test_normalize_lead_row_accepts_leadgen_id_alias() -> None:
    row = normalize_lead_row({"leadgen_id": "LEAD_123", "full_name": "Jane Doe"})
    assert row["meta_leadgen_id"] == "LEAD_123"
    assert row["full_name"] == "Jane Doe"
    assert row["email"] == "meta_LEAD_123@meta.nexus"
    assert row["stage"] == LeadStage.AI_ACTIVE
    assert row["channel"] == LeadChannel.FACEBOOK


def test_save_lead_merges_duplicate_email_into_existing_lead() -> None:
    db = MagicMock()
    existing = MagicMock(
        id=7,
        full_name="Rahul N",
        email="rahulravan385@gmail.com",
        meta_leadgen_id=None,
        channel=LeadChannel.WHATSAPP,
        phone_number=None,
    )
    lead_query = MagicMock()
    lead_query.filter.return_value.first.side_effect = [
        None,  # by leadgen_id
        existing,  # by email
        None,  # leadgen_id taken check
        None,  # phone conflict check
    ]
    db.query.return_value = lead_query

    result = save_lead(
        db,
        {
            "leadgen_id": "1237045681836065",
            "full_name": "Rahul N",
            "email": "rahulravan385@gmail.com",
            "phone_number": "+918121829995",
            "channel": LeadChannel.FACEBOOK,
            "source": "FACEBOOK_LEAD",
            "meta_campaign_name": "18/04/26_coldtraffic_leads",
        },
    )

    assert result.created is False
    assert result.lead is existing
    assert existing.meta_leadgen_id == "1237045681836065"
    assert existing.channel == LeadChannel.FACEBOOK
    db.commit.assert_called_once()


def test_save_lead_inserts_when_no_conflicts() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    created_lead = MagicMock(id=42)

    def add_side_effect(lead: Lead) -> None:
        lead.id = 42

    db.add.side_effect = add_side_effect
    db.refresh.side_effect = lambda lead: None

    with patch("app.services.leads.Lead", side_effect=lambda **kwargs: created_lead):
        result = save_lead(
            db,
            {
                "leadgen_id": "NEW_LEAD_1",
                "full_name": "Jane",
                "email": "jane@example.com",
                "channel": LeadChannel.FACEBOOK,
                "source": "FACEBOOK_LEAD",
            },
        )

    assert result.created is True
    assert result.lead.id == 42
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_format_lead_sync_error_shortens_sql_dump() -> None:
    raw = (
        "1237045681836065: (psycopg.errors.UniqueViolation) duplicate key value violates "
        'unique constraint "ix_leads_email" DETAIL: Key (email)=(rahulravan385@gmail.com) '
        "already exists. [SQL: INSERT INTO leads ...]"
    )
    assert format_lead_sync_error("1237045681836065", raw) == (
        "1237045681836065: duplicate email (rahulravan385@gmail.com)"
    )
    assert sanitize_stored_sync_error(raw) == (
        "1237045681836065: duplicate email (rahulravan385@gmail.com)"
    )


def test_resolve_delta_sync_cursor_uses_initial_30_day_window_when_empty(monkeypatch) -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = None
    monkeypatch.setattr("app.services.leads.time.time", lambda: 1_700_000_000)

    cursor = resolve_delta_sync_cursor(db)

    assert cursor.is_initial_backfill is True
    assert cursor.since_unix == str(1_700_000_000 - INITIAL_DELTA_LOOKBACK_SECONDS)
    assert cursor.since_label.endswith("UTC")


def test_resolve_delta_sync_cursor_uses_latest_meta_lead_timestamp() -> None:
    db = MagicMock()
    latest = datetime(2026, 6, 1, 12, 30, 0)
    db.query.return_value.filter.return_value.scalar.return_value = latest

    cursor = resolve_delta_sync_cursor(db)

    assert cursor.is_initial_backfill is False
    assert cursor.since_unix == str(int(latest.replace(tzinfo=timezone.utc).timestamp()))
    assert "2026-06-01 12:30:00 UTC" == cursor.since_label


def test_format_no_new_leads_delta_message() -> None:
    assert (
        format_no_new_leads_delta_message("2026-06-01 12:30:00 UTC")
        == "No new leads detected since 2026-06-01 12:30:00 UTC."
    )


def test_normalize_meta_field_key() -> None:
    assert normalize_meta_field_key("your_preferred_country") == "preferred_country"
    assert normalize_meta_field_key("your_preferred_course/university?") == "preferred_course_university"


def test_parse_meta_field_data_normalizes_custom_questions() -> None:
    parsed = parse_meta_field_data(
        [
            {"name": "full_name", "values": ["Jane Doe"]},
            {"name": "email", "values": ["jane@example.com"]},
            {"name": "your_preferred_country", "values": ["Canada"]},
            {"name": "your_preferred_course/university?", "values": ["Fashion Design"]},
        ]
    )
    assert parsed["full_name"] == "Jane Doe"
    assert parsed["preferred_country"] == "Canada"
    assert parsed["preferred_course_university"] == "Fashion Design"


def test_split_meta_contact_fields_moves_custom_fields_to_additional_data() -> None:
    normalized = parse_meta_field_data(
        [
            {"name": "full_name", "values": ["Jane Doe"]},
            {"name": "email", "values": ["jane@example.com"]},
            {"name": "phone_number", "values": ["+15551234567"]},
            {"name": "your_preferred_country", "values": ["Canada"]},
        ]
    )
    full_name, email, phone, additional = split_meta_contact_fields(normalized)
    assert full_name == "Jane Doe"
    assert email == "jane@example.com"
    assert phone == "+15551234567"
    assert additional == {"preferred_country": "Canada"}


def test_build_lead_data_from_meta_maps_payload() -> None:
    event = LeadgenWebhookEvent(
        leadgen_id="LEAD_123",
        page_id="PAGE_1",
        form_id="FORM_99",
        ad_id="AD_1",
        adgroup_id=None,
        created_time=1710000000,
        raw_value={},
    )
    details = {
        "platform": "facebook",
        "campaign_name": "Spring Fashion Leads",
        "field_data": [
            {"name": "full_name", "values": ["Alex Smith"]},
            {"name": "email", "values": ["alex@example.com"]},
            {"name": "your_preferred_country", "values": ["UK"]},
            {"name": "your_preferred_course/university?", "values": ["Fashion designer"]},
        ],
    }

    payload = build_lead_data_from_meta(event, details)

    assert payload["source"] == "FACEBOOK_LEAD"
    assert payload["meta_campaign_name"] == "Spring Fashion Leads"
    assert payload["meta_form_id"] == "FORM_99"
    assert payload["full_name"] == "Alex Smith"
    assert payload["email"] == "alex@example.com"
    assert payload["additional_data"] == {
        "preferred_country": "UK",
        "preferred_course_university": "Fashion designer",
    }
