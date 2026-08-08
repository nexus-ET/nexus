from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.full_time_study_year import FullTimeStudyYear

# FT code → levels.code (kept in sync with Alembic seed map)
DEFAULT_FULL_TIME_STUDY_YEARS: list[dict[str, str | int]] = [
    {
        "code": "10",
        "label": "10 - High School",
        "level_code": "FOUNDATIONAL",
        "sort_order": 1,
    },
    {
        "code": "12",
        "label": "12 - High School",
        "level_code": "FOUNDATIONAL",
        "sort_order": 2,
    },
    {
        "code": "13",
        "label": "13 - Foundation Year",
        "level_code": "FOUNDATIONAL",
        "sort_order": 3,
    },
    {
        "code": "14",
        "label": "14 - Associate / Diploma",
        "level_code": "UNDERGRAD",
        "sort_order": 4,
    },
    {
        "code": "15",
        "label": "15 - 3-Year Bachelor's",
        "level_code": "UNDERGRAD",
        "sort_order": 5,
    },
    {
        "code": "16",
        "label": "16 - 4-Year Bachelor's",
        "level_code": "UNDERGRAD",
        "sort_order": 6,
    },
    {
        "code": "17+",
        "label": "17+ - Master's / Postgraduate",
        "level_code": "GRADUATE",
        "sort_order": 7,
    },
    {
        "code": "17+",
        "label": "17+ - Master's / Postgraduate",
        "level_code": "INTEGRATED",
        "sort_order": 7,
    },
    {
        "code": "18+",
        "label": "18+ - Doctoral / Research",
        "level_code": "DOCTORAL",
        "sort_order": 8,
    },
    {
        "code": "18+",
        "label": "18+ - Doctoral / Research",
        "level_code": "INTEGRATED",
        "sort_order": 8,
    },
]

VALID_FULL_TIME_STUDY_YEAR_CODES = {str(item["code"]) for item in DEFAULT_FULL_TIME_STUDY_YEARS}


def normalize_full_time_study_years(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def list_active_full_time_study_years(
    db: Session,
    *,
    level_id: int | None = None,
) -> list[FullTimeStudyYear]:
    q = (
        db.query(FullTimeStudyYear)
        .options(joinedload(FullTimeStudyYear.level))
        .filter(FullTimeStudyYear.is_active.is_(True))
        .order_by(FullTimeStudyYear.sort_order.asc(), FullTimeStudyYear.code.asc())
    )
    if level_id is not None:
        q = q.filter(FullTimeStudyYear.level_id == level_id)
    return q.all()


def get_full_time_study_year_by_code(
    db: Session,
    code: str,
    *,
    level_id: int | None = None,
) -> FullTimeStudyYear | None:
    normalized = normalize_full_time_study_years(code)
    if not normalized:
        return None
    q = (
        db.query(FullTimeStudyYear)
        .options(joinedload(FullTimeStudyYear.level))
        .filter(
            FullTimeStudyYear.code == normalized,
            FullTimeStudyYear.is_active.is_(True),
        )
    )
    if level_id is not None:
        q = q.filter(FullTimeStudyYear.level_id == level_id)
    return q.order_by(FullTimeStudyYear.sort_order.asc(), FullTimeStudyYear.id.asc()).first()


def require_full_time_study_years(
    db: Session,
    code: str | None,
    *,
    level_id: int | None = None,
) -> FullTimeStudyYear:
    normalized = normalize_full_time_study_years(code)
    if not normalized:
        raise HTTPException(status_code=400, detail="Full-Time Study Years is required.")
    record = get_full_time_study_year_by_code(db, normalized, level_id=level_id)
    if not record:
        raise HTTPException(status_code=400, detail="Select a valid Full-Time Study Years option.")
    if level_id is not None and record.level_id != level_id:
        raise HTTPException(
            status_code=400,
            detail="Selected Full-Time Study Years does not belong to the chosen level.",
        )
    return record
