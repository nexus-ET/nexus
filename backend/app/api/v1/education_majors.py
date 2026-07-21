from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.education_major import EducationMajorRead
from app.services.education_majors import list_active_education_majors

router = APIRouter()


@router.get("/education-majors", response_model=list[EducationMajorRead])
@router.get("/education-majors/", response_model=list[EducationMajorRead])
def get_education_majors(db: Session = Depends(get_db)):
    """List active education major options for academic history forms."""
    return list_active_education_majors(db)
