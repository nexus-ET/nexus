"""UTC / TIMESTAMPTZ helpers for event timestamps."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.utils.timezone import as_utc, utc_now, utc_now_naive


def test_utc_now_is_timezone_aware():
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_utc_now_naive_has_no_tzinfo():
    now = utc_now_naive()
    assert now.tzinfo is None


def test_as_utc_promotes_naive_and_converts_aware():
    naive = datetime(2026, 7, 26, 2, 26, 58)
    aware = as_utc(naive)
    assert aware.tzinfo == ZoneInfo("UTC")
    assert aware.hour == 2

    kolkata = datetime(2026, 7, 26, 7, 56, 58, tzinfo=ZoneInfo("Asia/Kolkata"))
    as_utc_k = as_utc(kolkata)
    assert as_utc_k.hour == 2
    assert as_utc_k.minute == 26
