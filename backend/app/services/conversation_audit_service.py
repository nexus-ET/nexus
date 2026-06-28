from __future__ import annotations

import math
from typing import Any

from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session

from app.models.conversation_audit_log import ConversationAuditLog
from app.models.lead import Lead

ALLOWED_SORT_FIELDS = {"created_at", "confidence_score"}
ALLOWED_ORDERS = {"asc", "desc"}
ALLOWED_STATUS_FILTERS = {"all", "escalated", "ai_active", None, ""}


def log_ai_interaction(
    db: Session,
    *,
    lead_id: int,
    student_message: str,
    ai_reply: str,
    ai_model: str,
    confidence_score: float | None,
    escalated: bool,
    commit: bool = True,
) -> ConversationAuditLog:
    """Persist one AI conversation turn for the Agent Console audit dashboard."""
    entry = ConversationAuditLog(
        lead_id=lead_id,
        student_message=(student_message or "").strip(),
        ai_reply=(ai_reply or "").strip(),
        ai_model=(ai_model or "").strip(),
        confidence_score=confidence_score,
        escalated=bool(escalated),
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry


def _apply_audit_log_filters(
    query,
    *,
    search: str | None,
    status: str | None,
    ai_model: str | None,
):
    normalized_status = (status or "all").strip().lower()
    if normalized_status not in ALLOWED_STATUS_FILTERS:
        normalized_status = "all"
    if normalized_status == "escalated":
        query = query.filter(ConversationAuditLog.escalated.is_(True))
    elif normalized_status == "ai_active":
        query = query.filter(ConversationAuditLog.escalated.is_(False))

    if ai_model and ai_model.strip().lower() not in {"all", ""}:
        query = query.filter(ConversationAuditLog.ai_model == ai_model.strip())

    cleaned_search = (search or "").strip()
    if cleaned_search:
        pattern = f"%{cleaned_search}%"
        query = query.outerjoin(Lead, Lead.id == ConversationAuditLog.lead_id).filter(
            or_(
                ConversationAuditLog.student_message.ilike(pattern),
                ConversationAuditLog.ai_reply.ilike(pattern),
                Lead.full_name.ilike(pattern),
            )
        )

    return query, normalized_status


def list_conversation_audit_candidates(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
    ai_model: str | None = None,
) -> dict[str, Any]:
    """One summary row per candidate (lead) for the Audit Dashboard."""
    filtered, normalized_status = _apply_audit_log_filters(
        db.query(ConversationAuditLog),
        search=search,
        status=status,
        ai_model=ai_model,
    )

    grouped = filtered.with_entities(
        ConversationAuditLog.lead_id.label("lead_id"),
        func.count(ConversationAuditLog.id).label("turn_count"),
        func.max(ConversationAuditLog.created_at).label("last_activity_at"),
        func.bool_or(ConversationAuditLog.escalated).label("has_escalated"),
        func.max(ConversationAuditLog.id).label("latest_audit_id"),
    ).group_by(ConversationAuditLog.lead_id)

    if normalized_status == "escalated":
        grouped = grouped.having(func.bool_or(ConversationAuditLog.escalated).is_(True))
    elif normalized_status == "ai_active":
        grouped = grouped.having(func.bool_or(ConversationAuditLog.escalated).is_(False))

    grouped_sub = grouped.subquery()
    total = db.query(func.count()).select_from(grouped_sub).scalar() or 0

    sort_field = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    sort_order = order.lower() if order.lower() in ALLOWED_ORDERS else "desc"
    if sort_field == "confidence_score":
        sort_expr = ConversationAuditLog.confidence_score
    else:
        sort_expr = grouped_sub.c.last_activity_at
    ordering = desc(sort_expr) if sort_order == "desc" else asc(sort_expr)

    offset = (page - 1) * page_size
    rows = (
        db.query(ConversationAuditLog, Lead, grouped_sub.c.turn_count, grouped_sub.c.has_escalated)
        .join(grouped_sub, grouped_sub.c.latest_audit_id == ConversationAuditLog.id)
        .join(Lead, Lead.id == ConversationAuditLog.lead_id)
        .order_by(ordering, desc(grouped_sub.c.last_activity_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "lead_id": audit.lead_id,
            "student_name": lead.full_name,
            "turn_count": int(turn_count or 0),
            "latest_student_message": audit.student_message,
            "latest_ai_reply": audit.ai_reply,
            "latest_ai_model": audit.ai_model,
            "latest_confidence_score": audit.confidence_score,
            "latest_escalated": audit.escalated,
            "has_escalated": bool(has_escalated),
            "last_activity_at": audit.created_at,
        }
        for audit, lead, turn_count, has_escalated in rows
    ]

    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def list_audit_turns_for_lead(
    db: Session,
    lead_id: int,
    *,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Full AI turn history for one candidate, oldest first."""
    query = (
        db.query(ConversationAuditLog)
        .filter(ConversationAuditLog.lead_id == lead_id)
        .order_by(ConversationAuditLog.created_at.asc(), ConversationAuditLog.id.asc())
    )
    total = query.order_by(None).count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def list_conversation_audit_logs(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
    ai_model: str | None = None,
) -> dict[str, Any]:
    query = db.query(ConversationAuditLog)

    normalized_status = (status or "all").strip().lower()
    if normalized_status not in ALLOWED_STATUS_FILTERS:
        normalized_status = "all"
    if normalized_status == "escalated":
        query = query.filter(ConversationAuditLog.escalated.is_(True))
    elif normalized_status == "ai_active":
        query = query.filter(ConversationAuditLog.escalated.is_(False))

    if ai_model and ai_model.strip().lower() not in {"all", ""}:
        query = query.filter(ConversationAuditLog.ai_model == ai_model.strip())

    cleaned_search = (search or "").strip()
    if cleaned_search:
        pattern = f"%{cleaned_search}%"
        query = query.filter(
            or_(
                ConversationAuditLog.student_message.ilike(pattern),
                ConversationAuditLog.ai_reply.ilike(pattern),
            )
        )

    total = query.order_by(None).count()

    sort_field = sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at"
    sort_order = order.lower() if order.lower() in ALLOWED_ORDERS else "desc"
    sort_column = getattr(ConversationAuditLog, sort_field)
    ordering = desc(sort_column) if sort_order == "desc" else asc(sort_column)
    if sort_field == "confidence_score":
        query = query.order_by(ordering, desc(ConversationAuditLog.created_at))
    else:
        query = query.order_by(ordering)

    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def list_distinct_audit_models(db: Session) -> list[str]:
    rows = (
        db.query(ConversationAuditLog.ai_model)
        .filter(ConversationAuditLog.ai_model.isnot(None))
        .filter(ConversationAuditLog.ai_model != "")
        .distinct()
        .order_by(ConversationAuditLog.ai_model.asc())
        .all()
    )
    return [row[0] for row in rows if row[0]]


def get_pending_advisor_questions(db: Session, *, limit: int = 10) -> list[dict[str, object]]:
    """Latest escalated student questions that still need an admissions officer response."""
    from sqlalchemy import cast, String

    from app.models.lead import Lead

    rows = (
        db.query(ConversationAuditLog, Lead)
        .join(Lead, Lead.id == ConversationAuditLog.lead_id)
        .filter(ConversationAuditLog.escalated.is_(True))
        .filter(cast(Lead.stage, String).ilike("%HANDOFF%"))
        .filter(cast(Lead.stage, String).not_ilike("%ARCHIVE%"))
        .order_by(ConversationAuditLog.created_at.desc())
        .limit(max(limit * 5, 25))
        .all()
    )

    seen_leads: set[int] = set()
    pending: list[dict[str, object]] = []
    for audit, lead in rows:
        if audit.lead_id in seen_leads:
            continue
        seen_leads.add(audit.lead_id)
        pending.append(
            {
                "audit_id": audit.id,
                "lead_id": lead.id,
                "student_name": lead.full_name,
                "question": audit.student_message,
                "ai_reply": audit.ai_reply,
                "ai_model": audit.ai_model,
                "confidence_score": audit.confidence_score,
                "escalated": audit.escalated,
                "created_at": audit.created_at.isoformat() if audit.created_at else None,
                "link_path": "/handoffs",
            }
        )
        if len(pending) >= limit:
            break
    return pending
