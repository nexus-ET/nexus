from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.research_project import ResearchProject
from app.utils.timezone import utc_now
from app.schemas.research_project import (
    RESEARCH_PROJECT_TYPE_LABELS,
    ResearchProjectInput,
    ResearchProjectOut,
    ResearchProjectType,
    ResearchProjectsResponse,
    list_research_project_type_options,
)


def _project_query(db: Session, *, lead_id: int | None, booking_id: int):
    if lead_id is not None:
        return db.query(ResearchProject).filter(ResearchProject.lead_id == lead_id)
    return db.query(ResearchProject).filter(ResearchProject.booking_id == booking_id)


def _serialize_project(record: ResearchProject) -> ResearchProjectOut:
    project_type = ResearchProjectType(record.project_type)
    return ResearchProjectOut(
        id=record.id,
        project_type=project_type,
        project_type_label=RESEARCH_PROJECT_TYPE_LABELS[project_type],
        project_title=record.project_title,
        project_description=record.project_description,
        publication_url=record.publication_url,
        role=record.role,
        sort_order=record.sort_order,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_research_projects(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
) -> ResearchProjectsResponse:
    lead_id = lead.id if lead else None
    records = (
        _project_query(db, lead_id=lead_id, booking_id=booking_id)
        .order_by(ResearchProject.sort_order.asc(), ResearchProject.id.asc())
        .all()
    )
    saved_at = max((record.updated_at for record in records), default=None)

    return ResearchProjectsResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        project_types=list_research_project_type_options(),
        projects=[_serialize_project(record) for record in records],
        saved_at=saved_at,
    )


def _get_owned_project(
    db: Session,
    *,
    project_id: int,
    lead_id: int | None,
    booking_id: int,
) -> ResearchProject:
    record = db.query(ResearchProject).filter(ResearchProject.id == project_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Research project not found.")

    if lead_id is not None:
        if record.lead_id != lead_id:
            raise HTTPException(status_code=404, detail="Research project not found.")
    elif record.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Research project not found.")

    return record


def create_research_project(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: ResearchProjectInput,
) -> ResearchProjectsResponse:
    lead_id = lead.id if lead else None
    existing_count = _project_query(db, lead_id=lead_id, booking_id=booking_id).count()

    record = ResearchProject(
        lead_id=lead_id,
        booking_id=booking_id,
        project_type=payload.project_type.value,
        project_title=payload.project_title,
        project_description=payload.project_description,
        publication_url=payload.publication_url,
        role=payload.role,
        sort_order=existing_count,
    )
    db.add(record)
    db.commit()
    return get_research_projects(db, booking_id=booking_id, lead=lead)


def update_research_project(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    project_id: int,
    payload: ResearchProjectInput,
) -> ResearchProjectsResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_project(
        db,
        project_id=project_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )

    record.project_type = payload.project_type.value
    record.project_title = payload.project_title
    record.project_description = payload.project_description
    record.publication_url = payload.publication_url
    record.role = payload.role
    record.updated_at = utc_now()
    db.commit()
    return get_research_projects(db, booking_id=booking_id, lead=lead)


def delete_research_project(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    project_id: int,
) -> ResearchProjectsResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_project(
        db,
        project_id=project_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )
    db.delete(record)
    db.commit()
    return get_research_projects(db, booking_id=booking_id, lead=lead)
