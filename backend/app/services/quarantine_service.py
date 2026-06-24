from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.lead_quarantine import LeadQuarantine
from app.services.lead_ingestion_pipeline import reprocess_quarantine_record


def list_quarantine_records(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
) -> tuple[list[LeadQuarantine], int]:
    safe_page = max(1, page)
    safe_limit = min(max(1, limit), 100)
    query = db.query(LeadQuarantine).filter(LeadQuarantine.reprocessed_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(LeadQuarantine.created_at.desc(), LeadQuarantine.id.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
        .all()
    )
    return rows, total


def get_quarantine_record(db: Session, record_id: int) -> LeadQuarantine | None:
    return db.query(LeadQuarantine).filter(LeadQuarantine.id == record_id).first()


def update_quarantine_payload(
    db: Session,
    record: LeadQuarantine,
    normalized_payload: dict,
) -> LeadQuarantine:
    record.normalized_payload = normalized_payload
    db.commit()
    db.refresh(record)
    return record


def delete_quarantine_record(db: Session, record: LeadQuarantine) -> None:
    db.delete(record)
    db.commit()


def reprocess_quarantine(db: Session, record: LeadQuarantine, normalized_payload: dict | None = None):
    return reprocess_quarantine_record(db, record, normalized_payload=normalized_payload)
