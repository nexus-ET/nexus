from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.academia_wizard import AcademiaAuditLog


def _serialize(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {"value": value}


def write_academia_audit(
    db: Session,
    *,
    user_id: int | None,
    entity_type: str,
    entity_id: int,
    action: str,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    rollback_of_id: int | None = None,
    commit: bool = False,
) -> AcademiaAuditLog:
    entry = AcademiaAuditLog(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_data=old_data,
        new_data=new_data,
        rollback_of_id=rollback_of_id,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def list_academia_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    limit: int = 50,
) -> list[AcademiaAuditLog]:
    return (
        db.query(AcademiaAuditLog)
        .filter(
            AcademiaAuditLog.entity_type == entity_type,
            AcademiaAuditLog.entity_id == entity_id,
        )
        .order_by(AcademiaAuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


def get_academia_audit(db: Session, audit_id: int) -> AcademiaAuditLog | None:
    return db.query(AcademiaAuditLog).filter(AcademiaAuditLog.id == audit_id).first()
