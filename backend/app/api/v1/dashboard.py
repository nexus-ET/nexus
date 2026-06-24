from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lead import Lead, get_dashboard_metrics

router = APIRouter()


def _normalize_stage(lead: Lead) -> str:
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    return stage.upper()


def _map_pipeline_status(lead: Lead) -> str:
    stage = _normalize_stage(lead)
    if stage == "ARCHIVE":
        return "CONVERTED"
    if stage == "HANDOFF" or lead.is_human_locked:
        return "QUALIFIED"
    return "NEEDS_AUDIT"


def _map_lead_for_dashboard(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "status": _map_pipeline_status(lead),
        "destination_country": lead.preferred_country or "Unassigned",
    }


@router.get("/summary")
@router.get("/summary/")
async def get_dashboard_summary(limit: int = 5, db: Session = Depends(get_db)):
    metrics = get_dashboard_metrics(db)

    sort_column = Lead.updated_at if hasattr(Lead, "updated_at") else Lead.created_at
    pipeline_leads = (
        db.query(Lead)
        .order_by(sort_column.desc())
        .limit(int(limit))
        .all()
    )

    notifications = [
        {
            "id": 1,
            "severity": "HIGH",
            "title": "High Intent Lead",
            "message": "Pipeline notification initialized.",
            "link_path": "/handoffs",
        }
    ] if metrics["escalation_queue"] > 0 else []

    return {
        **metrics,
        # Backward-compatible alias for existing frontend consumers
        "missing_audit_count": metrics["missing_post_audit"],
        "notifications": notifications,
        "leads": [_map_lead_for_dashboard(lead) for lead in pipeline_leads],
    }
