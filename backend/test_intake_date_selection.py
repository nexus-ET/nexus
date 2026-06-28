"""Tests for date selection parsing during WhatsApp intake."""

from datetime import date
from types import SimpleNamespace

from app.services.admissions_intake_flow import (
    _offered_dates_for_lead,
    _parse_date_selection,
    _parse_time_selection,
    _resolve_selected_date,
)
from types import SimpleNamespace


def test_parse_date_selection_accepts_number():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _parse_date_selection("2", dates) == 2


def test_parse_date_selection_accepts_meta_list_id():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _parse_date_selection("date:2026-07-01", dates) == 2


def test_parse_date_selection_rejects_okay():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _parse_date_selection("okay", dates) is None


def test_resolve_selected_date_uses_offered_list():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _resolve_selected_date("date:2026-07-01", dates) == date(2026, 7, 1)


def test_resolve_selected_date_trusts_meta_list_id_even_if_offered_drifted():
    dates = [date(2026, 6, 30)]
    assert _resolve_selected_date("date:2026-07-01", dates) == date(2026, 7, 1)


def test_offered_dates_for_lead_prefers_context(monkeypatch):
    class FakeLead:
        intake_context = '{"date_options": ["2026-07-01", "2026-07-02"]}'

    class FakeSession:
        pass

    offered = _offered_dates_for_lead(FakeSession(), FakeLead())  # type: ignore[arg-type]
    assert offered == [date(2026, 7, 1), date(2026, 7, 2)]


def test_parse_date_selection_does_not_confuse_month_with_list_index():
    dates = [
        date(2026, 6, 24),
        date(2026, 6, 25),
        date(2026, 6, 26),
        date(2026, 6, 27),
        date(2026, 6, 28),
        date(2026, 6, 29),
        date(2026, 7, 4),
        date(2026, 7, 6),
    ]
    assert _resolve_selected_date("date:2026-06-29", dates) == date(2026, 6, 29)
    assert _parse_date_selection("date:2026-06-29", dates) == 6


def test_parse_time_selection_uses_slot_id_not_embedded_digits():
    slots = [
        SimpleNamespace(id=49, slot_date=date(2026, 6, 29), slot_time="10:00"),
        SimpleNamespace(id=50, slot_date=date(2026, 6, 29), slot_time="14:00"),
        SimpleNamespace(id=51, slot_date=date(2026, 6, 29), slot_time="16:00"),
        SimpleNamespace(id=52, slot_date=date(2026, 6, 29), slot_time="17:00"),
    ]
    assert _parse_time_selection("time:49", slots) == 1
    assert _parse_time_selection("time:52", slots) == 4
