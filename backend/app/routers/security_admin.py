from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.security_audit import (
    SecurityAuditRunOut,
    SecurityAuditRunsResponse,
    SecurityAuditStatusResponse,
    SecurityAuditTriggerResponse,
)
from app.services.audit_runner import (
    get_latest_security_audit_status,
    get_security_audit_run,
    list_security_audit_runs,
    run_security_audit_suite,
)
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/security-audit/status", response_model=SecurityAuditStatusResponse)
@router.get("/security-audit/status/", response_model=SecurityAuditStatusResponse)
def read_security_audit_status(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    latest = get_latest_security_audit_status(db)
    return SecurityAuditStatusResponse(
        latest_run=latest,
        fortress_healthy=latest is None or latest.status == "pass",
    )


@router.get("/security-audit/runs", response_model=SecurityAuditRunsResponse)
@router.get("/security-audit/runs/", response_model=SecurityAuditRunsResponse)
def read_security_audit_runs(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    runs = list_security_audit_runs(db)
    latest_status = runs[0].status if runs else None
    return SecurityAuditRunsResponse(runs=runs, latest_status=latest_status)


@router.get("/security-audit/runs/{run_id}", response_model=SecurityAuditRunOut)
@router.get("/security-audit/runs/{run_id}/", response_model=SecurityAuditRunOut)
def read_security_audit_run(
    run_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    run = get_security_audit_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Security audit run not found.")
    return run


@router.post("/security-audit/run", response_model=SecurityAuditTriggerResponse)
@router.post("/security-audit/run/", response_model=SecurityAuditTriggerResponse)
@log_action("trigger_security_audit", "security_audit")
def trigger_security_audit(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    run_record, alert_sent = run_security_audit_suite(
        db,
        triggered_by="manual",
        triggered_by_user_id=current_user.id,
    )
    serialized = get_security_audit_run(db, run_record.id)
    if serialized is None:
        raise HTTPException(status_code=500, detail="Audit run could not be loaded.")
    return SecurityAuditTriggerResponse(run=serialized, alert_sent=alert_sent)
