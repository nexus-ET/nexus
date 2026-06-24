from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional

from app.db.database import get_db
from app.models.lead import Lead
# 🎯 Import your newly aligned schemas
from app.schemas.lead import LeadResponse, LeadStage, LeadUpdate 

router = APIRouter(prefix="", tags=["Leads"])

# 1. 🤖 VIEW: AI Active Queue
@router.get("/ai-active", response_model=List[LeadResponse])  # 👈 Added serialization model
def get_ai_active_leads(db: Session = Depends(get_db)):
    stmt = (
        select(Lead)
        .where(Lead.stage == LeadStage.AI_ACTIVE.value)
        .where(Lead.is_human_locked == False)
        .order_by(Lead.updated_at.desc())
    )
    return db.scalars(stmt).all()


# 2. 🔥 VIEW: Confirmed Handoffs
@router.get("/handoffs", response_model=List[LeadResponse])  # 👈 Added serialization model
def get_handoff_leads(db: Session = Depends(get_db)):
    stmt = (
        select(Lead)
        .where(Lead.stage == LeadStage.HANDOFF.value)
        .order_by(Lead.updated_at.asc())
    )
    return db.scalars(stmt).all()


# 3. 👥 VIEW: All Prospects Master Workbench
@router.get("/all", response_model=List[LeadResponse])  # 👈 Added serialization model
def get_all_prospects(
    country: Optional[str] = None,
    budget: Optional[str] = None,
    stage: Optional[LeadStage] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    stmt = select(Lead)
    
    if country:
        stmt = stmt.where(Lead.preferred_country.ilike(f"%{country}%"))
    if budget:
        stmt = stmt.where(Lead.budget_tier == budget)
    if stage:
        stmt = stmt.where(Lead.stage == stage.value)
    if search:
        stmt = stmt.where(
            Lead.full_name.ilike(f"%{search}%") | 
            Lead.email.ilike(f"%{search}%") | 
            Lead.phone_number.ilike(f"%{search}%")
        )
        
    stmt = stmt.order_by(Lead.ml_conversion_score.desc())
    return db.scalars(stmt).all()


# 4. 🗂️ VIEW: Archives Lifecycle
@router.get("/archive", response_model=List[LeadResponse])  # 👈 Added serialization model
def get_archived_leads(db: Session = Depends(get_db)):
    stmt = (
        select(Lead)
        .where(Lead.stage == LeadStage.ARCHIVE.value)
        .order_by(Lead.updated_at.desc())
    )
    return db.scalars(stmt).all()

# 5. 📊 VIEW: Dashboard Main Pipeline Bridge
@router.get("/pipeline", response_model=List[LeadResponse])
def get_dashboard_pipeline(limit: Optional[int] = 5, db: Session = Depends(get_db)):
    """
    Acts as a direct data feed for the frontend dashboard main data matrix table grid.
    """
    stmt = (
        select(Lead)
        .order_by(Lead.ml_conversion_score.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()

# 🛠️ INTERACTION: Counselor Human Override (Panic Button)
@router.post("/{lead_id}/override", response_model=LeadResponse)  # 👈 Return the updated lead object
def counselor_override(lead_id: int, db: Session = Depends(get_db)):
    stmt = select(Lead).where(Lead.id == lead_id)
    lead = db.scalars(stmt).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    lead.is_human_locked = True
    db.commit()
    db.refresh(lead)  # Refresh object state to match our response model mapping
    return lead

# Append this to the bottom of app/api/leads.py

@router.get("/pipeline", response_model=List[LeadResponse])
def get_dashboard_pipeline(limit: Optional[int] = 5, db: Session = Depends(get_db)):
    """
    Direct data bridge feeding the main dashboard metrics tables
    """
    stmt = (
        select(Lead)
        .order_by(Lead.ml_conversion_score.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()