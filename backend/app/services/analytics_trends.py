from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import cast, String, func
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadStage
from app.utils.timezone import utc_now


CHANNEL_LABELS = {
    LeadChannel.WHATSAPP.value: "WhatsApp",
    LeadChannel.INSTAGRAM.value: "Instagram",
    LeadChannel.FACEBOOK.value: "Facebook",
}

WEB_CHANNEL_VALUES = {
    LeadChannel.EMAIL.value,
    LeadChannel.GOOGLE_ADS.value,
    LeadChannel.OFFLINE.value,
}


def normalize_channel_label(channel: LeadChannel | str | None) -> str:
    raw = channel.value if hasattr(channel, "value") else str(channel or "")
    raw = raw.upper()
    if raw in CHANNEL_LABELS:
        return CHANNEL_LABELS[raw]
    return "Web"


def _channel_filter(channel: LeadChannel | str):
    label = normalize_channel_label(channel)
    if label == "WhatsApp":
        return cast(Lead.channel, String).ilike("%WHATSAPP%")
    if label == "Instagram":
        return cast(Lead.channel, String).ilike("%INSTAGRAM%")
    if label == "Facebook":
        return cast(Lead.channel, String).ilike("%FACEBOOK%")
    return cast(Lead.channel, String).in_(list(WEB_CHANNEL_VALUES))


def _apply_channel_filter(query, channel: Optional[str]):
    if not channel or channel.lower() == "all":
        return query
    normalized = channel.strip()
    if normalized not in {"WhatsApp", "Instagram", "Web"}:
        return query
    return query.filter(_channel_filter(normalized))


def _week_start(value: datetime) -> datetime:
    start = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=start.weekday())


def _is_enrolled(lead: Lead) -> bool:
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    return stage.upper() == LeadStage.ARCHIVE.value


def _close_timestamp(lead: Lead) -> Optional[datetime]:
    if lead.archived_at:
        return lead.archived_at
    if _is_enrolled(lead):
        return lead.updated_at or lead.created_at
    return None


def get_conversion_funnel_trends(
    db: Session,
    weeks: int = 8,
    channel: Optional[str] = None,
) -> dict:
    now = utc_now()
    current_week = _week_start(now)
    results = []

    for offset in range(weeks - 1, -1, -1):
        week_start = current_week - timedelta(weeks=offset)
        week_end = week_start + timedelta(days=7)

        inquiry_query = db.query(func.count(Lead.id)).filter(
            Lead.created_at >= week_start,
            Lead.created_at < week_end,
        )
        inquiry_query = _apply_channel_filter(inquiry_query, channel)
        inquiry_count = inquiry_query.scalar() or 0

        enrolled_query = db.query(Lead).filter(
            cast(Lead.stage, String).ilike(f"%{LeadStage.ARCHIVE.value}%"),
        )
        enrolled_query = _apply_channel_filter(enrolled_query, channel)
        enrolled_leads = enrolled_query.all()

        enrolled_count = 0
        for lead in enrolled_leads:
            closed_at = _close_timestamp(lead)
            if closed_at and week_start <= closed_at < week_end:
                enrolled_count += 1

        conversion_rate = round((enrolled_count / inquiry_count) * 100, 1) if inquiry_count else 0.0

        results.append(
            {
                "week_start": week_start.date().isoformat(),
                "week_label": week_start.strftime("%b %d"),
                "inquiry": inquiry_count,
                "enrolled": enrolled_count,
                "conversion_rate": conversion_rate,
            }
        )

    return {"weeks": results, "channel_filter": channel or "All"}


def get_channel_performance(
    db: Session,
    days: int = 90,
    channel: Optional[str] = None,
) -> dict:
    since = utc_now() - timedelta(days=days)
    channels = ["WhatsApp", "Instagram", "Web"]
    if channel and channel not in {"All", "all"} and channel in channels:
        channels = [channel]

    rows = []
    for label in channels:
        total_query = db.query(func.count(Lead.id)).filter(Lead.created_at >= since)
        total_query = _apply_channel_filter(total_query, label)
        total = total_query.scalar() or 0

        enrolled_query = db.query(Lead).filter(
            Lead.created_at >= since,
            cast(Lead.stage, String).ilike(f"%{LeadStage.ARCHIVE.value}%"),
        )
        enrolled_query = _apply_channel_filter(enrolled_query, label)
        enrolled = enrolled_query.count()

        conversion_rate = round((enrolled / total) * 100, 1) if total else 0.0
        rows.append(
            {
                "channel": label,
                "leads": total,
                "enrolled": enrolled,
                "conversion_rate": conversion_rate,
            }
        )

    return {"period_days": days, "channels": rows, "channel_filter": channel or "All"}


def get_ai_efficacy_trends(
    db: Session,
    weeks: int = 12,
    channel: Optional[str] = None,
) -> dict:
    now = utc_now()
    current_week = _week_start(now)
    points = []

    for offset in range(weeks - 1, -1, -1):
        week_start = current_week - timedelta(weeks=offset)
        week_end = week_start + timedelta(days=7)

        closed_query = db.query(Lead).filter(
            cast(Lead.stage, String).ilike(f"%{LeadStage.ARCHIVE.value}%"),
        )
        closed_query = _apply_channel_filter(closed_query, channel)
        closed_leads = closed_query.all()

        closed_count = 0
        ai_resolved_count = 0
        for lead in closed_leads:
            closed_at = _close_timestamp(lead)
            if not closed_at or not (week_start <= closed_at < week_end):
                continue
            closed_count += 1
            if not lead.is_human_locked:
                ai_resolved_count += 1

        resolution_rate = round((ai_resolved_count / closed_count) * 100, 1) if closed_count else 0.0
        points.append(
            {
                "week_start": week_start.date().isoformat(),
                "week_label": week_start.strftime("%b %d"),
                "closed_leads": closed_count,
                "ai_resolved": ai_resolved_count,
                "resolution_rate": resolution_rate,
            }
        )

    return {"weeks": points, "channel_filter": channel or "All"}


def get_lead_velocity(
    db: Session,
    channel: Optional[str] = None,
) -> dict:
    now = utc_now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_end = current_month_start
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

    def average_days_for_range(start: datetime, end: datetime) -> dict:
        query = db.query(Lead).filter(
            cast(Lead.stage, String).ilike(f"%{LeadStage.ARCHIVE.value}%"),
        )
        query = _apply_channel_filter(query, channel)
        leads = query.all()

        durations = []
        for lead in leads:
            closed_at = _close_timestamp(lead)
            if not closed_at or not lead.created_at:
                continue
            if start <= closed_at < end:
                durations.append((closed_at - lead.created_at).total_seconds() / 86400)

        avg_days = round(sum(durations) / len(durations), 1) if durations else 0.0
        return {"average_days": avg_days, "closed_leads": len(durations)}

    current = average_days_for_range(current_month_start, now + timedelta(days=1))
    previous = average_days_for_range(previous_month_start, previous_month_end)

    delta = round(current["average_days"] - previous["average_days"], 1)
    change_percent = (
        round((delta / previous["average_days"]) * 100, 1)
        if previous["average_days"]
        else 0.0
    )

    return {
        "current_month": {
            "label": current_month_start.strftime("%B %Y"),
            **current,
        },
        "previous_month": {
            "label": previous_month_start.strftime("%B %Y"),
            **previous,
        },
        "delta_days": delta,
        "change_percent": change_percent,
        "channel_filter": channel or "All",
    }


def build_trends_payload(
    db: Session,
    channel: Optional[str] = None,
    funnel_weeks: int = 8,
    channel_days: int = 90,
    ai_weeks: int = 12,
) -> dict:
    return {
        "generated_at": utc_now().isoformat(),
        "filters": {
            "channel": channel or "All",
            "funnel_weeks": funnel_weeks,
            "channel_days": channel_days,
            "ai_weeks": ai_weeks,
        },
        "conversion_funnel": get_conversion_funnel_trends(db, weeks=funnel_weeks, channel=channel),
        "channel_performance": get_channel_performance(db, days=channel_days, channel=channel),
        "ai_efficacy": get_ai_efficacy_trends(db, weeks=ai_weeks, channel=channel),
        "lead_velocity": get_lead_velocity(db, channel=channel),
    }
