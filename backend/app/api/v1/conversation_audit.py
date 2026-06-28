from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.conversation_audit import (
    ConversationAuditCandidateListResponse,
    ConversationAuditCandidateSummary,
    ConversationAuditListResponse,
    ConversationAuditLogRead,
)
from app.services.conversation_audit_service import (
    list_audit_turns_for_lead,
    list_conversation_audit_candidates,
    list_conversation_audit_logs,
    list_distinct_audit_models,
)

router = APIRouter(prefix="/audit", tags=["Agent Audit"])


@router.get("/conversations/candidates", response_model=ConversationAuditCandidateListResponse)
@router.get("/conversations/candidates/", response_model=ConversationAuditCandidateListResponse)
def get_conversation_audit_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None, description="all | escalated | ai_active"),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    model: str | None = Query(None, description="Filter by ai_model value"),
    db: Session = Depends(get_db),
):
    payload = list_conversation_audit_candidates(
        db,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        sort_by=sort_by,
        order=order,
        ai_model=model,
    )
    return ConversationAuditCandidateListResponse(
        items=[ConversationAuditCandidateSummary.model_validate(item) for item in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        total_pages=payload["total_pages"],
    )


@router.get("/conversations/candidates/{lead_id}/turns", response_model=ConversationAuditListResponse)
@router.get("/conversations/candidates/{lead_id}/turns/", response_model=ConversationAuditListResponse)
def get_conversation_audit_candidate_turns(
    lead_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    payload = list_audit_turns_for_lead(db, lead_id, page=page, page_size=page_size)
    return ConversationAuditListResponse(
        items=[ConversationAuditLogRead.model_validate(item) for item in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        total_pages=payload["total_pages"],
    )


@router.get("/conversations", response_model=ConversationAuditListResponse)
@router.get("/conversations/", response_model=ConversationAuditListResponse)
def get_conversation_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None, description="all | escalated | ai_active"),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    model: str | None = Query(None, description="Filter by ai_model value"),
    db: Session = Depends(get_db),
):
    payload = list_conversation_audit_logs(
        db,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        sort_by=sort_by,
        order=order,
        ai_model=model,
    )
    return ConversationAuditListResponse(
        items=[ConversationAuditLogRead.model_validate(item) for item in payload["items"]],
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        total_pages=payload["total_pages"],
    )


@router.get("/conversations/models")
@router.get("/conversations/models/")
def get_conversation_audit_models(db: Session = Depends(get_db)):
    return {"models": list_distinct_audit_models(db)}
