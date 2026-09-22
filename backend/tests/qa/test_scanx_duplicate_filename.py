"""Unit tests for ScanX same-filename in-flight guard."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.constants.scanx import STATUS_ACTION_REQUIRED, STATUS_PARSING, STATUS_UPLOADING
from app.services.scanx_upload_guard import (
    filenames_match_ci,
    find_inflight_same_filename,
    is_in_flight_status,
    normalize_scanx_filename,
)


def test_normalize_strips_path_components() -> None:
    assert normalize_scanx_filename(r"C:\Users\x\Marksheet.PDF") == "Marksheet.PDF"
    assert normalize_scanx_filename("  /tmp/a.pdf  ") == "a.pdf"


def test_filenames_match_case_insensitive() -> None:
    assert filenames_match_ci("Report.PDF", "report.pdf") is True
    assert filenames_match_ci("a.pdf", "b.pdf") is False


def test_in_flight_statuses_only_uploading_and_parsing() -> None:
    assert is_in_flight_status("uploading") is True
    assert is_in_flight_status("PARSING") is True
    assert is_in_flight_status(STATUS_ACTION_REQUIRED) is False
    assert is_in_flight_status("verified") is False
    assert is_in_flight_status("red_flag") is False


def test_find_inflight_same_filename_matches_ci_for_lead() -> None:
    doc = SimpleNamespace(
        id=9,
        lead_id=42,
        original_filename="Marksheet.PDF",
        status=STATUS_PARSING,
    )
    db = MagicMock()
    query = db.query.return_value
    filt = query.filter.return_value
    filt.order_by.return_value.first.return_value = doc

    found = find_inflight_same_filename(db, lead_id=42, original_filename="marksheet.pdf")
    assert found is doc
    db.query.assert_called_once()
    # Ensure we scoped to in-flight statuses (uploading/parsing).
    filter_args, filter_kwargs = query.filter.call_args
    assert filter_kwargs == {}
    assert len(filter_args) == 3


def test_find_inflight_same_filename_none_when_terminal() -> None:
    db = MagicMock()
    query = db.query.return_value
    filt = query.filter.return_value
    filt.order_by.return_value.first.return_value = None

    found = find_inflight_same_filename(db, lead_id=1, original_filename="done.pdf")
    assert found is None


def test_m17_message_includes_filename() -> None:
    from app.constants.scanx import format_message

    text = format_message("M17", name="Transcript.pdf")
    assert "Transcript.pdf" in text
    assert "already in progress" in text.lower()


def test_upload_status_constants_cover_guard() -> None:
    # Guard must use the same status strings the router writes.
    assert STATUS_UPLOADING == "uploading"
    assert STATUS_PARSING == "parsing"
