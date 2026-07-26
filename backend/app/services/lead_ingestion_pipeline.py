from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.lead_quarantine import LeadQuarantine
from app.models.raw_incoming_lead import RawIncomingLead
from app.services.facebook_leads import LeadgenWebhookEvent
from app.services.lead_validation import primary_error_code, validate_lead_payload

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50


@dataclass(frozen=True)
class StageLeadResult:
    raw: RawIncomingLead | None
    created: bool
    skipped: bool


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_safe(value: Any) -> Any:
    """Convert values so PostgreSQL JSONB / stdlib json can serialize them."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in value]
    return value


def raw_leadgen_already_handled(db: Session, leadgen_id: str) -> bool:
    """True when this leadgen id is already staged, processed, or in Leads."""
    if db.query(Lead.id).filter(Lead.meta_leadgen_id == leadgen_id).first() is not None:
        return True
    return (
        db.query(RawIncomingLead.id)
        .filter(RawIncomingLead.meta_leadgen_id == leadgen_id)
        .first()
        is not None
    )


def stage_meta_lead_raw(
    db: Session,
    *,
    event: LeadgenWebhookEvent,
    details: dict[str, Any],
    sync_mode: str,
    triggered_by_user: str,
    source: str,
    triggered_by_user_id: int | None = None,
    sync_log_id: int | None = None,
) -> StageLeadResult:
    """
    Persist raw Meta payload to staging without validation.

    Skips duplicate leadgen ids already present in staging or Leads.
    """
    leadgen_id = event.leadgen_id.strip()
    if raw_leadgen_already_handled(db, leadgen_id):
        return StageLeadResult(raw=None, created=False, skipped=True)

    payload = _json_safe(
        {
            "event": event.raw_value,
            "event_meta": {
                "leadgen_id": event.leadgen_id,
                "form_id": event.form_id,
                "page_id": event.page_id,
                "ad_id": event.ad_id,
                "created_time": event.created_time,
            },
            "details": details,
        }
    )
    row = RawIncomingLead(
        meta_leadgen_id=leadgen_id,
        raw_payload=payload,
        source=source,
        sync_mode=sync_mode,
        triggered_by_user=triggered_by_user,
        triggered_by_user_id=triggered_by_user_id,
        sync_log_id=sync_log_id,
        processed=False,
        received_at=_utcnow_naive(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Staged raw Meta lead leadgen_id=%s source=%s sync_mode=%s raw_id=%s",
        leadgen_id,
        source,
        sync_mode,
        row.id,
    )
    return StageLeadResult(raw=row, created=True, skipped=False)


def _payload_from_raw(raw: RawIncomingLead) -> dict[str, Any]:
    from app.services.leads import build_lead_data_from_meta

    stored = raw.raw_payload or {}
    event_meta = stored.get("event_meta") or {}
    event = LeadgenWebhookEvent(
        leadgen_id=event_meta.get("leadgen_id") or raw.meta_leadgen_id,
        form_id=event_meta.get("form_id"),
        page_id=event_meta.get("page_id"),
        ad_id=event_meta.get("ad_id"),
        adgroup_id=event_meta.get("adgroup_id"),
        created_time=event_meta.get("created_time"),
        raw_value=stored.get("event") or {},
    )
    details = stored.get("details") or {}
    return build_lead_data_from_meta(event, details)


def _move_to_quarantine(
    db: Session,
    raw: RawIncomingLead,
    lead_data: dict[str, Any],
    errors: list[str],
) -> LeadQuarantine:
    reason = "; ".join(errors)
    safe_payload = _json_safe(dict(lead_data))
    row = LeadQuarantine(
        raw_incoming_lead_id=raw.id,
        meta_leadgen_id=raw.meta_leadgen_id,
        original_payload=safe_payload,
        normalized_payload=dict(safe_payload),
        error_reason=reason,
        error_code=primary_error_code(errors),
        source=raw.source,
        sync_mode=raw.sync_mode,
        triggered_by_user=raw.triggered_by_user,
    )
    db.add(row)
    db.flush()
    raw.processed = True
    raw.processed_at = _utcnow_naive()
    raw.quarantine_id = row.id
    raw.processing_error = reason
    db.commit()
    db.refresh(row)
    logger.info(
        "Quarantined leadgen_id=%s raw_id=%s quarantine_id=%s reason=%s",
        raw.meta_leadgen_id,
        raw.id,
        row.id,
        reason,
    )
    return row


def _promote_to_leads(db: Session, raw: RawIncomingLead, lead_data: dict[str, Any]):
    from app.services.leads import save_lead

    result = save_lead(db, lead_data)
    raw.processed = True
    raw.processed_at = _utcnow_naive()
    raw.lead_id = result.lead.id
    raw.processing_error = None
    db.commit()
    logger.info(
        "Promoted leadgen_id=%s raw_id=%s lead_id=%s created=%s",
        raw.meta_leadgen_id,
        raw.id,
        result.lead.id,
        result.created,
    )
    return result


def process_one_raw_lead(db: Session, raw: RawIncomingLead):
    if raw.processed:
        return None
    try:
        lead_data = _payload_from_raw(raw)
    except Exception as exc:
        logger.exception("Failed to parse raw lead id=%s", raw.id)
        errors = [f"Parse error: {exc}"]
        return _move_to_quarantine(db, raw, {"meta_leadgen_id": raw.meta_leadgen_id}, errors)

    errors = validate_lead_payload(lead_data)
    if errors:
        return _move_to_quarantine(db, raw, lead_data, errors)
    try:
        return _promote_to_leads(db, raw, lead_data)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to promote raw lead id=%s; moving to quarantine.", raw.id)
        return _move_to_quarantine(
            db,
            raw,
            lead_data,
            [f"Promote error: {exc}"],
        )


def process_raw_leads(db: Session, *, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, int]:
    """Process unprocessed staging rows (valid → Leads, invalid → Quarantine)."""
    rows = (
        db.query(RawIncomingLead)
        .filter(RawIncomingLead.processed.is_(False))
        .order_by(RawIncomingLead.id.asc())
        .limit(max(1, batch_size))
        .all()
    )
    promoted = 0
    quarantined = 0
    failed = 0
    for row in rows:
        try:
            outcome = process_one_raw_lead(db, row)
            if outcome is None:
                continue
            if isinstance(outcome, LeadQuarantine):
                quarantined += 1
            else:
                promoted += 1
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("Failed to process raw incoming lead id=%s", row.id)
    return {
        "examined": len(rows),
        "promoted": promoted,
        "quarantined": quarantined,
        "failed": failed,
    }


def reprocess_quarantine_record(
    db: Session,
    quarantine: LeadQuarantine,
    *,
    normalized_payload: dict[str, Any] | None = None,
):
    """Re-validate quarantine payload and promote to Leads when clean."""
    from app.services.leads import save_lead

    payload = dict(normalized_payload or quarantine.normalized_payload or {})
    if not payload.get("leadgen_id") and not payload.get("meta_leadgen_id"):
        payload["leadgen_id"] = quarantine.meta_leadgen_id

    errors = validate_lead_payload(payload)
    quarantine.normalized_payload = _json_safe(payload)
    quarantine.updated_at = _utcnow_naive()

    if errors:
        quarantine.error_reason = "; ".join(errors)
        quarantine.error_code = primary_error_code(errors)
        db.commit()
        db.refresh(quarantine)
        return quarantine

    result = save_lead(db, payload)
    quarantine.lead_id = result.lead.id
    quarantine.reprocessed_at = _utcnow_naive()
    quarantine.error_reason = ""
    quarantine.error_code = "reprocessed"
    quarantine.normalized_payload = _json_safe(payload)
    db.commit()
    db.refresh(quarantine)
    return result
