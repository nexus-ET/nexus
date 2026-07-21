from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadSource, LeadStage
from app.models.status_definition import StatusDefinition


def resolve_platform_badge(lead: Lead) -> str | None:
    source = (getattr(lead, "source", None) or "").upper()
    channel = lead.channel

    if source == LeadSource.INSTAGRAM_LEAD.value or channel == LeadChannel.INSTAGRAM:
        return "IG"
    if source == LeadSource.FACEBOOK_LEAD.value or channel == LeadChannel.FACEBOOK:
        return "FB"
    return None


def encode_prospect_cursor(created_at: datetime, lead_id: int) -> str:
    ts = created_at.isoformat()
    return f"{ts}|{lead_id}"


def decode_prospect_cursor(cursor: str) -> tuple[datetime, int]:
    if "|" not in cursor:
        raise ValueError("Invalid cursor.")
    ts_raw, lead_id_raw = cursor.rsplit("|", 1)
    parsed_ts = datetime.fromisoformat(ts_raw)
    return parsed_ts, int(lead_id_raw)


def _apply_prospect_filters(
    query,
    *,
    q: str | None,
    source: str | None,
    date_from: date | None,
    date_to: date | None,
    stage: str | None,
    category: str | None = None,
):
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Lead.full_name.ilike(term),
                Lead.email.ilike(term),
                Lead.phone_number.ilike(term),
            )
        )

    normalized_source = (source or "").strip().upper()
    if normalized_source and normalized_source not in {"ALL", ""}:
        if normalized_source in {LeadSource.FACEBOOK_LEAD.value, "FACEBOOK", "FB"}:
            query = query.filter(
                or_(
                    Lead.source == LeadSource.FACEBOOK_LEAD.value,
                    Lead.channel == LeadChannel.FACEBOOK,
                )
            )
        elif normalized_source in {LeadSource.INSTAGRAM_LEAD.value, "INSTAGRAM", "IG"}:
            query = query.filter(
                or_(
                    Lead.source == LeadSource.INSTAGRAM_LEAD.value,
                    Lead.channel == LeadChannel.INSTAGRAM,
                )
            )
        elif normalized_source == "WHATSAPP":
            query = query.filter(Lead.channel == LeadChannel.WHATSAPP)
        else:
            query = query.filter(Lead.source == normalized_source)

    if date_from:
        start = datetime.combine(date_from, time.min)
        query = query.filter(Lead.created_at >= start)
    if date_to:
        end = datetime.combine(date_to, time.max)
        query = query.filter(Lead.created_at <= end)

    if stage and stage.upper() != "ALL":
        query = query.filter(cast(Lead.stage, String).ilike(f"%{stage.upper()}%"))

    normalized_category = (category or "").strip()
    if normalized_category and normalized_category.upper() != "ALL":
        query = query.join(
            StatusDefinition,
            Lead.status_definition_id == StatusDefinition.id,
        ).filter(StatusDefinition.category == normalized_category)

    return query


def build_prospect_list_item(lead: Lead) -> dict:
    from app.services.admissions_intake_flow import build_intake_profile_summary

    received_at = lead.created_at or lead.updated_at
    updated_at = lead.updated_at or lead.created_at
    intake = {
        key: value
        for key, value in build_intake_profile_summary(lead, db=None).items()
        if key
        not in {
            "available_consultation_dates",
            "available_consultation_times",
            "selected_consultation_date",
        }
    }
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "name": lead.full_name,
        "email": getattr(lead, "email", None) or "",
        "phone": getattr(lead, "phone_number", None),
        "phone_number": getattr(lead, "phone_number", None),
        "stage": lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage),
        "status": lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage),
        "source": getattr(lead, "source", None),
        "platform_badge": resolve_platform_badge(lead),
        "received_at": received_at.isoformat() if received_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "latest_interaction_time": updated_at.isoformat() if updated_at else None,
        **intake,
    }


def list_prospects_keyset(
    db: Session,
    *,
    limit: int = 50,
    cursor: str | None = None,
    q: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    stage: str | None = None,
    category: str | None = None,
) -> dict:
    safe_limit = max(1, min(limit, 100))
    query = db.query(Lead)
    query = _apply_prospect_filters(
        query,
        q=q,
        source=source,
        date_from=date_from,
        date_to=date_to,
        stage=stage,
        category=category,
    )

    filtered_total = query.count()

    query = query.order_by(Lead.created_at.desc(), Lead.id.desc())

    if cursor:
        cursor_ts, cursor_id = decode_prospect_cursor(cursor)
        query = query.filter(
            or_(
                Lead.created_at < cursor_ts,
                and_(Lead.created_at == cursor_ts, Lead.id < cursor_id),
            )
        )

    rows = query.limit(safe_limit + 1).all()
    has_more = len(rows) > safe_limit
    page_rows = rows[:safe_limit]

    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        anchor_time = last.created_at or datetime.now(timezone.utc).replace(tzinfo=None)
        next_cursor = encode_prospect_cursor(anchor_time, last.id)

    return {
        "items": [build_prospect_list_item(row) for row in page_rows],
        "next_cursor": next_cursor,
        "filtered_total": filtered_total,
    }


def get_prospects_summary(db: Session) -> dict:
    today_start = datetime.combine(datetime.utcnow().date(), time.min)
    total_leads = db.query(func.count(Lead.id)).scalar() or 0
    leads_today = (
        db.query(func.count(Lead.id)).filter(Lead.created_at >= today_start).scalar() or 0
    )
    pending_handoff = (
        db.query(func.count(Lead.id))
        .filter(
            or_(
                cast(Lead.stage, String).ilike("%HANDOFF%"),
                Lead.is_human_locked.is_(True),
            )
        )
        .scalar()
        or 0
    )
    meta_leads = (
        db.query(func.count(Lead.id)).filter(Lead.meta_leadgen_id.isnot(None)).scalar() or 0
    )
    return {
        "total_leads": total_leads,
        "leads_today": leads_today,
        "pending_handoff": pending_handoff,
        "meta_leads": meta_leads,
    }
