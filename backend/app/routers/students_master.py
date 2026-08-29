"""Students Master API — Invoice Workspace and profile lookups."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.students_master import (
    StudentMasterInvoiceHit,
    StudentMasterInvoiceSearchResponse,
)
from app.services.students_master_service import search_students_master_for_invoice

router = APIRouter(prefix="/students-master", tags=["Students Master"])


@router.get("/search", response_model=StudentMasterInvoiceSearchResponse)
@router.get("/search/", response_model=StudentMasterInvoiceSearchResponse)
def search_students_master(
    q: str | None = Query(default=None, description="Name, email, phone, id, or city/state"),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _current_user: User = Depends(deps.get_current_user),
):
    items = search_students_master_for_invoice(db, q=q, limit=limit)
    return StudentMasterInvoiceSearchResponse(
        items=[StudentMasterInvoiceHit.model_validate(row) for row in items],
        total=len(items),
    )
