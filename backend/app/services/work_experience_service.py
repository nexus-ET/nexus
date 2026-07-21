from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.lead import Lead
from app.models.work_experience import WorkExperience, WorkProject
from app.schemas.work_experience import WorkExperienceSaveRequest, WorkExperiencesResponse


def _experience_query(db: Session, *, lead_id: int | None, booking_id: int):
    if lead_id is not None:
        return db.query(WorkExperience).filter(WorkExperience.lead_id == lead_id)
    return db.query(WorkExperience).filter(WorkExperience.booking_id == booking_id)


def get_work_experiences(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
) -> WorkExperiencesResponse:
    lead_id = lead.id if lead else None
    records = (
        _experience_query(db, lead_id=lead_id, booking_id=booking_id)
        .options(joinedload(WorkExperience.projects))
        .order_by(WorkExperience.sort_order.asc(), WorkExperience.id.asc())
        .all()
    )

    saved_at = max((record.created_at for record in records), default=None)

    return WorkExperiencesResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        experiences=records,
        saved_at=saved_at,
    )


def _is_experience_empty(experience_input) -> bool:
    has_project = any(
        project.project_name or project.project_description
        for project in experience_input.projects
    )
    return not any(
        [
            experience_input.company_name,
            experience_input.job_title,
            experience_input.start_date,
            experience_input.end_date,
            experience_input.description,
            experience_input.is_current,
            has_project,
        ]
    )


def save_work_experiences(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: WorkExperienceSaveRequest,
) -> WorkExperiencesResponse:
    lead_id = lead.id if lead else None
    existing = _experience_query(db, lead_id=lead_id, booking_id=booking_id).all()
    for record in existing:
        db.delete(record)
    db.flush()

    saved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    for index, experience_input in enumerate(payload.experiences):
        if _is_experience_empty(experience_input):
            continue

        record = WorkExperience(
            lead_id=lead_id,
            booking_id=booking_id,
            company_name=experience_input.company_name,
            job_title=experience_input.job_title,
            start_date=experience_input.start_date,
            end_date=None if experience_input.is_current else experience_input.end_date,
            is_current=experience_input.is_current,
            description=experience_input.description,
            sort_order=index,
            created_at=saved_at,
        )
        db.add(record)
        db.flush()

        for project_index, project_input in enumerate(experience_input.projects):
            if not (project_input.project_name or project_input.project_description):
                continue
            db.add(
                WorkProject(
                    work_experience_id=record.id,
                    project_name=project_input.project_name,
                    project_description=project_input.project_description,
                    sort_order=project_index,
                )
            )

    try:
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = get_work_experiences(db, booking_id=booking_id, lead=lead)
    response.saved_at = saved_at
    return response
