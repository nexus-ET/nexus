from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.qualification_program import (
    QualificationProgramMajorRead,
    QualificationProgramRead,
)
from app.services.qualification_programs import list_active_qualification_programs

router = APIRouter()


def _program_majors(row) -> list[QualificationProgramMajorRead]:
    mappings = getattr(row, "education_major_mappings", None) or []
    majors: list[QualificationProgramMajorRead] = []
    seen: set[int] = set()
    for mapping in mappings:
        major = getattr(mapping, "education_major", None)
        if not major or not major.is_active or major.id in seen:
            continue
        seen.add(major.id)
        majors.append(
            QualificationProgramMajorRead(
                id=major.id,
                code=major.code,
                label=major.label,
            )
        )
    majors.sort(key=lambda item: ((item.label or "").lower(), item.id))
    return majors


def _program_read(row) -> QualificationProgramRead:
    level = row.level
    return QualificationProgramRead(
        id=row.id,
        code=row.code,
        name=row.name,
        label=row.name,
        level_id=row.level_id,
        level_code=level.code if level else None,
        level_name=level.name if level else None,
        program_url=getattr(row, "program_url", None),
        sort_order=row.sort_order or 0,
        majors=_program_majors(row),
    )


@router.get("/programs", response_model=list[QualificationProgramRead])
@router.get("/programs/", response_model=list[QualificationProgramRead])
def get_qualification_programs(
    db: Session = Depends(get_db),
    level_id: int | None = Query(None, ge=1),
):
    """List active framework qualification programs, optionally filtered by level."""
    rows = list_active_qualification_programs(db, level_id=level_id)
    return [_program_read(row) for row in rows]
