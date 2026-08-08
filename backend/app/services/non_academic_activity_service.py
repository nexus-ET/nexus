from __future__ import annotations

from datetime import datetime, timezone
from app.utils.timezone import utc_now

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.non_academic_activity import NonAcademicActivity
from app.schemas.non_academic_activity import (
    ACTIVITY_CATEGORY_LABELS,
    ActivityCategory,
    NonAcademicActivitiesResponse,
    NonAcademicActivityInput,
    NonAcademicActivityOut,
    list_activity_category_options,
)


def _activity_query(db: Session, *, lead_id: int | None, booking_id: int):
    if lead_id is not None:
        return db.query(NonAcademicActivity).filter(NonAcademicActivity.lead_id == lead_id)
    return db.query(NonAcademicActivity).filter(NonAcademicActivity.booking_id == booking_id)


def _serialize_activity(record: NonAcademicActivity) -> NonAcademicActivityOut:
    category_label = None
    category_value = None
    if record.activity_category:
        category_value = ActivityCategory(record.activity_category)
        category_label = ACTIVITY_CATEGORY_LABELS[category_value]

    return NonAcademicActivityOut(
        id=record.id,
        activity_category=category_value,
        activity_category_label=category_label,
        activity_name=record.activity_name,
        role_or_title=record.role_or_title,
        start_date=record.start_date,
        end_date=record.end_date,
        description=record.description,
        sort_order=record.sort_order,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_non_academic_activities(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
) -> NonAcademicActivitiesResponse:
    lead_id = lead.id if lead else None
    records = (
        _activity_query(db, lead_id=lead_id, booking_id=booking_id)
        .order_by(NonAcademicActivity.sort_order.asc(), NonAcademicActivity.id.asc())
        .all()
    )
    saved_at = max((record.updated_at for record in records), default=None)

    return NonAcademicActivitiesResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        activity_categories=list_activity_category_options(),
        activities=[_serialize_activity(record) for record in records],
        saved_at=saved_at,
    )


def _get_owned_activity(
    db: Session,
    *,
    activity_id: int,
    lead_id: int | None,
    booking_id: int,
) -> NonAcademicActivity:
    record = db.query(NonAcademicActivity).filter(NonAcademicActivity.id == activity_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Non-academic activity not found.")

    if lead_id is not None:
        if record.lead_id != lead_id:
            raise HTTPException(status_code=404, detail="Non-academic activity not found.")
    elif record.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Non-academic activity not found.")

    return record


def _is_activity_empty(payload: NonAcademicActivityInput) -> bool:
    return not any(
        [
            payload.activity_category,
            payload.activity_name,
            payload.role_or_title,
            payload.start_date,
            payload.end_date,
            payload.description,
        ]
    )


def create_non_academic_activity(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: NonAcademicActivityInput,
) -> NonAcademicActivitiesResponse:
    if _is_activity_empty(payload):
        return get_non_academic_activities(db, booking_id=booking_id, lead=lead)

    lead_id = lead.id if lead else None
    existing_count = _activity_query(db, lead_id=lead_id, booking_id=booking_id).count()

    record = NonAcademicActivity(
        lead_id=lead_id,
        booking_id=booking_id,
        activity_category=payload.activity_category.value if payload.activity_category else None,
        activity_name=payload.activity_name,
        role_or_title=payload.role_or_title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        description=payload.description,
        sort_order=existing_count,
    )
    db.add(record)
    db.commit()
    return get_non_academic_activities(db, booking_id=booking_id, lead=lead)


def update_non_academic_activity(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    activity_id: int,
    payload: NonAcademicActivityInput,
) -> NonAcademicActivitiesResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_activity(
        db,
        activity_id=activity_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )

    record.activity_category = (
        payload.activity_category.value if payload.activity_category else None
    )
    record.activity_name = payload.activity_name
    record.role_or_title = payload.role_or_title
    record.start_date = payload.start_date
    record.end_date = payload.end_date
    record.description = payload.description
    record.updated_at = utc_now()
    db.commit()
    return get_non_academic_activities(db, booking_id=booking_id, lead=lead)


def delete_non_academic_activity(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    activity_id: int,
) -> NonAcademicActivitiesResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_activity(
        db,
        activity_id=activity_id,
        lead_id=lead_id,
        booking_id=booking_id,
    )
    db.delete(record)
    db.commit()
    return get_non_academic_activities(db, booking_id=booking_id, lead=lead)
