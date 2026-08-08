from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dynamic_setting import DynamicSetting
from app.models.public_holiday import PublicHoliday
from app.models.user import User
from app.services.settings_service import is_working_day
from app.utils.timezone import utc_now

PRIVATE_HOLIDAY_LABEL = "Private holiday"
MAX_HOLIDAY_NAME_LENGTH = 100
LEGACY_SETTING_KEY = "PUBLIC_HOLIDAYS"


def _normalize_holiday_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = name.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_HOLIDAY_NAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Holiday name must be {MAX_HOLIDAY_NAME_LENGTH} characters or fewer.",
        )
    return cleaned


def holiday_entry_label(name: str | None) -> str:
    return name if name else PRIVATE_HOLIDAY_LABEL


def _build_user_name_map(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {user.id: user for user in users}


def _serialize_holiday_row(row: PublicHoliday) -> dict:
    return {
        "date": row.holiday_date.isoformat(),
        "name": row.name,
        "label": holiday_entry_label(row.name),
        "is_private": row.name is None,
    }


def _parse_legacy_holiday_entries(value: str | None) -> list[dict[str, date | str | None]]:
    if not value or not str(value).strip():
        return []

    raw = str(value).strip()
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []

        entries: list[dict[str, date | str | None]] = []
        seen: set[date] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date")
            if not isinstance(raw_date, str):
                continue
            try:
                holiday_date = date.fromisoformat(raw_date.strip())
            except ValueError:
                continue
            if holiday_date in seen:
                continue
            raw_name = item.get("name")
            name: str | None = None
            if isinstance(raw_name, str):
                cleaned = raw_name.strip()
                if cleaned:
                    name = cleaned[:MAX_HOLIDAY_NAME_LENGTH]
            entries.append({"date": holiday_date, "name": name})
            seen.add(holiday_date)
        entries.sort(key=lambda entry: entry["date"])
        return entries

    parsed_dates: list[date] = []
    seen_dates: set[date] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            holiday_date = date.fromisoformat(token)
        except ValueError:
            continue
        if holiday_date not in seen_dates:
            parsed_dates.append(holiday_date)
            seen_dates.add(holiday_date)
    return [{"date": holiday_date, "name": None} for holiday_date in sorted(parsed_dates)]


def migrate_holidays_from_dynamic_settings(db: Session) -> None:
    legacy_row = db.query(DynamicSetting).filter(DynamicSetting.key == LEGACY_SETTING_KEY).first()
    if legacy_row is None:
        return

    legacy_entries = _parse_legacy_holiday_entries(legacy_row.value)
    for entry in legacy_entries:
        holiday_date = entry["date"]
        if not isinstance(holiday_date, date):
            continue
        existing = (
            db.query(PublicHoliday)
            .filter(PublicHoliday.holiday_date == holiday_date)
            .first()
        )
        if existing:
            continue
        db.add(
            PublicHoliday(
                holiday_date=holiday_date,
                name=entry.get("name") if isinstance(entry.get("name"), str) else None,
                updated_by_user_id=legacy_row.updated_by_user_id,
            )
        )

    db.delete(legacy_row)
    db.commit()


def list_public_holiday_rows(db: Session) -> list[PublicHoliday]:
    return db.query(PublicHoliday).order_by(PublicHoliday.holiday_date.asc()).all()


def get_public_holidays(db: Session) -> set[date]:
    rows = db.query(PublicHoliday.holiday_date).all()
    return {row[0] for row in rows}


def is_public_holiday(db: Session, target_date: date) -> bool:
    return (
        db.query(PublicHoliday.id)
        .filter(PublicHoliday.holiday_date == target_date)
        .first()
        is not None
    )


def is_bookable_day(db: Session, target_date: date) -> bool:
    return is_working_day(db, target_date) and not is_public_holiday(db, target_date)


def get_public_holidays_payload(db: Session) -> dict:
    rows = list_public_holiday_rows(db)
    latest_row = (
        db.query(PublicHoliday)
        .order_by(PublicHoliday.updated_at.desc(), PublicHoliday.id.desc())
        .first()
    )
    user_map = _build_user_name_map(
        db,
        {latest_row.updated_by_user_id} if latest_row and latest_row.updated_by_user_id else set(),
    )
    modifier_first_name: str | None = None
    modifier_last_name: str | None = None
    if latest_row and latest_row.updated_by_user_id:
        user = user_map.get(latest_row.updated_by_user_id)
        if user:
            modifier_first_name = (user.first_name or "").strip() or None
            modifier_last_name = (user.last_name or "").strip() or None

    return {
        "holidays": [_serialize_holiday_row(row) for row in rows],
        "updated_at": latest_row.updated_at if latest_row else None,
        "updated_by_first_name": modifier_first_name,
        "updated_by_last_name": modifier_last_name,
    }


def save_public_holiday(
    db: Session,
    holiday_date: date,
    name: str | None = None,
    updated_by_user_id: int | None = None,
) -> dict:
    normalized_name = _normalize_holiday_name(name)
    row = db.query(PublicHoliday).filter(PublicHoliday.holiday_date == holiday_date).first()
    if row is None:
        row = PublicHoliday(
            holiday_date=holiday_date,
            name=normalized_name,
            updated_by_user_id=updated_by_user_id,
        )
        db.add(row)
    else:
        row.name = normalized_name
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = utc_now()

    db.commit()
    db.refresh(row)
    return get_public_holidays_payload(db)


def remove_public_holiday(
    db: Session,
    holiday_date: date,
    updated_by_user_id: int | None = None,
) -> dict:
    row = db.query(PublicHoliday).filter(PublicHoliday.holiday_date == holiday_date).first()
    if row is None:
        return get_public_holidays_payload(db)

    db.delete(row)
    db.commit()
    return get_public_holidays_payload(db)


def bulk_save_public_holidays(
    db: Session,
    holiday_dates: list[date],
    name: str | None = None,
    updated_by_user_id: int | None = None,
) -> dict:
    if not holiday_dates:
        raise HTTPException(status_code=400, detail="Select at least one date.")

    normalized_name = _normalize_holiday_name(name)
    unique_dates = sorted(set(holiday_dates))
    existing_rows = {
        row.holiday_date: row
        for row in db.query(PublicHoliday).filter(PublicHoliday.holiday_date.in_(unique_dates)).all()
    }

    for holiday_date in unique_dates:
        row = existing_rows.get(holiday_date)
        if row is None:
            db.add(
                PublicHoliday(
                    holiday_date=holiday_date,
                    name=normalized_name,
                    updated_by_user_id=updated_by_user_id,
                )
            )
            continue
        row.name = normalized_name
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = utc_now()

    db.commit()
    return get_public_holidays_payload(db)


def bulk_remove_public_holidays(
    db: Session,
    holiday_dates: list[date],
    updated_by_user_id: int | None = None,
) -> dict:
    if not holiday_dates:
        raise HTTPException(status_code=400, detail="Select at least one date.")

    unique_dates = set(holiday_dates)
    db.query(PublicHoliday).filter(PublicHoliday.holiday_date.in_(unique_dates)).delete(
        synchronize_session=False
    )
    db.commit()
    return get_public_holidays_payload(db)


def toggle_public_holiday(
    db: Session,
    holiday_date: date,
    updated_by_user_id: int | None = None,
) -> dict:
    if is_public_holiday(db, holiday_date):
        return remove_public_holiday(db, holiday_date, updated_by_user_id)
    return save_public_holiday(db, holiday_date, None, updated_by_user_id)
