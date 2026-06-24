from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lead import get_dashboard_metrics
from app.services.analytics_insights import explain_chart_trend
from app.services.analytics_trends import build_trends_payload

router = APIRouter()


class ExplainChartRequest(BaseModel):
    chart_type: Literal["funnel", "channel", "ai_efficacy", "velocity"]
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/summary")
async def get_analytics_summary(db: Session = Depends(get_db)):
    """
    Real-time operational metrics for the dashboard home page.
    Historical/strategic analytics live under /trends instead.
    """
    metrics = get_dashboard_metrics(db)
    return {
        "awaiting_consultation": metrics["awaiting_consultation"],
        "escalation_count": metrics["escalation_queue"],
        "escalation_queue": metrics["escalation_queue"],
        "missing_audit_count": metrics["missing_post_audit"],
        "missing_post_audit": metrics["missing_post_audit"],
        "active_ai_chats": metrics["active_ai_chats"],
    }


@router.get("/trends")
@router.get("/trends/")
async def get_analytics_trends(
    channel: Optional[str] = Query(default="All", description="All, WhatsApp, Instagram, or Web"),
    funnel_weeks: int = Query(default=8, ge=4, le=26),
    channel_days: int = Query(default=90, ge=30, le=365),
    ai_weeks: int = Query(default=12, ge=4, le=52),
    db: Session = Depends(get_db),
):
    """
    Historical and strategic analytics for the Analytical Dashboard.
    """
    return build_trends_payload(
        db,
        channel=None if channel == "All" else channel,
        funnel_weeks=funnel_weeks,
        channel_days=channel_days,
        ai_weeks=ai_weeks,
    )


@router.post("/explain")
@router.post("/explain/")
async def explain_analytics_chart(payload: ExplainChartRequest):
    return await explain_chart_trend(payload.chart_type, payload.data)
