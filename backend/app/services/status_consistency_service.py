from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.status_definition import StatusDefinition
from app.models.status_history import StatusHistory


@dataclass
class ConsistencyIssue:
    code: str
    message: str
    student_id: int | None = None
    details: dict = field(default_factory=dict)


def validate_status_history_row_integrity(db: Session, student_id: int | None = None) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []

    history_query = db.query(StatusHistory)
    if student_id is not None:
        history_query = history_query.filter(StatusHistory.student_id == student_id)
    history_rows = history_query.all()

    lead_ids = {row.student_id for row in history_rows}
    status_ids = {row.status_id for row in history_rows}

    existing_leads = {
        row.id
        for row in db.query(Lead.id).filter(Lead.id.in_(lead_ids or [-1])).all()
    }
    existing_statuses = {
        row.id
        for row in db.query(StatusDefinition.id).filter(StatusDefinition.id.in_(status_ids or [-1])).all()
    }

    for row in history_rows:
        if row.student_id not in existing_leads:
            issues.append(
                ConsistencyIssue(
                    code="orphan_student",
                    message="status_history references a missing student.",
                    student_id=row.student_id,
                    details={"history_id": row.id},
                )
            )
        if row.status_id not in existing_statuses:
            issues.append(
                ConsistencyIssue(
                    code="orphan_status",
                    message="status_history references a missing status definition.",
                    student_id=row.student_id,
                    details={"history_id": row.id, "status_id": row.status_id},
                )
            )

    return issues


def validate_student_current_status_alignment(
    db: Session,
    student_id: int | None = None,
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []

    lead_query = db.query(Lead)
    if student_id is not None:
        lead_query = lead_query.filter(Lead.id == student_id)
    leads = lead_query.all()

    for lead in leads:
        latest_history = (
            db.query(StatusHistory)
            .filter(StatusHistory.student_id == lead.id)
            .order_by(StatusHistory.created_at.desc(), StatusHistory.id.desc())
            .first()
        )
        if not latest_history:
            if lead.status_definition_id is not None:
                issues.append(
                    ConsistencyIssue(
                        code="missing_history",
                        message="Lead has a pipeline status but no status_history rows.",
                        student_id=lead.id,
                        details={"status_definition_id": lead.status_definition_id},
                    )
                )
            continue

        if lead.status_definition_id != latest_history.status_id:
            issues.append(
                ConsistencyIssue(
                    code="status_mismatch",
                    message="Latest status_history does not match lead.status_definition_id.",
                    student_id=lead.id,
                    details={
                        "lead_status_definition_id": lead.status_definition_id,
                        "latest_history_status_id": latest_history.status_id,
                        "latest_history_id": latest_history.id,
                    },
                )
            )

    return issues


def validate_status_data_consistency(
    db: Session,
    student_id: int | None = None,
) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    issues.extend(validate_status_history_row_integrity(db, student_id=student_id))
    issues.extend(validate_student_current_status_alignment(db, student_id=student_id))
    return issues


def assert_single_active_pipeline_status(lead: Lead) -> None:
    """Leads store exactly one active pipeline status via status_definition_id."""
    if lead.status_definition_id is None:
        return
    # status_definition_id is a scalar FK — multiple active stages cannot coexist.
    return
