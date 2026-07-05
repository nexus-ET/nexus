"""Tests for degree, major, country intake steps and text limits."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import settings
from app.services.admissions_intake_flow import (
    INTAKE_STEP_CURRENT_LOCATION,
    INTAKE_STEP_ENGLISH_SCORES,
    INTAKE_STEP_FULL_NAME,
    INTAKE_STEP_GRE_SCORE,
    INTAKE_STEP_TARGET_COUNTRY,
    INTAKE_STEP_TARGET_DEGREE,
    INTAKE_STEP_TARGET_MAJOR,
    INTAKE_TEXT_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SCORE_MAX_LENGTH,
    _accept_intake_name_reply,
    _normalize_major_reply,
    _normalize_score_reply,
    _normalize_target_country_reply,
    _parse_degree_selection,
    process_intake_message,
)


def test_parse_degree_selection_accepts_ids_and_labels() -> None:
    assert _parse_degree_selection("degree:masters") == "Master's Degree (1-2 years)"
    assert _parse_degree_selection("Master's Degree (1-2 years)") == "Master's Degree (1-2 years)"
    assert _parse_degree_selection("2") == "Master's Degree (1-2 years)"
    assert _parse_degree_selection("phd") == "Doctorate (3-7 years)"
    assert _parse_degree_selection("unknown") is None


def test_name_reply_enforces_max_length() -> None:
    assert _accept_intake_name_reply("Ishq") == "Ishq"
    assert _accept_intake_name_reply("A" * NAME_MAX_LENGTH) == ("A" * NAME_MAX_LENGTH).title()
    assert _accept_intake_name_reply("A" * (NAME_MAX_LENGTH + 1)) is None


def test_normalize_major_reply_enforces_length() -> None:
    assert _normalize_major_reply("Computer Science") == "Computer Science"
    assert _normalize_major_reply("a") is None
    assert _normalize_major_reply("x" * (INTAKE_TEXT_MAX_LENGTH + 1)) is None


def test_normalize_target_country_reply() -> None:
    assert _normalize_target_country_reply("UK") == "UK"
    assert _normalize_target_country_reply("jp") == "Japan"
    assert _normalize_target_country_reply("x" * (INTAKE_TEXT_MAX_LENGTH + 1)) is None


def test_normalize_score_reply_enforces_length() -> None:
    assert _normalize_score_reply("IELTS 7.5") == "IELTS 7.5"
    assert _normalize_score_reply("skip") == "skip"
    assert _normalize_score_reply("x" * (SCORE_MAX_LENGTH + 1)) is None


def test_location_advances_to_degree_picker() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Ishq",
            intake_step=INTAKE_STEP_CURRENT_LOCATION,
            intake_context=None,
            preferred_country=None,
            current_location=None,
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "Tokyo, Japan",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_DEGREE
        assert lead.current_location == "Tokyo, Japan"
        assert reply.list_picker is not None
        assert len(reply.list_picker.items) == 4

    asyncio.run(_run())


def test_degree_selection_advances_to_major() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Ishq",
            intake_step=INTAKE_STEP_TARGET_DEGREE,
            intake_context=None,
            preferred_country=None,
            current_location="Tokyo, Japan",
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "degree:masters",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_MAJOR
        context = json.loads(lead.intake_context)
        assert context["target_degree"] == "Master's Degree (1-2 years)"
        assert "major" in reply.text.lower()

    asyncio.run(_run())


def test_valid_major_advances_to_country() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Ishq",
            intake_step=INTAKE_STEP_TARGET_MAJOR,
            intake_context=json.dumps({"target_degree": "Master's Degree (1-2 years)"}),
            preferred_country=None,
            current_location="Tokyo, Japan",
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "Computer Science",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_TARGET_COUNTRY
        assert "country" in reply.text.lower()
        assert "uk" in reply.text.lower()

    asyncio.run(_run())


def test_valid_country_advances_to_english_scores() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Ishq",
            intake_step=INTAKE_STEP_TARGET_COUNTRY,
            intake_context=json.dumps(
                {
                    "target_degree": "Master's Degree (1-2 years)",
                    "preferred_course": "Computer Science",
                    "target_major": "Computer Science",
                }
            ),
            preferred_country=None,
            current_location="Tokyo, Japan",
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "UK",
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_ENGLISH_SCORES
        assert lead.preferred_country == "UK"
        assert "Country: UK" in lead.academic_summary
        assert "english" in reply.text.lower()

    asyncio.run(_run())


def test_score_too_long_is_rejected() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="Ishq",
            intake_step=INTAKE_STEP_ENGLISH_SCORES,
            intake_context=None,
            preferred_country="UK",
            current_location="Tokyo, Japan",
            phone_number="+911234567890",
            academic_summary=None,
            english_test_scores=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "A" * (SCORE_MAX_LENGTH + 1),
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_ENGLISH_SCORES
        assert "20 characters" in reply.text.lower()

    asyncio.run(_run())


def test_name_too_long_is_rejected() -> None:
    async def _run() -> None:
        lead = SimpleNamespace(
            id=1,
            full_name="WhatsApp Contact (+911234567890)",
            intake_step=INTAKE_STEP_FULL_NAME,
            intake_context=None,
            preferred_country=None,
            current_location=None,
            phone_number="+911234567890",
            academic_summary=None,
            consultation_scheduled_at=None,
            wants_consultation_call=None,
        )
        db = MagicMock()
        db.commit = MagicMock()

        with patch.object(settings, "NEXUS_APPOINTMENTS_ONLY", True):
            reply = await process_intake_message(
                db,
                lead,
                "A" * (NAME_MAX_LENGTH + 1),
                MagicMock(is_active=False),
            )

        assert lead.intake_step == INTAKE_STEP_FULL_NAME
        assert "75 characters" in reply.text.lower()

    asyncio.run(_run())
