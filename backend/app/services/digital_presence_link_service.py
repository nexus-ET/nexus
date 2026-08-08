from __future__ import annotations

from datetime import datetime, timezone
from app.utils.timezone import utc_now

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.digital_presence_link import DigitalPresenceLink
from app.models.lead import Lead
from app.schemas.digital_presence_link import (
    CATEGORY_LABELS,
    CATEGORY_SORT_ORDER,
    PLATFORM_LABELS,
    PLATFORM_SORT_ORDER,
    DigitalPresenceCategory,
    DigitalPresenceLinkInput,
    DigitalPresenceLinkOut,
    DigitalPresenceLinksResponse,
    DigitalPlatform,
    list_category_options,
    list_platform_options,
)


def _link_query(db: Session, *, lead_id: int | None, booking_id: int | None):
    if lead_id is not None:
        return db.query(DigitalPresenceLink).filter(DigitalPresenceLink.lead_id == lead_id)
    return db.query(DigitalPresenceLink).filter(DigitalPresenceLink.booking_id == booking_id)


def _serialize_link(record: DigitalPresenceLink) -> DigitalPresenceLinkOut:
    platform = DigitalPlatform(record.platform_name) if record.platform_name else None
    category = DigitalPresenceCategory(record.category) if record.category else None
    return DigitalPresenceLinkOut(
        id=record.id,
        platform_name=platform,
        platform_label=PLATFORM_LABELS.get(platform) if platform else None,
        url=record.url,
        category=category,
        category_label=CATEGORY_LABELS.get(category) if category else None,
        admission_value_note=record.admission_value_note,
        sort_order=record.sort_order,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _link_sort_key(record: DigitalPresenceLink) -> tuple[int, int, int]:
    category = DigitalPresenceCategory(record.category) if record.category else None
    platform = DigitalPlatform(record.platform_name) if record.platform_name else None
    return (
        CATEGORY_SORT_ORDER.get(category, 99) if category else 99,
        PLATFORM_SORT_ORDER.get(platform, 99) if platform else 99,
        record.id,
    )


def get_digital_presence_links(
    db: Session,
    *,
    booking_id: int | None,
    lead: Lead | None,
) -> DigitalPresenceLinksResponse:
    lead_id = lead.id if lead else None
    records = _link_query(db, lead_id=lead_id, booking_id=booking_id).all()
    records.sort(key=_link_sort_key)
    saved_at = max((record.updated_at for record in records), default=None)

    return DigitalPresenceLinksResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        platform_options=list_platform_options(),
        category_options=list_category_options(),
        links=[_serialize_link(record) for record in records],
        saved_at=saved_at,
    )


def get_digital_presence_links_for_lead(db: Session, lead_id: int) -> DigitalPresenceLinksResponse:
    records = _link_query(db, lead_id=lead_id, booking_id=None).all()
    records.sort(key=_link_sort_key)
    saved_at = max((record.updated_at for record in records), default=None)
    return DigitalPresenceLinksResponse(
        booking_id=None,
        lead_id=lead_id,
        platform_options=list_platform_options(),
        category_options=list_category_options(),
        links=[_serialize_link(record) for record in records],
        saved_at=saved_at,
    )


def _get_owned_link(
    db: Session,
    *,
    link_id: int,
    lead_id: int | None,
    booking_id: int | None,
) -> DigitalPresenceLink:
    record = db.query(DigitalPresenceLink).filter(DigitalPresenceLink.id == link_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Digital presence link not found.")

    if lead_id is not None:
        if record.lead_id != lead_id:
            raise HTTPException(status_code=404, detail="Digital presence link not found.")
    elif record.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Digital presence link not found.")

    return record


def _validate_link_input(payload: DigitalPresenceLinkInput) -> dict:
    if not payload.platform_name:
        raise HTTPException(status_code=400, detail="Platform is required.")
    if not payload.url:
        raise HTTPException(status_code=400, detail="URL is required.")
    if not payload.category:
        raise HTTPException(status_code=400, detail="Category is required.")

    return {
        "platform_name": payload.platform_name.value,
        "url": payload.url,
        "category": payload.category.value,
        "admission_value_note": payload.admission_value_note,
    }


def create_digital_presence_link(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: DigitalPresenceLinkInput,
) -> DigitalPresenceLinksResponse:
    lead_id = lead.id if lead else None
    fields = _validate_link_input(payload)
    existing_count = _link_query(db, lead_id=lead_id, booking_id=booking_id).count()

    record = DigitalPresenceLink(
        lead_id=lead_id,
        booking_id=booking_id,
        sort_order=existing_count,
        **fields,
    )
    db.add(record)
    db.commit()
    return get_digital_presence_links(db, booking_id=booking_id, lead=lead)


def update_digital_presence_link(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    link_id: int,
    payload: DigitalPresenceLinkInput,
) -> DigitalPresenceLinksResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_link(db, link_id=link_id, lead_id=lead_id, booking_id=booking_id)
    fields = _validate_link_input(payload)

    record.platform_name = fields["platform_name"]
    record.url = fields["url"]
    record.category = fields["category"]
    record.admission_value_note = fields["admission_value_note"]
    record.updated_at = utc_now()
    db.commit()
    return get_digital_presence_links(db, booking_id=booking_id, lead=lead)


def delete_digital_presence_link(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    link_id: int,
) -> DigitalPresenceLinksResponse:
    lead_id = lead.id if lead else None
    record = _get_owned_link(db, link_id=link_id, lead_id=lead_id, booking_id=booking_id)
    db.delete(record)
    db.commit()
    return get_digital_presence_links(db, booking_id=booking_id, lead=lead)
