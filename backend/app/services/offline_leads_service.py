from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, asc, cast, desc, or_, text
from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadChannel, LeadStage
from app.schemas.offline_lead import OfflineLeadCreate, SortDirection, SortField
from app.services.countries import get_country_by_iso2
from app.services.education_degrees import resolve_education_payload
from app.services.target_programs import resolve_study_interest_fields

OFFLINE_SOURCE = "OFFLINE"
EXPRESS_SOURCE = "EXPRESS"

SORT_COLUMNS: dict[SortField, Any] = {
    "full_name": Lead.full_name,
    "created_at": Lead.created_at,
    "email": Lead.email,
    "phone_number": Lead.phone_number,
}


def _compose_full_name(first: str, middle: str | None, last: str) -> str:
    parts = [first.strip().title(), (middle or "").strip().title(), last.strip().title()]
    return " ".join(part for part in parts if part)


def _compute_age(dob_str: str | None) -> int | None:
    if not dob_str:
        return None
    try:
        dob = date.fromisoformat(dob_str)
    except ValueError:
        return None
    today = date.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


def _format_phone(db: Session, iso2: str, local: str) -> str:
    country = get_country_by_iso2(db, iso2)
    if not country:
        raise HTTPException(status_code=400, detail="Select a valid phone country code.")
    return f"+{country.dial_code}{local}"


def _offline_email(payload: OfflineLeadCreate, phone: str) -> str:
    if payload.email:
        return str(payload.email).strip().lower()
    phone_slug = re.sub(r"\D", "", phone) or "unknown"
    return f"offline_{phone_slug}@edutrust.nexus"


def _resolve_country_name(db: Session, iso2: str | None) -> str | None:
    if not iso2:
        return None
    country = get_country_by_iso2(db, iso2)
    return country.name if country else iso2


def _build_location_string(db: Session, payload: OfflineLeadCreate) -> str | None:
    if not payload.location:
        return None
    loc = payload.location
    country_name = _resolve_country_name(db, loc.country_iso2)
    city_state = ", ".join(
        p.strip() for p in (loc.city, loc.state) if p and p.strip()
    )
    if loc.zip_code and loc.zip_code.strip():
        city_state = f"{city_state} {loc.zip_code.strip()}" if city_state else loc.zip_code.strip()
    parts = [p for p in (city_state, country_name) if p]
    return ", ".join(parts) if parts else None


def _build_academic_summary(db: Session, payload: OfflineLeadCreate) -> str | None:
    bits: list[str] = []
    study_interest = resolve_study_interest_fields(db, payload)
    programs = study_interest.get("target_programs") or []
    if isinstance(programs, list) and programs:
        bits.append(", ".join(str(item) for item in programs))
    elif study_interest.get("target_program"):
        bits.append(str(study_interest["target_program"]))
    if payload.education:
        edu = resolve_education_payload(db, payload.education)
        if edu and (edu.get("program") or edu.get("degree")):
            program = str(edu.get("program") or edu.get("degree"))
            if program not in bits:
                bits.append(program)
    return " — ".join(bits) if bits else None


def _build_additional_data(db: Session, payload: OfflineLeadCreate) -> dict[str, Any]:
    data: dict[str, Any] = {
        "entry_type": "offline",
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
    }
    if payload.middle_name and payload.middle_name.strip():
        data["middle_name"] = payload.middle_name.strip()
    data["phone_country_iso2"] = payload.phone_country_iso2
    if payload.date_of_birth:
        data["date_of_birth"] = payload.date_of_birth.isoformat()
    if payload.education:
        edu = resolve_education_payload(db, payload.education)
        if edu:
            data["education"] = edu
    loc = payload.location.model_dump()
    if not get_country_by_iso2(db, loc["country_iso2"]):
        raise HTTPException(status_code=400, detail="Select a valid location country.")
    loc["country"] = _resolve_country_name(db, loc["country_iso2"])
    data["location"] = loc
    data.update(resolve_study_interest_fields(db, payload))
    return data


def _status_label(lead: Lead) -> str:
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    if lead.is_human_locked or "HANDOFF" in stage.upper():
        return "Handoff"
    if "ARCHIVE" in stage.upper():
        return "Archive"
    return "AI Active"


def _extract_additional(lead: Lead) -> dict[str, Any]:
    raw = getattr(lead, "additional_data", None)
    return raw if isinstance(raw, dict) else {}


def build_offline_lead_list_item(lead: Lead, db: Session | None = None) -> dict[str, Any]:
    extra = _extract_additional(lead)
    education = extra.get("education") if isinstance(extra.get("education"), dict) else {}
    location = extra.get("location") if isinstance(extra.get("location"), dict) else {}
    dob = extra.get("date_of_birth")
    country_iso2 = location.get("country_iso2")
    country_name = location.get("country")
    if db and country_iso2 and not country_name:
        country_name = _resolve_country_name(db, country_iso2)

    first_name = extra.get("first_name")
    middle_name = extra.get("middle_name")
    last_name = extra.get("last_name")
    if not first_name and not last_name and lead.full_name:
        parts = lead.full_name.split()
        if parts:
            first_name = parts[0]
            if len(parts) > 2:
                middle_name = " ".join(parts[1:-1])
                last_name = parts[-1]
            elif len(parts) == 2:
                last_name = parts[1]

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone_country_iso2": extra.get("phone_country_iso2"),
        "stage": lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage),
        "status_label": _status_label(lead),
        "source": lead.source or OFFLINE_SOURCE,
        "target_destination": extra.get("target_destination") or lead.preferred_country,
        "target_destination_iso2": extra.get("target_destination_iso2"),
        "target_destination_iso2s": list(extra.get("target_destination_iso2s") or (
            [extra["target_destination_iso2"]] if extra.get("target_destination_iso2") else []
        )),
        "target_destinations": list(extra.get("target_destinations") or (
            [extra["target_destination"]] if extra.get("target_destination") else []
        )),
        "target_level_id": extra.get("target_level_id"),
        "target_level_name": extra.get("target_level_name"),
        "target_major_ids": list(extra.get("target_major_ids") or []),
        "target_majors": list(extra.get("target_majors") or []),
        "target_program_codes": list(extra.get("target_program_codes") or (
            [extra["target_program_code"]] if extra.get("target_program_code") else []
        )),
        "target_programs": list(extra.get("target_programs") or (
            [extra["target_program"]] if extra.get("target_program") else []
        )),
        "target_program": extra.get("target_program"),
        "target_program_code": extra.get("target_program_code"),
        "target_course": extra.get("target_course") or lead.academic_summary,
        "target_course_code": extra.get("target_course_code"),
        "city": location.get("city"),
        "state": location.get("state"),
        "zip_code": location.get("zip_code"),
        "country": country_name,
        "country_iso2": country_iso2,
        "degree": education.get("degree"),
        "degree_code": education.get("degree_code"),
        "program": education.get("program") or education.get("degree"),
        "program_code": education.get("program_code") or education.get("degree_code"),
        "level_id": education.get("level_id"),
        "full_time_study_years": education.get("full_time_study_years"),
        "major": education.get("major"),
        "university": education.get("university"),
        "graduation_year": education.get("graduation_year"),
        "gpa_cgpa": education.get("gpa_cgpa"),
        "gpa_cgpa_code": education.get("gpa_cgpa_code"),
        "date_of_birth": dob,
        "age": _compute_age(dob if isinstance(dob, str) else None),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "booking_count": 0,
    }


def _base_offline_query(db: Session):
    return db.query(Lead).filter(
        or_(
            Lead.source == OFFLINE_SOURCE,
            Lead.source == EXPRESS_SOURCE,
            Lead.channel == LeadChannel.OFFLINE,
        )
    )


def _apply_status_filter(query, status: str | None):
    normalized = (status or "ALL").strip().upper().replace("-", "_").replace(" ", "_")
    if normalized in {"", "ALL", "ALL_PROSPECTS"}:
        return query
    if normalized in {"AI_ACTIVE", "AIACTIVE"}:
        return query.filter(
            cast(Lead.stage, String).ilike("%AI_ACTIVE%"),
            Lead.is_human_locked.is_(False),
        )
    if normalized == "HANDOFF":
        return query.filter(
            or_(
                cast(Lead.stage, String).ilike("%HANDOFF%"),
                Lead.is_human_locked.is_(True),
            )
        )
    if normalized == "ARCHIVE":
        return query.filter(cast(Lead.stage, String).ilike("%ARCHIVE%"))
    return query


def _count_bookings_for_lead_ids(db: Session, lead_ids: list[int]) -> dict[int, int]:
    """Count counselling bookings per lead without loading ORM relationship graphs."""
    if not lead_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT lead_id, COUNT(*)::int AS booking_count
            FROM counselling_bookings
            WHERE lead_id = ANY(:lead_ids)
              AND admin_id IS NOT NULL
            GROUP BY lead_id
            """
        ),
        {"lead_ids": lead_ids},
    ).all()
    return {int(lead_id): int(count) for lead_id, count in rows if lead_id is not None}


def list_offline_leads(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    status: str | None = None,
    sort_by: SortField = "created_at",
    sort_dir: SortDirection = "desc",
) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    query = _base_offline_query(db)

    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Lead.full_name.ilike(term),
                Lead.email.ilike(term),
                Lead.phone_number.ilike(term),
            )
        )

    query = _apply_status_filter(query, status)

    total = query.count()
    total_pages = max(1, math.ceil(total / safe_page_size)) if total else 1
    if safe_page > total_pages and total > 0:
        safe_page = total_pages

    sort_col = SORT_COLUMNS.get(sort_by, Lead.created_at)
    ordering = asc(sort_col) if sort_dir == "asc" else desc(sort_col)
    if sort_by != "created_at":
        query = query.order_by(ordering, Lead.id.desc())
    else:
        query = query.order_by(ordering, Lead.id.desc())

    offset = (safe_page - 1) * safe_page_size
    rows = query.offset(offset).limit(safe_page_size).all()

    booking_counts = _count_bookings_for_lead_ids(db, [row.id for row in rows])
    items = []
    for row in rows:
        item = build_offline_lead_list_item(row, db)
        item["booking_count"] = booking_counts.get(row.id, 0)
        items.append(item)

    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": total_pages,
    }


def create_offline_lead(db: Session, payload: OfflineLeadCreate) -> Lead:
    phone = _format_phone(db, payload.phone_country_iso2, payload.phone_local)
    email = _offline_email(payload, phone)

    existing_email = db.query(Lead.id).filter(Lead.email == email).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="A lead with this email already exists.")

    if phone:
        existing_phone = db.query(Lead.id).filter(Lead.phone_number == phone).first()
        if existing_phone:
            raise HTTPException(status_code=409, detail="A lead with this phone number already exists.")

    if payload.location.country_iso2:
        if not get_country_by_iso2(db, payload.location.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")

    full_name = _compose_full_name(payload.first_name, payload.middle_name, payload.last_name)
    location_str = _build_location_string(db, payload)
    academic_summary = _build_academic_summary(db, payload)
    study_interest = resolve_study_interest_fields(db, payload)

    lead = Lead(
        full_name=full_name,
        email=email,
        phone_number=phone,
        channel=LeadChannel.OFFLINE,
        source=OFFLINE_SOURCE,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        preferred_country=str(study_interest.get("target_destination") or "")[:100] or None,
        academic_summary=academic_summary,
        current_location=location_str,
        additional_data=_build_additional_data(db, payload),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    from app.services.student_status_service import on_lead_created

    on_lead_created(db, lead, source="Offline Leads")
    return lead


def get_offline_lead(db: Session, lead_id: int) -> Lead:
    lead = _base_offline_query(db).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Offline lead not found.")
    return lead


def check_offline_lead_duplicates(
    db: Session,
    *,
    email: str,
    phone_country_iso2: str,
    phone_local: str,
    exclude_lead_id: int | None = None,
) -> dict[str, bool]:
    normalized_email = email.strip().lower()
    email_taken = False
    if normalized_email:
        email_query = db.query(Lead.id).filter(Lead.email == normalized_email)
        if exclude_lead_id:
            email_query = email_query.filter(Lead.id != exclude_lead_id)
        email_taken = email_query.first() is not None

    phone_taken = False
    local_digits = re.sub(r"\D", "", phone_local or "")
    if phone_country_iso2 and len(local_digits) == 10:
        phone = _format_phone(db, phone_country_iso2, local_digits)
        phone_query = db.query(Lead.id).filter(Lead.phone_number == phone)
        if exclude_lead_id:
            phone_query = phone_query.filter(Lead.id != exclude_lead_id)
        phone_taken = phone_query.first() is not None

    return {"email_taken": email_taken, "phone_taken": phone_taken}


def update_offline_lead(db: Session, lead_id: int, payload: OfflineLeadCreate) -> Lead:
    lead = get_offline_lead(db, lead_id)
    phone = _format_phone(db, payload.phone_country_iso2, payload.phone_local)
    email = _offline_email(payload, phone)

    existing_email = (
        db.query(Lead.id).filter(Lead.email == email, Lead.id != lead_id).first()
    )
    if existing_email:
        raise HTTPException(status_code=409, detail="A lead with this email already exists.")

    existing_phone = (
        db.query(Lead.id).filter(Lead.phone_number == phone, Lead.id != lead_id).first()
    )
    if existing_phone:
        raise HTTPException(status_code=409, detail="A lead with this phone number already exists.")

    if payload.location.country_iso2:
        if not get_country_by_iso2(db, payload.location.country_iso2):
            raise HTTPException(status_code=400, detail="Select a valid location country.")

    full_name = _compose_full_name(payload.first_name, payload.middle_name, payload.last_name)
    location_str = _build_location_string(db, payload)
    academic_summary = _build_academic_summary(db, payload)
    study_interest = resolve_study_interest_fields(db, payload)

    extra = _extract_additional(lead)
    merged = {**extra, **_build_additional_data(db, payload)}

    if not payload.middle_name or not payload.middle_name.strip():
        merged.pop("middle_name", None)
    if not payload.date_of_birth:
        merged.pop("date_of_birth", None)
    if not payload.education or not resolve_education_payload(db, payload.education):
        merged.pop("education", None)

    lead.full_name = full_name
    lead.email = email
    lead.phone_number = phone
    lead.preferred_country = str(study_interest.get("target_destination") or "")[:100] or None
    lead.academic_summary = academic_summary
    lead.current_location = location_str
    lead.additional_data = merged

    db.commit()
    db.refresh(lead)
    return lead
