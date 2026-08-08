from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.full_time_study_year import FullTimeStudyYearRead
from app.services.full_time_study_years import list_active_full_time_study_years

router = APIRouter()


def _study_year_read(row) -> FullTimeStudyYearRead:
    level = row.level
    return FullTimeStudyYearRead(
        id=row.id,
        code=row.code,
        label=row.label,
        level_id=row.level_id,
        level_code=level.code if level else None,
        level_name=level.name if level else None,
        sort_order=row.sort_order,
    )


@router.get("/full-time-study-years", response_model=list[FullTimeStudyYearRead])
@router.get("/full-time-study-years/", response_model=list[FullTimeStudyYearRead])
def get_full_time_study_years(
    db: Session = Depends(get_db),
    level_id: int | None = Query(None, ge=1),
):
    """List active Full-Time Study Years options for counselling and lead forms."""
    rows = list_active_full_time_study_years(db, level_id=level_id)
    return [_study_year_read(row) for row in rows]
