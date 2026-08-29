"""Tests for date and time availability during WhatsApp intake.

Availability tests below pin the *live configured* business-hours shape for this
workspace (Asia/Kolkata, 10:00-18:00, Mon-Sat, 60 minute slots) so a regression in
same-day booking is caught with the settings students actually see.
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from app.services import counselling_service
from app.services.admissions_intake_flow import (
    _format_available_slot_date,
    _offered_dates_for_lead,
    _parse_date_selection,
    _parse_time_selection,
    _resolve_selected_date,
)

# Mirrors the configured DynamicSetting rows for this deployment.
LIVE_OFFICE_START = time(10, 0)
LIVE_OFFICE_END = time(18, 0)
LIVE_SLOT_MINUTES = 60
LIVE_WORKING_WEEKDAYS = {0, 1, 2, 3, 4, 5}  # Mon-Sat
MONDAY = date(2026, 8, 17)


class FakeSession:
    pass


def _apply_live_office_hours(
    monkeypatch,
    *,
    office_end: time = LIVE_OFFICE_END,
    lead_minutes: int = 120,
):
    monkeypatch.setattr(counselling_service, "_get_office_start", lambda db: LIVE_OFFICE_START)
    monkeypatch.setattr(counselling_service, "_get_office_end", lambda db: office_end)
    monkeypatch.setattr(counselling_service, "_get_slot_minutes", lambda db: LIVE_SLOT_MINUTES)
    monkeypatch.setattr(
        counselling_service,
        "_get_same_day_booking_lead_minutes",
        lambda db: lead_minutes,
    )


def _mock_bookable_dates(
    monkeypatch,
    now: datetime,
    *,
    office_end: time = LIVE_OFFICE_END,
    closed_dates: set[date] | None = None,
):
    """Live office hours + Mon-Sat working week, with optional holiday closures."""
    closed_dates = closed_dates or set()
    _apply_live_office_hours(monkeypatch, office_end=office_end)
    monkeypatch.setattr(counselling_service, "office_now", lambda db: now)
    monkeypatch.setattr(
        counselling_service,
        "is_bookable_day",
        lambda db, slot_day: (
            slot_day not in closed_dates and slot_day.weekday() in LIVE_WORKING_WEEKDAYS
        ),
    )
    monkeypatch.setattr(
        counselling_service,
        "get_bookable_slot_starts",
        lambda db, slot_day: (
            _live_day_slot_starts(slot_day, now, office_end)
            if slot_day > now.date() or counselling_service._same_day_booking_window_is_open(None, now)
            else []
        ),
    )


def _live_day_slot_starts(slot_day: date, now: datetime, office_end: time) -> list[datetime]:
    starts: list[datetime] = []
    cursor = datetime.combine(slot_day, LIVE_OFFICE_START)
    end = datetime.combine(slot_day, office_end)
    while cursor < end:
        if cursor > now:
            starts.append(cursor)
        cursor += timedelta(minutes=LIVE_SLOT_MINUTES)
    return starts


def test_midday_offers_same_day_consultation(monkeypatch):
    now = datetime(2026, 8, 17, 13, 0)
    _mock_bookable_dates(monkeypatch, now)

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=2)

    assert dates == [MONDAY, date(2026, 8, 18)]


def test_available_date_label_marks_today_and_tomorrow(monkeypatch):
    from app.services import admissions_intake_flow as flow

    monkeypatch.setattr(flow, "office_today", lambda db: MONDAY)

    assert _format_available_slot_date(FakeSession(), MONDAY) == "Today (Mon, Aug 17, 2026)"
    assert _format_available_slot_date(
        FakeSession(), date(2026, 8, 18)
    ) == "Tomorrow (Tue, Aug 18, 2026)"
    assert _format_available_slot_date(
        FakeSession(), date(2026, 8, 19)
    ) == "Wed, Aug 19, 2026"


def test_available_date_label_skips_tomorrow_when_not_next_calendar_day(monkeypatch):
    """If today is Friday and next offered day is Monday, do not label Monday as Tomorrow."""
    from app.services import admissions_intake_flow as flow

    friday = date(2026, 8, 21)
    monday = date(2026, 8, 24)
    monkeypatch.setattr(flow, "office_today", lambda db: friday)

    assert _format_available_slot_date(FakeSession(), friday) == "Today (Fri, Aug 21, 2026)"
    assert _format_available_slot_date(FakeSession(), monday) == "Mon, Aug 24, 2026"


def test_before_office_opens_still_offers_today(monkeypatch):
    """Early-morning IST: the whole office day is ahead, so today must be first."""
    now = datetime(2026, 8, 17, 5, 45)
    _mock_bookable_dates(monkeypatch, now)

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=2)

    assert dates == [MONDAY, date(2026, 8, 18)]


def test_last_business_hour_start_from_tomorrow(monkeypatch):
    """16:01 leaves under the 2 hour minimum before the 18:00 close."""
    now = datetime(2026, 8, 17, 16, 1)
    _mock_bookable_dates(monkeypatch, now)

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=1)

    assert dates == [date(2026, 8, 18)]


@pytest.mark.parametrize(
    ("office_end", "last_booking_hour"),
    [
        (time(18, 0), 16),
        (time(20, 0), 18),
        (time(21, 0), 19),
    ],
)
def test_same_day_cutoff_tracks_configured_close_time(
    monkeypatch,
    office_end: time,
    last_booking_hour: int,
):
    """The cutoff is always live office close minus the configured two-hour lead."""
    _apply_live_office_hours(monkeypatch, office_end=office_end, lead_minutes=120)
    at_cutoff = datetime(2026, 8, 17, last_booking_hour, 0)
    after_cutoff = at_cutoff + timedelta(minutes=1)

    assert counselling_service._same_day_booking_window_is_open(None, at_cutoff)
    assert not counselling_service._same_day_booking_window_is_open(None, after_cutoff)


def test_same_day_cutoff_tracks_configured_lead_minutes(monkeypatch):
    _apply_live_office_hours(
        monkeypatch,
        office_end=time(18, 0),
        lead_minutes=60,
    )

    assert counselling_service._same_day_booking_window_is_open(
        None,
        datetime(2026, 8, 17, 17, 0),
    )
    assert not counselling_service._same_day_booking_window_is_open(
        None,
        datetime(2026, 8, 17, 17, 1),
    )


def test_after_close_starts_from_tomorrow(monkeypatch):
    now = datetime(2026, 8, 17, 21, 30)
    _mock_bookable_dates(monkeypatch, now)

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=1)

    assert dates == [date(2026, 8, 18)]


def test_holiday_skips_today_and_uses_next_open_day(monkeypatch):
    now = datetime(2026, 8, 17, 13, 0)
    _mock_bookable_dates(monkeypatch, now, closed_dates={MONDAY})

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=1)

    assert dates == [date(2026, 8, 18)]


def test_sunday_is_skipped_for_the_live_working_week(monkeypatch):
    saturday_evening = datetime(2026, 8, 22, 19, 0)
    _mock_bookable_dates(monkeypatch, saturday_evening)

    dates = counselling_service.list_whatsapp_bookable_dates(FakeSession(), limit=1)

    assert dates == [date(2026, 8, 24)]


def test_same_day_times_only_include_future_slots(monkeypatch):
    class EmptyBookingQuery:
        def filter(self, *args):
            return self

        def all(self):
            return []

    class BookingSession:
        def query(self, *args):
            return EmptyBookingQuery()

    _apply_live_office_hours(monkeypatch)
    monkeypatch.setattr(counselling_service, "office_now", lambda db: datetime(2026, 8, 17, 13, 15))
    monkeypatch.setattr(counselling_service, "is_bookable_day", lambda db, day: True)
    monkeypatch.setattr(counselling_service, "get_max_bookings_per_slot", lambda db: 5)

    slots = counselling_service.get_bookable_slot_starts(BookingSession(), MONDAY)

    assert slots == [
        datetime(2026, 8, 17, 14, 0),
        datetime(2026, 8, 17, 15, 0),
        datetime(2026, 8, 17, 16, 0),
        datetime(2026, 8, 17, 17, 0),
    ]

    monkeypatch.setattr(counselling_service, "office_now", lambda db: datetime(2026, 8, 17, 5, 45))
    assert counselling_service.get_bookable_slot_starts(BookingSession(), MONDAY) == [
        datetime(2026, 8, 17, hour, 0) for hour in range(10, 18)
    ]

    monkeypatch.setattr(counselling_service, "office_now", lambda db: datetime(2026, 8, 17, 16, 1))
    assert counselling_service.get_bookable_slot_starts(BookingSession(), MONDAY) == []


@pytest.mark.parametrize(
    ("office_end", "now", "expected_hours"),
    [
        (time(18, 0), datetime(2026, 8, 17, 15, 15), [16, 17]),
        (time(20, 0), datetime(2026, 8, 17, 17, 15), [18, 19]),
        (time(21, 0), datetime(2026, 8, 17, 18, 15), [19, 20]),
    ],
)
def test_today_slots_are_future_and_follow_configured_close(
    monkeypatch,
    office_end: time,
    now: datetime,
    expected_hours: list[int],
):
    class EmptyBookingQuery:
        def filter(self, *args):
            return self

        def all(self):
            return []

    class BookingSession:
        def query(self, *args):
            return EmptyBookingQuery()

    _apply_live_office_hours(monkeypatch, office_end=office_end)
    monkeypatch.setattr(counselling_service, "office_now", lambda db: now)
    monkeypatch.setattr(counselling_service, "is_bookable_day", lambda db, day: True)
    monkeypatch.setattr(counselling_service, "get_max_bookings_per_slot", lambda db: 5)

    slots = counselling_service.get_bookable_slot_starts(BookingSession(), MONDAY)

    assert slots == [datetime(2026, 8, 17, hour, 0) for hour in expected_hours]
    assert all(slot > now for slot in slots)


def test_time_picker_offers_nothing_when_day_has_no_open_slot(monkeypatch):
    """Closed/expired day must not fall back to the raw ConsultationSlot rows."""
    from app.services import admissions_intake_flow as flow

    class ExplodingSession:
        def query(self, *args):
            raise AssertionError("slot rows must not be read when no start time is bookable")

    monkeypatch.setattr(flow, "is_bookable_day", lambda db, day: True)
    monkeypatch.setattr(flow, "_ensure_slots_for_day", lambda db, day: None)
    monkeypatch.setattr(counselling_service, "get_bookable_slot_starts", lambda db, day: [])

    assert flow._available_times_for_date(ExplodingSession(), MONDAY) == []


def test_parse_date_selection_accepts_number():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _parse_date_selection("2", dates) == 2


def test_parse_date_selection_accepts_meta_list_id():
    dates = [date(2026, 6, 30), date(2026, 7, 1)]
    assert _parse_date_selection("date:2026-07-01", dates) == 2


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Today 17 Aug, 2026", 1),
        ("Tomorrow 18 Aug, 2026", 2),
        ("Wed 19 Aug, 2026", 3),
        ("Today · 17 Aug", 1),
        ("Tomorrow · 18 Aug", 2),
        ("Wed, 19 Aug", 3),
        ("Today (Mon, Aug 17, 2026)", 1),
        ("Tomorrow (Tue, Aug 18, 2026)", 2),
        ("Tue, Aug 18, 2026", 2),
        ("Today (Mon, Aug 17, 2026", 1),
        ("Tomorrow (Tue, Aug 18, 2", 2),
    ],
)
def test_parse_date_selection_accepts_meta_date_row_text(reply, expected):
    dates = [date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)]
    assert _parse_date_selection(reply, dates) == expected


def test_parse_date_selection_accepts_selected_display_label():
    dates = [date(2026, 8, 10), date(2026, 8, 11)]
    assert _parse_date_selection("Selected Mon, Aug 10, 2026", dates) == 1
    assert _resolve_selected_date("Selected Mon, Aug 10, 2026", dates) == date(2026, 8, 10)


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
    assert _parse_time_selection("Selected 10:00 AM", slots) == 1
