from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.gpa_cgpa_score import GpaCgpaScoreRead
from app.services.gpa_cgpa_scores import list_active_gpa_cgpa_scores

router = APIRouter()


@router.get("/gpa-cgpa-scores", response_model=list[GpaCgpaScoreRead])
@router.get("/gpa-cgpa-scores/", response_model=list[GpaCgpaScoreRead])
def get_gpa_cgpa_scores(db: Session = Depends(get_db)):
    """List active GPA/CGPA score options for lead intake forms."""
    return list_active_gpa_cgpa_scores(db)
