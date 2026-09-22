from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.utils.timezone import utc_now

from sqlalchemy import String, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadSource, LeadStage
from app.models.message import Message
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


def _normalize_contact_status(contact_status: str | None) -> str:
    raw = (contact_status or "all").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"started", "chat_started", "contacted", "active"}:
        return "started"
    if raw in {"not_started", "not_contacted", "pending", "new"}:
        return "not_started"
    return "all"


def _apply_prospect_filters(
    query,
    *,
    q: str | None,
    source: str | None,
    date_from: date | None,
    date_to: date | None,
    stage: str | None,
    category: str | None = None,
    contact_status: str | None = None,
):
    term = (q or "").strip()
    # Name/email/phone search must work across pipeline stages. Stage category is
    # only for empty-browse queues (e.g. Document Readiness → Documentation).
    # Ignore category when q is set so older clients that still send both still match.
    searching = bool(term)
    if searching:
        pattern = f"%{term}%"
        filters = [
            Lead.full_name.ilike(pattern),
            Lead.email.ilike(pattern),
            Lead.phone_number.ilike(pattern),
        ]
        if term.isdigit():
            try:
                filters.append(Lead.id == int(term))
            except ValueError:
                pass
        query = query.filter(or_(*filters))

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
    if (
        not searching
        and normalized_category
        and normalized_category.upper() != "ALL"
    ):
        categories = [part.strip() for part in normalized_category.split(",") if part.strip()]
        query = query.join(
            StatusDefinition,
            Lead.status_definition_id == StatusDefinition.id,
        )
        if len(categories) == 1:
            query = query.filter(StatusDefinition.category == categories[0])
        elif categories:
            query = query.filter(StatusDefinition.category.in_(categories))

    status = _normalize_contact_status(contact_status)
    if status != "all":
        has_any_message = exists().where(Message.lead_id == Lead.id)
        if status == "started":
            query = query.filter(has_any_message)
        else:
            query = query.filter(~has_any_message)

    return query


def _load_prospect_message_stats(db: Session, lead_ids: list[int]) -> dict[int, dict]:
    if not lead_ids:
        return {}

    rows = (
        db.query(
            Message.lead_id,
            func.count()
            .filter(Message.sender.in_(["student", "candidate"]))
            .label("total_received"),
            func.count()
            .filter(
                Message.sender.in_(["student", "candidate"]),
                Message.is_read.is_(False),
            )
            .label("unread_count"),
            func.max(Message.created_at).label("latest_msg_at"),
            func.count()
            .filter(Message.sender.in_(["advisor", "system"]))
            .label("ai_msg_count"),
            func.count().label("msg_count"),
        )
        .filter(Message.lead_id.in_(lead_ids))
        .group_by(Message.lead_id)
        .all()
    )

    return {
        row.lead_id: {
            "total_messages_received": int(row.total_received or 0),
            "unread_count": int(row.unread_count or 0),
            "latest_interaction_time": (
                row.latest_msg_at.isoformat() if row.latest_msg_at else None
            ),
            "has_ai_messages": int(row.ai_msg_count or 0) > 0,
            "has_messages": int(row.msg_count or 0) > 0,
        }
        for row in rows
    }


def build_prospect_list_item(
    lead: Lead,
    db: Session | None = None,
    *,
    active_booking=None,
    message_stats: dict | None = None,
    counsellor_name: str | None = None,
    skip_booking_lookup: bool = False,
) -> dict:
    from app.services.admissions_intake_flow import build_intake_profile_summary

    received_at = lead.created_at or lead.updated_at
    updated_at = lead.updated_at or lead.created_at
    stats = message_stats or {}
    latest_interaction = stats.get("latest_interaction_time")
    intake = {
        key: value
        for key, value in build_intake_profile_summary(
            lead,
            db,
            refresh_lead=False,
            include_booking_options=False,
            include_session_fields=True,
            active_booking=active_booking,
            counsellor_name=counsellor_name,
            skip_booking_lookup=skip_booking_lookup,
        ).items()
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
        # Only real chat activity — never fall back to lead.updated_at here,
        # or "Recently replied" treats never-contacted leads as replies.
        "latest_interaction_time": latest_interaction,
        "total_messages_received": int(stats.get("total_messages_received") or 0),
        "unread_count": int(stats.get("unread_count") or 0),
        "has_ai_messages": bool(stats.get("has_ai_messages")),
        "has_messages": bool(stats.get("has_messages")),
        **intake,
    }


def list_prospects_keyset(
    db: Session,
    *,
    limit: int = 50,
    cursor: str | None = None,
    offset: int = 0,
    q: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    stage: str | None = None,
    category: str | None = None,
    contact_status: str | None = None,
) -> dict:
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    searching = bool((q or "").strip())
    query = db.query(Lead)
    query = _apply_prospect_filters(
        query,
        q=q,
        source=source,
        date_from=date_from,
        date_to=date_to,
        stage=stage,
        category=category,
        contact_status=contact_status,
    )

    # Cheap COUNT(id) — avoid SQLAlchemy's default count(*) over a full-column subquery.
    filtered_total = int(query.with_entities(func.count(Lead.id)).order_by(None).scalar() or 0)

    if searching:
        # Name search: skip message ranking; lead recency is enough and index-friendly.
        ordered = query.order_by(
            Lead.updated_at.desc(),
            Lead.created_at.desc(),
            Lead.id.desc(),
        )
    else:
        # One aggregated join instead of per-row EXISTS / MAX(messages) subqueries.
        msg_stats = (
            select(
                Message.lead_id.label("lead_id"),
                func.max(Message.created_at).label("latest_msg_at"),
            )
            .group_by(Message.lead_id)
            .subquery()
        )
        contacted_rank = case((msg_stats.c.lead_id.isnot(None), 0), else_=1)
        ordered = (
            query.outerjoin(msg_stats, msg_stats.c.lead_id == Lead.id)
            .order_by(
                contacted_rank.asc(),
                msg_stats.c.latest_msg_at.desc().nulls_last(),
                Lead.updated_at.desc(),
                Lead.created_at.desc(),
                Lead.id.desc(),
            )
        )

    # Offset pagination takes precedence for page-based UI; cursor remains for legacy callers.
    if safe_offset > 0 or not cursor:
        page_rows = ordered.offset(safe_offset).limit(safe_limit).all()
        has_more = (safe_offset + len(page_rows)) < filtered_total
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            anchor_time = last.created_at or utc_now()
            next_cursor = encode_prospect_cursor(anchor_time, last.id)
    else:
        cursor_ts, cursor_id = decode_prospect_cursor(cursor)
        cursor_q = ordered.filter(
            or_(
                Lead.created_at < cursor_ts,
                and_(Lead.created_at == cursor_ts, Lead.id < cursor_id),
            )
        )
        rows = cursor_q.limit(safe_limit + 1).all()
        has_more = len(rows) > safe_limit
        page_rows = rows[:safe_limit]
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            anchor_time = last.created_at or utc_now()
            next_cursor = encode_prospect_cursor(anchor_time, last.id)

    from app.models.user import User
    from app.services.admissions_intake_flow import _load_active_consultation_bookings_map
    from app.services.counselling_service import _format_admin_name

    page_ids = [row.id for row in page_rows]
    bookings_by_lead = _load_active_consultation_bookings_map(db, page_ids)
    message_stats_by_id = _load_prospect_message_stats(db, page_ids)

    admin_ids = {
        int(booking.admin_id)
        for booking in bookings_by_lead.values()
        if getattr(booking, "admin_id", None) is not None
    }
    counsellor_by_admin_id: dict[int, str] = {}
    if admin_ids:
        for admin in db.query(User).filter(User.id.in_(admin_ids)).all():
            counsellor_by_admin_id[int(admin.id)] = _format_admin_name(admin)

    return {
        "items": [
            build_prospect_list_item(
                row,
                db,
                active_booking=bookings_by_lead.get(row.id),
                message_stats=message_stats_by_id.get(row.id),
                counsellor_name=(
                    counsellor_by_admin_id.get(int(bookings_by_lead[row.id].admin_id))
                    if row.id in bookings_by_lead
                    and getattr(bookings_by_lead[row.id], "admin_id", None) is not None
                    else None
                ),
                skip_booking_lookup=True,
            )
            for row in page_rows
        ],
        "next_cursor": next_cursor,
        "filtered_total": filtered_total,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": has_more,
    }


def get_prospects_summary(db: Session) -> dict:
    today_start = datetime.combine(utc_now().date(), time.min, tzinfo=ZoneInfo("UTC"))
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
