from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.education_degree import EducationDegreeRead
from app.services.education_degrees import list_active_education_degrees

router = APIRouter()


@router.get("/education-degrees", response_model=list[EducationDegreeRead])
@router.get("/education-degrees/", response_model=list[EducationDegreeRead])
def get_education_degrees(db: Session = Depends(get_db)):
    """List active education degree options for lead intake forms."""
    return list_active_education_degrees(db)
