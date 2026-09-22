from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.counselor_followup import CounselorFollowupLog, CounselorStatusMaster
from app.models.lead import Lead
from app.schemas.counselor_followup import CounselorFollowupCreate


_ACTION_ITEMS_SPLIT = re.compile(r"(?i)\bAction\s+Items\s*:\s*")


def _split_notes(points_discussed: str, action_items: str | None) -> tuple[str, str | None]:
    points = (points_discussed or "").strip()
    if not points:
        raise HTTPException(status_code=400, detail="Notes cannot be empty.")

    explicit_actions = (action_items or "").strip() or None
    if explicit_actions:
        return points, explicit_actions

    match = _ACTION_ITEMS_SPLIT.search(points)
    if not match:
        return points, None

    discussed = points[: match.start()].strip()
    actions = points[match.end() :].strip() or None
    # Keep "Points Discussed:" prefix tidy if present
    discussed = re.sub(r"(?i)^\s*Points\s+Discussed\s*:\s*", "Points Discussed: ", discussed).strip()
    if actions and not discussed:
        discussed = points
        actions = None
    return discussed or points, actions


def _serialize_followup(row: CounselorFollowupLog) -> dict[str, Any]:
    status = row.status
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "counselor_id": row.counselor_id,
        "status_id": row.status_id,
        "status_key": status.status_key if status else "",
        "status_heading": status.status_heading if status else "",
        "points_discussed": row.points_discussed,
        "action_items": row.action_items,
        "target_completion_date": row.target_completion_date,
        "created_at": row.created_at,
    }


def list_counselor_statuses(db: Session, *, active_only: bool = True) -> list[dict[str, Any]]:
    query = db.query(CounselorStatusMaster)
    if active_only:
        query = query.filter(CounselorStatusMaster.is_active.is_(True))
    rows = query.order_by(
        CounselorStatusMaster.sort_order.asc(),
        CounselorStatusMaster.status_heading.asc(),
    ).all()
    return [
        {
            "id": row.id,
            "status_key": row.status_key,
            "status_heading": row.status_heading,
            "default_description": row.default_description,
            "is_active": row.is_active,
            "sort_order": row.sort_order,
        }
        for row in rows
    ]


def list_lead_followups(db: Session, lead_id: int) -> dict[str, Any]:
    lead = db.query(Lead.id).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    rows = (
        db.query(CounselorFollowupLog)
        .options(joinedload(CounselorFollowupLog.status))
        .filter(CounselorFollowupLog.lead_id == lead_id)
        .order_by(CounselorFollowupLog.created_at.desc(), CounselorFollowupLog.id.desc())
        .all()
    )
    items = [_serialize_followup(row) for row in rows]
    return {"items": items, "total": len(items)}


def create_lead_followup(
    db: Session,
    lead_id: int,
    payload: CounselorFollowupCreate,
    *,
    counselor_id: str | None = None,
) -> dict[str, Any]:
    lead = db.query(Lead.id).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    status = (
        db.query(CounselorStatusMaster)
        .filter(
            CounselorStatusMaster.id == payload.status_id,
            CounselorStatusMaster.is_active.is_(True),
        )
        .first()
    )
    if not status:
        raise HTTPException(status_code=400, detail="Select a valid follow-up status.")

    points, actions = _split_notes(payload.points_discussed, payload.action_items)
    followup_date = payload.target_completion_date
    today = date.today()

    if followup_date is not None and followup_date < today:
        raise HTTPException(
            status_code=400,
            detail="Next Follow-up Date cannot be in the past.",
        )
    if actions and followup_date is None:
        raise HTTPException(
            status_code=400,
            detail="Select a Next Follow-up Date (today or a future date) when Action Items are set.",
        )

    row = CounselorFollowupLog(
        lead_id=lead_id,
        counselor_id=(counselor_id or "").strip() or None,
        status_id=status.id,
        points_discussed=points,
        action_items=actions,
        target_completion_date=followup_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    # Ensure status relationship is loaded for serialization
    row = (
        db.query(CounselorFollowupLog)
        .options(joinedload(CounselorFollowupLog.status))
        .filter(CounselorFollowupLog.id == row.id)
        .one()
    )
    return _serialize_followup(row)


def count_followups_for_lead_ids(db: Session, lead_ids: list[int]) -> dict[int, int]:
    if not lead_ids:
        return {}
    rows = (
        db.query(CounselorFollowupLog.lead_id, func.count(CounselorFollowupLog.id))
        .filter(CounselorFollowupLog.lead_id.in_(lead_ids))
        .group_by(CounselorFollowupLog.lead_id)
        .all()
    )
    return {int(lead_id): int(count) for lead_id, count in rows if lead_id is not None}
