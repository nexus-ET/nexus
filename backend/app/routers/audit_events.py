from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.api import deps
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.client_audit_event import ClientAuditEventsBatchIn
from app.services.audit_context import build_client_event_details, client_event_target_resource
from app.services.audit_logger import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter()


def _event_fingerprint(event) -> tuple[str, ...]:
    endpoint = ""
    query = ""
    trigger_control = ""
    trigger_value = ""
    if event.metadata and isinstance(event.metadata, dict):
        endpoint = str(event.metadata.get("api_endpoint") or "")
        query = str(event.metadata.get("query_string") or "")
        trigger_control = str(event.metadata.get("trigger_control") or "")
        trigger_value = str(event.metadata.get("trigger_value") or "")
    return (
        event.action_type,
        event.page,
        event.action,
        event.element_label or "",
        event.element_type or "",
        endpoint,
        query,
        trigger_control,
        trigger_value,
    )


def _dedupe_batch_events(events):
    seen: set[tuple[str, ...]] = set()
    unique = []
    for event in events:
        key = _event_fingerprint(event)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


async def _parse_audit_batch(request: Request) -> ClientAuditEventsBatchIn | None:
    """Parse JSON body; treat client disconnect / empty body as a no-op.

    Browser ``keepalive`` / ``beforeunload`` audit flushes often abort mid-body.
    FastAPI would otherwise convert ``ClientDisconnect`` into HTTP 400
    \"There was an error parsing the body\" and spam Exception Report.
    """
    import json

    try:
        raw = await request.body()
    except ClientDisconnect:
        logger.debug("audit-events client disconnected before body finished")
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Truncated keepalive payload — not actionable.
        logger.debug("audit-events body not valid JSON (likely aborted flush)")
        return None
    try:
        return ClientAuditEventsBatchIn.model_validate(data)
    except ValidationError:
        logger.debug("audit-events payload failed validation", exc_info=True)
        return None


@router.post("/audit-events", status_code=204)
@router.post("/audit-events/", status_code=204)
@limiter.limit("120/minute")
async def ingest_client_audit_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Response:
    """Accept batched UI activity events from the authenticated frontend client."""
    payload = await _parse_audit_batch(request)
    if payload is None or not payload.events:
        # Aborted keepalive / empty body — acknowledge quietly.
        return Response(status_code=204)

    for event in _dedupe_batch_events(payload.events):
        try:
            write_audit_log(
                db,
                user_id=current_user.id,
                action_type=event.action_type,
                target_resource=client_event_target_resource(event.action_type, event.target_resource),
                resource_id=event.resource_id,
                request=request,
                status="success",
                details=build_client_event_details(
                    action_type=event.action_type,
                    page=event.page,
                    menu=event.menu,
                    action=event.action,
                    element_type=event.element_type,
                    element_label=event.element_label,
                    metadata=event.metadata,
                ),
                sync_mode="MANUAL",
                commit=False,
            )
        except Exception:
            logger.exception("Failed to prepare client audit event %s", event.action_type)
            db.rollback()
            return Response(status_code=500)
    try:
        db.commit()
    except Exception:
        logger.exception("Failed to commit client audit event batch")
        db.rollback()
        return Response(status_code=500)
    return Response(status_code=204)
