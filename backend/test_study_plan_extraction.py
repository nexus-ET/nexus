"""Tests for WhatsApp study-plan extraction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.study_plan_extraction import (
    StudyPlanExtraction,
    build_study_plan_confirmation_message,
    build_study_plan_followup_message,
    parse_study_plan_payload,
    rule_based_study_plan_extraction,
)


@pytest.mark.parametrize(
    ("message", "level", "field", "location", "status"),
    [
        ("MBA in US", "Postgraduate", "Business Administration", "USA", "complete"),
        ("Undergraduate in science", "Undergraduate", "Science", None, "incomplete"),
        ("Masters in Science in JP", "Postgraduate", "Science", "Japan", "complete"),
    ],
)
def test_rule_based_study_plan_extraction_examples(
    message: str,
    level: str | None,
    field: str | None,
    location: str | None,
    status: str,
) -> None:
    result = rule_based_study_plan_extraction(message)
    assert result.level == level
    assert result.field == field
    assert result.location == location
    assert result.status == status


def test_parse_study_plan_payload_accepts_json_string() -> None:
    parsed = parse_study_plan_payload(
        '{"level":"Postgraduate","field":"Science","location":"Japan","status":"complete"}'
    )
    assert parsed is not None
    assert parsed.status == "complete"
    assert parsed.location == "Japan"


def test_build_study_plan_followup_prefers_location() -> None:
    message = build_study_plan_followup_message(
        StudyPlanExtraction(level="Undergraduate", field="Science", location=None)
    )
    assert "country" in message.lower()


def test_build_study_plan_followup_asks_level_when_missing() -> None:
    message = build_study_plan_followup_message(
        StudyPlanExtraction(level=None, field="Science", location="USA")
    )
    assert "Undergraduate or Postgraduate" in message


def test_build_study_plan_confirmation_message() -> None:
    message = build_study_plan_confirmation_message(
        "Ishq",
        StudyPlanExtraction(
            level="Postgraduate",
            field="Business Administration",
            location="USA",
        ),
    )
    assert "Ishq" in message
    assert "Business Administration" in message
    assert "yes" in message.lower()


def test_rule_based_merges_pending_country_from_context() -> None:
    lead = SimpleNamespace(
        preferred_country="UK",
        additional_data={},
        intake_context='{"pending_country":"UK"}',
    )
    from app.services.study_plan_extraction import load_pending_study_plan

    pending = load_pending_study_plan({"pending_country": "UK"}, lead)
    result = rule_based_study_plan_extraction("MBA", pending=pending)
    assert result.location == "UK"
    assert result.level == "Postgraduate"
    assert result.field == "Business Administration"


@pytest.mark.parametrize(
    "country_reply",
    ["UK", "Uk", "U.k", "U.K.", "Usa", "USA", "Japan"],
)
def test_standalone_country_reply_after_science_field(country_reply: str) -> None:
    pending = StudyPlanExtraction(level=None, field="Science", location=None)
    result = rule_based_study_plan_extraction(country_reply, pending=pending)
    assert result.field == "Science"
    assert result.location is not None
    assert result.location in {"UK", "USA", "Japan"}


def test_standalone_country_unknown_does_not_guess() -> None:
    pending = StudyPlanExtraction(level=None, field="Science", location=None)
    result = rule_based_study_plan_extraction("Ukd", pending=pending)
    assert result.location is None
    assert result.field == "Science"


def test_standalone_science_sets_field() -> None:
    result = rule_based_study_plan_extraction("science")
    assert result.field == "Science"
    assert result.location is None


def test_undergraduate_science_then_uk_is_complete() -> None:
    first = rule_based_study_plan_extraction("Undergraduate in science")
    assert first.field == "Science"
    assert first.level == "Undergraduate"
    second = rule_based_study_plan_extraction("UK", pending=first)
    assert second.status == "complete"
    assert second.location == "UK"


def test_coalesce_prefers_rule_based_country_when_llm_returns_null() -> None:
    from app.services.study_plan_extraction import coalesce_study_plan_extractions

    pending = StudyPlanExtraction(level="Undergraduate", field="Science", location=None)
    rule = rule_based_study_plan_extraction("UK", pending=pending)
    llm_empty = StudyPlanExtraction(level=None, field=None, location=None)
    merged = coalesce_study_plan_extractions(rule, llm_empty)
    assert merged.location == "UK"
    assert merged.field == "Science"
    assert merged.level == "Undergraduate"
    assert merged.status == "complete"


def test_normalize_country_dotted_alias() -> None:
    from app.services.admissions_intake_flow import _normalize_country_name

    assert _normalize_country_name("U.k") == "UK"
    assert _normalize_country_name("U.K.") == "UK"
