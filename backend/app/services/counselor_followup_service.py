from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.counselor_followup import CounselorFollowupLog, CounselorStatusMaster
from app.models.lead import Lead
from app.models.user import User
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


def _parse_counselor_user_id(counselor_id: str | None) -> int | None:
    """counselor_id is stored as 'user_id' or 'user_id:email'."""
    raw = (counselor_id or "").strip()
    if not raw:
        return None
    head = raw.split(":", 1)[0].strip()
    if not head.isdigit():
        return None
    try:
        return int(head)
    except ValueError:
        return None


def _user_display_name(user: User | None) -> str | None:
    if not user:
        return None
    parts = [(user.first_name or "").strip(), (user.last_name or "").strip()]
    name = " ".join(part for part in parts if part)
    if name:
        return name
    email = (user.email or "").strip()
    return email or None


def _counselor_names_by_id(
    db: Session, counselor_ids: list[str | None]
) -> dict[int, str]:
    user_ids: set[int] = set()
    for cid in counselor_ids:
        uid = _parse_counselor_user_id(cid)
        if uid is not None:
            user_ids.add(uid)
    if not user_ids:
        return {}
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {
        int(user.id): name
        for user in users
        if (name := _user_display_name(user))
    }


def _serialize_followup(
    row: CounselorFollowupLog,
    *,
    counselor_name: str | None = None,
    email_sent: bool | None = None,
    email_error: str | None = None,
) -> dict[str, Any]:
    status = row.status
    documents = row.checklist_sent_documents
    if documents is not None and not isinstance(documents, list):
        documents = None
    payload: dict[str, Any] = {
        "id": row.id,
        "lead_id": row.lead_id,
        "counselor_id": row.counselor_id,
        "counselor_name": counselor_name,
        "status_id": row.status_id,
        "status_key": status.status_key if status else "",
        "status_heading": status.status_heading if status else "",
        "points_discussed": row.points_discussed,
        "action_items": row.action_items,
        "target_completion_date": row.target_completion_date,
        "created_at": row.created_at,
        "checklist_email_to": row.checklist_email_to,
        "checklist_email_sent_at": row.checklist_email_sent_at,
        "checklist_sent_documents": documents,
    }
    if email_sent is not None or email_error is not None:
        payload["email_sent"] = email_sent
        payload["email_error"] = email_error
    elif row.checklist_email_sent_at is not None:
        payload["email_sent"] = True
        payload["email_error"] = None
    return payload


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
    names = _counselor_names_by_id(db, [row.counselor_id for row in rows])
    items = []
    for row in rows:
        uid = _parse_counselor_user_id(row.counselor_id)
        items.append(
            _serialize_followup(
                row,
                counselor_name=names.get(uid) if uid is not None else None,
            )
        )
    return {"items": items, "total": len(items)}


def _is_send_document_checklist_status(status: CounselorStatusMaster) -> bool:
    key = (status.status_key or "").strip().lower()
    if key == "send_document_checklist":
        return True
    heading = (status.status_heading or "").strip().lower()
    return heading == "send document checklist"


def create_lead_followup(
    db: Session,
    lead_id: int,
    payload: CounselorFollowupCreate,
    *,
    counselor_id: str | None = None,
    current_user: User | None = None,
) -> dict[str, Any]:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
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

    send_checklist_email = bool(payload.send_document_checklist_email)
    checklist_level: str | None = None
    checklist_scope: str | None = None
    checklist_country_id: int | None = None

    if send_checklist_email:
        if not _is_send_document_checklist_status(status):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Document checklist email can only be sent when the follow-up "
                    "status is Send Document Checklist."
                ),
            )
        from app.services.document_checklist_email_service import (
            validate_checklist_email_selection,
        )

        checklist_level, checklist_scope, checklist_country_id = (
            validate_checklist_email_selection(
                db,
                program_level=payload.checklist_program_level,
                scope=payload.checklist_scope,
                country_id=payload.checklist_country_id,
            )
        )

    stored_counselor_id = (counselor_id or "").strip() or None
    row = CounselorFollowupLog(
        lead_id=lead_id,
        counselor_id=stored_counselor_id,
        status_id=status.id,
        points_discussed=points,
        action_items=actions,
        target_completion_date=followup_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    email_sent: bool | None = None
    email_error: str | None = None

    if send_checklist_email and checklist_level and checklist_scope:
        from app.services.document_checklist_email_service import (
            send_document_checklist_to_lead,
        )

        result = send_document_checklist_to_lead(
            db,
            lead=lead,
            program_level=checklist_level,
            scope=checklist_scope,
            country_id=checklist_country_id,
            current_user=current_user,
        )
        email_sent = bool(result.get("sent"))
        email_error = result.get("error")
        if email_sent:
            row.checklist_email_to = (result.get("email_to") or "").strip() or None
            row.checklist_email_sent_at = result.get("sent_at")
            sent_docs = result.get("sent_documents")
            row.checklist_sent_documents = (
                sent_docs if isinstance(sent_docs, list) else []
            )
            db.add(row)
            db.commit()
            db.refresh(row)

    row = (
        db.query(CounselorFollowupLog)
        .options(joinedload(CounselorFollowupLog.status))
        .filter(CounselorFollowupLog.id == row.id)
        .one()
    )
    names = _counselor_names_by_id(db, [stored_counselor_id])
    uid = _parse_counselor_user_id(stored_counselor_id)
    return _serialize_followup(
        row,
        counselor_name=names.get(uid) if uid is not None else None,
        email_sent=email_sent,
        email_error=email_error,
    )


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


def latest_followup_status_for_lead_ids(db: Session, lead_ids: list[int]) -> dict[int, str]:
    """Return latest counselor follow-up status_heading per lead (Counselor Notes status)."""
    if not lead_ids:
        return {}
    ranked = (
        db.query(
            CounselorFollowupLog.lead_id.label("lead_id"),
            CounselorFollowupLog.status_id.label("status_id"),
            func.row_number()
            .over(
                partition_by=CounselorFollowupLog.lead_id,
                order_by=(
                    CounselorFollowupLog.created_at.desc(),
                    CounselorFollowupLog.id.desc(),
                ),
            )
            .label("rn"),
        )
        .filter(CounselorFollowupLog.lead_id.in_(lead_ids))
        .subquery()
    )
    rows = (
        db.query(ranked.c.lead_id, CounselorStatusMaster.status_heading)
        .join(CounselorStatusMaster, CounselorStatusMaster.id == ranked.c.status_id)
        .filter(ranked.c.rn == 1)
        .all()
    )
    return {
        int(lead_id): str(heading)
        for lead_id, heading in rows
        if lead_id is not None and heading
    }
