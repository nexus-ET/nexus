from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session



from app.db.database import get_db

from app.schemas.level import LevelRead

from app.schemas.education_degree import EducationDegreeRead

from app.services import levels as level_service

from app.services.education_degrees import list_active_education_degrees



router = APIRouter()





def _education_degree_read(row) -> EducationDegreeRead:

    level = row.level

    return EducationDegreeRead(

        id=row.id,

        level_id=row.level_id,

        level_code=level.code if level else None,

        level_name=level.name if level else None,

        code=row.code,

        label=row.label,

        is_other=row.is_other,

        sort_order=row.sort_order,

    )





@router.get("/levels", response_model=list[LevelRead])

@router.get("/levels/", response_model=list[LevelRead])

def get_levels(db: Session = Depends(get_db)):

    return level_service.list_levels(db)





@router.get("/education-degrees", response_model=list[EducationDegreeRead])

@router.get("/education-degrees/", response_model=list[EducationDegreeRead])

def get_education_degrees(

    db: Session = Depends(get_db),

    level_id: int | None = Query(None, ge=1),

    level_code: str | None = Query(None, max_length=50),

):

    rows = list_active_education_degrees(

        db,

        level_id=level_id,

        level_code=level_code,

    )

    return [_education_degree_read(row) for row in rows]

