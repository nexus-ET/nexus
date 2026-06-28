from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.country import CountryRead
from app.services.countries import list_active_countries

router = APIRouter()


@router.get("/countries", response_model=list[CountryRead])
@router.get("/countries/", response_model=list[CountryRead])
def get_countries(db: Session = Depends(get_db)):
    """List active countries with ISO codes and phone dial codes."""
    return list_active_countries(db)
