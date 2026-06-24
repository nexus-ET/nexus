from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.lead_quarantine import LeadQuarantine
from app.models.raw_incoming_lead import RawIncomingLead


def _apply_date_filters(query, model, start_date: datetime | None, end_date: datetime | None):
    ts_col = getattr(model, "received_at", None) or model.created_at
    if start_date is not None:
        query = query.filter(ts_col >= start_date)
    if end_date is not None:
        query = query.filter(ts_col <= end_date)
    return query


def get_ingestion_quality_report(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    sync_mode: str | None = None,
) -> dict:
    """Aggregate clean vs quarantined ingestion metrics."""
    raw_query = db.query(RawIncomingLead)
    raw_query = _apply_date_filters(raw_query, RawIncomingLead, start_date, end_date)
    if sync_mode:
        raw_query = raw_query.filter(RawIncomingLead.sync_mode == sync_mode.upper())

    total_received = raw_query.count()
    total_processed = raw_query.filter(RawIncomingLead.processed.is_(True)).count()
    total_pending = raw_query.filter(RawIncomingLead.processed.is_(False)).count()
    total_promoted = raw_query.filter(RawIncomingLead.lead_id.isnot(None)).count()

    quarantine_query = db.query(LeadQuarantine)
    quarantine_query = _apply_date_filters(quarantine_query, LeadQuarantine, start_date, end_date)
    if sync_mode:
        quarantine_query = quarantine_query.filter(LeadQuarantine.sync_mode == sync_mode.upper())

    total_quarantined = quarantine_query.count()
    total_reprocessed = quarantine_query.filter(LeadQuarantine.reprocessed_at.isnot(None)).count()

    reason_rows = (
        quarantine_query.with_entities(LeadQuarantine.error_code, func.count(LeadQuarantine.id))
        .group_by(LeadQuarantine.error_code)
        .order_by(func.count(LeadQuarantine.id).desc())
        .all()
    )
    quarantine_reasons = [
        {"reason": row[0], "label": _reason_label(row[0]), "count": int(row[1])}
        for row in reason_rows
    ]

    clean_ratio = round((total_promoted / total_received) * 100, 1) if total_received else 0.0
    quarantine_ratio = round((total_quarantined / total_received) * 100, 1) if total_received else 0.0

    return {
        "total_received": total_received,
        "total_processed": total_processed,
        "total_pending": total_pending,
        "total_promoted": total_promoted,
        "total_quarantined": total_quarantined,
        "total_reprocessed": total_reprocessed,
        "clean_ratio_percent": clean_ratio,
        "quarantine_ratio_percent": quarantine_ratio,
        "quarantine_reasons": quarantine_reasons,
        "sync_mode_filter": sync_mode.upper() if sync_mode else None,
    }


def _reason_label(code: str) -> str:
    labels = {
        "invalid_email": "Invalid Email",
        "invalid_phone": "Invalid Phone",
        "unicode_issues": "Unicode Issues",
        "missing_leadgen_id": "Missing Leadgen ID",
        "validation_failed": "Validation Failed",
        "reprocessed": "Reprocessed",
    }
    return labels.get(code, code.replace("_", " ").title())
