from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy.orm import Session

from app.config import settings

BUSINESS_TIMEZONE_KEY = "BUSINESS_TIMEZONE"

BUSINESS_TIMEZONE_OPTIONS: list[dict[str, str]] = [
    {"value": "UTC", "label": "UTC — Coordinated Universal Time"},
    {"value": "Asia/Kolkata", "label": "India — Kolkata (IST)"},
    {"value": "Asia/Dubai", "label": "UAE — Dubai (GST)"},
    {"value": "Asia/Singapore", "label": "Singapore (SGT)"},
    {"value": "Asia/Tokyo", "label": "Japan — Tokyo (JST)"},
    {"value": "Asia/Shanghai", "label": "China — Shanghai (CST)"},
    {"value": "Asia/Bangkok", "label": "Thailand — Bangkok (ICT)"},
    {"value": "Europe/London", "label": "UK — London (GMT/BST)"},
    {"value": "Europe/Paris", "label": "Europe — Paris (CET/CEST)"},
    {"value": "Europe/Berlin", "label": "Europe — Berlin (CET/CEST)"},
    {"value": "America/New_York", "label": "US — Eastern (ET)"},
    {"value": "America/Chicago", "label": "US — Central (CT)"},
    {"value": "America/Denver", "label": "US — Mountain (MT)"},
    {"value": "America/Los_Angeles", "label": "US — Pacific (PT)"},
    {"value": "America/Toronto", "label": "Canada — Toronto (ET)"},
    {"value": "Australia/Sydney", "label": "Australia — Sydney (AEST/AEDT)"},
    {"value": "Pacific/Auckland", "label": "New Zealand — Auckland (NZST/NZDT)"},
    {"value": "Africa/Johannesburg", "label": "South Africa — Johannesburg (SAST)"},
]


def is_valid_timezone(name: str) -> bool:
    cleaned = name.strip()
    if not cleaned:
        return False
    if cleaned in available_timezones():
        return True
    try:
        ZoneInfo(cleaned)
        return True
    except Exception:
        return False


def get_business_timezone_name(db: Session | None = None) -> str:
    from app.services.settings_service import get_setting

    default = getattr(settings, "APP_TIMEZONE", None) or "UTC"
    raw = get_setting(BUSINESS_TIMEZONE_KEY, default=default, db=db)
    if raw and is_valid_timezone(raw):
        return raw.strip()
    return default if is_valid_timezone(default) else "UTC"


def get_business_zoneinfo(db: Session | None = None) -> ZoneInfo:
    return ZoneInfo(get_business_timezone_name(db))


def office_now(db: Session | None = None) -> datetime:
    """Current wall-clock time in the business timezone (naive, for slot comparisons)."""
    aware = datetime.now(get_business_zoneinfo(db))
    return aware.replace(second=0, microsecond=0, tzinfo=None)


def business_now(db: Session | None = None) -> datetime:
    """Current wall-clock time in the business timezone (naive, for audit timestamps)."""
    return datetime.now(get_business_zoneinfo(db)).replace(tzinfo=None)


def office_today(db: Session | None = None) -> date:
    return datetime.now(get_business_zoneinfo(db)).date()


def utc_now() -> datetime:
    """Timezone-aware UTC instant for event timestamps (TIMESTAMPTZ / DateTime(timezone=True))."""
    return datetime.now(ZoneInfo("UTC"))


def utc_now_naive() -> datetime:
    """Naive UTC wall-clock. Prefer utc_now() for new event writes into TIMESTAMPTZ columns."""
    return utc_now().replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC for comparisons and storage."""
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


def format_timezone_label(tz_name: str) -> str:
    for option in BUSINESS_TIMEZONE_OPTIONS:
        if option["value"] == tz_name:
            return option["label"]
    return tz_name.replace("_", " ")
