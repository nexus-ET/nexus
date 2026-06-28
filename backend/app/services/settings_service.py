from __future__ import annotations

from datetime import date, datetime, time
from threading import Lock

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dynamic_setting import DynamicSetting
from app.models.user import User
from app.utils.timezone import BUSINESS_TIMEZONE_OPTIONS, is_valid_timezone

WORKING_DAY_CODES: list[tuple[str, str]] = [
    ("mon", "Monday"),
    ("tue", "Tuesday"),
    ("wed", "Wednesday"),
    ("thu", "Thursday"),
    ("fri", "Friday"),
    ("sat", "Saturday"),
    ("sun", "Sunday"),
]

WORKING_DAY_CODE_TO_WEEKDAY = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

DEFAULT_WORKING_DAYS = "mon,tue,wed,thu,fri"

SETTING_DEFINITIONS: dict[str, dict[str, str]] = {
    "COUNSELING_SLOT_DURATION": {
        "label": "Counselling slot duration (minutes)",
        "value_type": "number",
        "description": "Length of each counselling appointment slot.",
    },
    "ALLOW_BOOKINGS": {
        "label": "Allow new bookings",
        "value_type": "boolean",
        "description": "When disabled, new counselling bookings cannot be created.",
    },
    "OFFICE_HOURS_START": {
        "label": "Office hours start",
        "value_type": "time",
        "description": "Daily start time for bookable counselling slots (24h HH:MM).",
    },
    "OFFICE_HOURS_END": {
        "label": "Office hours end",
        "value_type": "time",
        "description": "Daily end time for bookable counselling slots (24h HH:MM).",
    },
    "WORKING_DAYS": {
        "label": "Working days",
        "value_type": "working_days",
        "description": "Days of the week when counselling bookings and office slots are available.",
    },
    "MAX_BOOKINGS_PER_SLOT": {
        "label": "Max bookings per slot",
        "value_type": "number",
        "description": "Maximum pending or scheduled bookings allowed at the same time.",
    },
    "BUSINESS_TIMEZONE": {
        "label": "Business location timezone",
        "value_type": "timezone",
        "description": "Office timezone used for counselling schedules, slot times, and date boundaries.",
    },
    "AUDIT_LOG_RETENTION_DAYS": {
        "label": "Audit log retention (days)",
        "value_type": "number",
        "description": "Audit log entries older than this are permanently removed by the daily cleanup job.",
    },
}

DEFAULT_SETTING_VALUES: dict[str, str] = {
    "COUNSELING_SLOT_DURATION": "30",
    "ALLOW_BOOKINGS": "true",
    "OFFICE_HOURS_START": "09:00",
    "OFFICE_HOURS_END": "19:00",
    "WORKING_DAYS": DEFAULT_WORKING_DAYS,
    "MAX_BOOKINGS_PER_SLOT": "5",
    "BUSINESS_TIMEZONE": "UTC",
    "AUDIT_LOG_RETENTION_DAYS": "90",
}

_cache: dict[str, str] = {}
_cache_lock = Lock()


def clear_settings_cache() -> None:
    with _cache_lock:
        _cache.clear()


def seed_default_settings(db: Session) -> None:
    for key, value in DEFAULT_SETTING_VALUES.items():
        existing = db.query(DynamicSetting).filter(DynamicSetting.key == key).first()
        if existing:
            continue
        db.add(DynamicSetting(key=key, value=value))
    db.commit()
    clear_settings_cache()


def get_setting(
    key: str,
    default: str | None = None,
    db: Session | None = None,
) -> str | None:
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    if db is None:
        from app.db.database import SessionLocal

        session = SessionLocal()
        try:
            value = _load_setting_from_db(session, key, default)
        finally:
            session.close()
        return value

    return _load_setting_from_db(db, key, default)


def _load_setting_from_db(db: Session, key: str, default: str | None) -> str | None:
    row = db.query(DynamicSetting).filter(DynamicSetting.key == key).first()
    if row is None:
        return default
    with _cache_lock:
        _cache[key] = row.value
    return row.value


def get_int_setting(db: Session, key: str, default: int) -> int:
    raw = get_setting(key, default=str(default), db=db)
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def get_bool_setting(db: Session, key: str, default: bool = True) -> bool:
    raw = get_setting(key, default=str(default).lower(), db=db)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def get_time_setting(db: Session, key: str, default: time) -> time:
    raw = get_setting(key, default=default.strftime("%H:%M"), db=db)
    if not raw:
        return default
    try:
        hour_str, minute_str = str(raw).strip().split(":", 1)
        return time(int(hour_str), int(minute_str))
    except (TypeError, ValueError):
        return default


def parse_working_day_codes(value: str | None) -> list[str]:
    if not value:
        return []
    allowed = {code for code, _ in WORKING_DAY_CODES}
    parsed: list[str] = []
    seen: set[str] = set()
    for token in str(value).split(","):
        code = token.strip().lower()
        if code in allowed and code not in seen:
            parsed.append(code)
            seen.add(code)
    return parsed


def serialize_working_day_codes(codes: list[str]) -> str:
    allowed_order = [code for code, _ in WORKING_DAY_CODES]
    normalized = {code.strip().lower() for code in codes}
    return ",".join(code for code in allowed_order if code in normalized)


def get_working_weekdays(db: Session) -> set[int]:
    raw = get_setting("WORKING_DAYS", default=DEFAULT_WORKING_DAYS, db=db)
    codes = parse_working_day_codes(raw)
    if not codes:
        codes = parse_working_day_codes(DEFAULT_WORKING_DAYS)
    return {WORKING_DAY_CODE_TO_WEEKDAY[code] for code in codes}


def get_timezone_setting(db: Session) -> str:
    from app.utils.timezone import get_business_timezone_name

    return get_business_timezone_name(db)


def get_business_timezone_payload(db: Session) -> dict:
    from app.utils.timezone import format_timezone_label, get_business_timezone_name

    tz_name = get_business_timezone_name(db)
    return {
        "timezone": tz_name,
        "label": format_timezone_label(tz_name),
    }


def is_working_day(db: Session, target_date: date) -> bool:
    return target_date.weekday() in get_working_weekdays(db)


def _build_user_name_map(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {user.id: user for user in users}


def _serialize_setting_payload(
    db: Session,
    *,
    key: str,
    row: DynamicSetting | None,
    user_map: dict[int, User] | None = None,
) -> dict:
    definition = SETTING_DEFINITIONS.get(key, {})
    modifier_first_name: str | None = None
    modifier_last_name: str | None = None

    if row and row.updated_by_user_id:
        user: User | None = None
        if user_map is not None:
            user = user_map.get(row.updated_by_user_id)
        else:
            user = db.query(User).filter(User.id == row.updated_by_user_id).first()
        if user:
            modifier_first_name = (user.first_name or "").strip() or None
            modifier_last_name = (user.last_name or "").strip() or None

    return {
        "key": key,
        "value": row.value if row else DEFAULT_SETTING_VALUES.get(key, ""),
        "updated_at": row.updated_at if row else None,
        "updated_by_first_name": modifier_first_name,
        "updated_by_last_name": modifier_last_name,
        "label": definition.get("label", key.replace("_", " ").title()),
        "value_type": definition.get("value_type", "text"),
        "description": definition.get("description", ""),
        "options": BUSINESS_TIMEZONE_OPTIONS if definition.get("value_type") == "timezone" else None,
    }


def list_settings(db: Session) -> list[dict]:
    rows = db.query(DynamicSetting).order_by(DynamicSetting.key.asc()).all()
    row_map = {row.key: row for row in rows}
    user_map = _build_user_name_map(
        db,
        {row.updated_by_user_id for row in rows if row.updated_by_user_id},
    )
    keys = sorted(set(DEFAULT_SETTING_VALUES) | set(row_map))
    return [
        _serialize_setting_payload(db, key=key, row=row_map.get(key), user_map=user_map)
        for key in keys
    ]


def update_setting(db: Session, key: str, value: str, updated_by_user_id: int | None = None) -> dict:
    cleaned_key = key.strip()
    cleaned_value = value.strip()
    if not cleaned_key:
        raise HTTPException(status_code=400, detail="Setting key is required.")
    if cleaned_key not in DEFAULT_SETTING_VALUES and cleaned_key not in SETTING_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key '{cleaned_key}'.")

    validation_error = _validate_setting_value(cleaned_key, cleaned_value)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    if SETTING_DEFINITIONS.get(cleaned_key, {}).get("value_type") == "working_days":
        cleaned_value = serialize_working_day_codes(parse_working_day_codes(cleaned_value))

    row = db.query(DynamicSetting).filter(DynamicSetting.key == cleaned_key).first()
    if row is None:
        row = DynamicSetting(
            key=cleaned_key,
            value=cleaned_value,
            updated_by_user_id=updated_by_user_id,
        )
        db.add(row)
    else:
        row.value = cleaned_value
        row.updated_at = datetime.utcnow()
        row.updated_by_user_id = updated_by_user_id

    db.commit()
    db.refresh(row)
    clear_settings_cache()

    user_map = _build_user_name_map(db, {updated_by_user_id} if updated_by_user_id else set())
    return _serialize_setting_payload(db, key=row.key, row=row, user_map=user_map)


def _validate_setting_value(key: str, value: str) -> str | None:
    definition = SETTING_DEFINITIONS.get(key, {})
    value_type = definition.get("value_type", "text")

    if value_type == "boolean":
        if value.lower() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            return f"{key} must be a boolean value (true or false)."
        return None

    if value_type == "number":
        try:
            number = int(value)
        except ValueError:
            return f"{key} must be a whole number."
        if number <= 0:
            return f"{key} must be greater than zero."
        return None

    if value_type == "time":
        try:
            hour_str, minute_str = value.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError
        except ValueError:
            return f"{key} must be a valid time in HH:MM format."
        return None

    if value_type == "working_days":
        codes = parse_working_day_codes(value)
        if not codes:
            return "Select at least one working day."
        return None

    if value_type == "timezone":
        if not is_valid_timezone(value):
            return f"{key} must be a valid IANA timezone (e.g. Asia/Kolkata, America/New_York)."
        return None

    if not value:
        return f"{key} cannot be empty."
    return None
