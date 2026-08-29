import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lead import Lead, get_dashboard_metrics
from app.services.conversation_audit_service import get_pending_advisor_questions

logger = logging.getLogger(__name__)

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

    # Optional side panels must not take down the whole home dashboard
    # (e.g. schema drift on Institution columns used only by calendar alerts).
    calendar_alerts: list = []
    try:
        from app.services.hierarchical_intake_service import list_calendar_intake_alerts

        calendar_alerts = list_calendar_intake_alerts(db, limit=10)
    except Exception:
        logger.exception("dashboard/summary: calendar intake alerts unavailable")
        db.rollback()

    pending_advisor_questions: list = []
    try:
        pending_advisor_questions = get_pending_advisor_questions(db, limit=10)
    except Exception:
        logger.exception("dashboard/summary: pending advisor questions unavailable")
        db.rollback()

    return {
        **metrics,
        # Backward-compatible alias for existing frontend consumers
        "missing_audit_count": metrics["missing_post_audit"],
        "notifications": notifications,
        "calendar_alerts": [alert.model_dump() for alert in calendar_alerts],
        "leads": [_map_lead_for_dashboard(lead) for lead in pipeline_leads],
        "pending_advisor_questions": pending_advisor_questions,
    }
