from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.education_major import EducationMajor
from app.models.lead import Lead, LeadChannel, LeadStage
from app.models.students_master import StudentsMaster
from app.schemas.express_lead import ExpressLeadCreate
from app.services.countries import get_country_by_iso2
from app.services.phone_utils import digits_only, find_lead_by_phone

EXPRESS_SOURCE = "EXPRESS"

_SOURCE_LABELS = {
    "EXPRESS": "Express Lead",
    "OFFLINE": "Offline Lead",
    "FACEBOOK_LEAD": "Facebook",
    "INSTAGRAM_LEAD": "Instagram",
    "WHATSAPP": "WhatsApp",
    "GOOGLE_ADS": "Google Ads",
    "EMAIL": "Email",
}


def _compose_full_name(first: str, last: str) -> str:
    return " ".join(part.strip().title() for part in (first, last) if part and part.strip())


def _format_phone(db: Session, iso2: str, local: str) -> str:
    country = get_country_by_iso2(db, iso2)
    if not country:
        raise HTTPException(status_code=400, detail="Select a valid phone country code.")
    return f"+{country.dial_code}{local}"


def _express_email(email: str | None, phone: str) -> str:
    if email and str(email).strip():
        return str(email).strip().lower()
    phone_slug = re.sub(r"\D", "", phone) or "unknown"
    return f"express_{phone_slug}@edutrust.nexus"


def _status_label(lead: Lead) -> str:
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    if lead.is_human_locked or "HANDOFF" in stage.upper():
        return "Handoff"
    if "ARCHIVE" in stage.upper():
        return "Archive"
    return "AI Active"


def _directory_for_lead(lead: Lead) -> tuple[str, str]:
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    stage_u = stage.upper()
    source = str(lead.source or "").upper()
    if "ARCHIVE" in stage_u:
        return "/archive", "Archive"
    if bool(getattr(lead, "is_human_locked", False)) or "HANDOFF" in stage_u:
        return "/handoffs", "Handoffs"
    if source in {"OFFLINE", "EXPRESS"}:
        return "/offline-leads", "Offline Leads"
    return "/ai-active", "AI Active"


def _source_label(lead: Lead) -> str:
    source = str(getattr(lead, "source", None) or "").strip()
    if source:
        return _SOURCE_LABELS.get(source.upper(), source.replace("_", " ").title())
    channel = getattr(lead, "channel", None)
    channel_value = channel.value if hasattr(channel, "value") else str(channel or "")
    if channel_value:
        return _SOURCE_LABELS.get(channel_value.upper(), channel_value.replace("_", " ").title())
    return "Lead"


def serialize_express_match(lead: Lead, matched_on: str) -> dict[str, Any]:
    page_path, page_label = _directory_for_lead(lead)
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    created = getattr(lead, "created_at", None)
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "matched_on": matched_on,
        "stage": stage,
        "status_label": _status_label(lead),
        "source": str(getattr(lead, "source", None) or "") or None,
        "source_label": _source_label(lead),
        "preferred_country": str(getattr(lead, "preferred_country", None) or "") or None,
        "academic_summary": str(getattr(lead, "academic_summary", None) or "") or None,
        "created_at": created.isoformat() if created else None,
        "record_kind": "lead",
        "students_master_id": None,
        "lead_id": lead.id,
        "page_path": page_path,
        "page_label": page_label,
        "prospects_path": f"/prospects/{lead.id}",
    }


def _students_master_display_name(record: StudentsMaster) -> str:
    parts = [
        (record.first_name or "").strip(),
        (record.middle_name or "").strip(),
        (record.last_name or "").strip(),
    ]
    name = " ".join(part for part in parts if part)
    return name or "Students Master record"


def serialize_students_master_match(record: StudentsMaster, matched_on: str) -> dict[str, Any]:
    lead_id = getattr(record, "lead_id", None)
    created = getattr(record, "created_at", None)
    academic = ", ".join(
        part
        for part in (
            str(getattr(record, "major", None) or "").strip(),
            str(getattr(record, "university", None) or "").strip(),
        )
        if part
    )
    prospects_path = f"/prospects/{lead_id}" if lead_id else "/prospects"
    return {
        "id": record.id,
        "full_name": _students_master_display_name(record),
        "email": record.email,
        "phone_number": record.phone_number or record.phone_local,
        "matched_on": matched_on,
        "stage": "",
        "status_label": "Students Master",
        "source": "STUDENTS_MASTER",
        "source_label": "Students Master",
        "preferred_country": str(getattr(record, "target_destination_iso2", None) or "") or None,
        "academic_summary": academic or None,
        "created_at": created.isoformat() if created else None,
        "record_kind": "students_master",
        "students_master_id": record.id,
        "lead_id": lead_id,
        "page_path": prospects_path,
        "page_label": "Students Master",
        "prospects_path": prospects_path,
    }


def _find_email_students_master(db: Session, email: str) -> StudentsMaster | None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(StudentsMaster)
        .filter(func.lower(StudentsMaster.email) == normalized)
        .first()
    )


def _find_phone_students_master(
    db: Session, formatted_phone: str, local_digits: str
) -> StudentsMaster | None:
    digits = digits_only(formatted_phone) or local_digits
    suffix = digits[-10:] if len(digits) >= 10 else local_digits
    filters = []
    if local_digits:
        filters.extend(
            [
                StudentsMaster.phone_local == local_digits,
                StudentsMaster.phone_local_secondary == local_digits,
            ]
        )
    if formatted_phone:
        filters.extend(
            [
                StudentsMaster.phone_number == formatted_phone,
                StudentsMaster.phone_number_secondary == formatted_phone,
            ]
        )
    if suffix:
        like = f"%{suffix}"
        filters.extend(
            [
                StudentsMaster.phone_number.ilike(like),
                StudentsMaster.phone_number_secondary.ilike(like),
            ]
        )
    if not filters:
        return None
    return db.query(StudentsMaster).filter(or_(*filters)).first()


def resolve_express_study_interest(
    db: Session, payload: ExpressLeadCreate
) -> dict[str, Any]:
    iso2s = list(payload.target_destination_iso2s or [])
    destination_names: list[str] = []
    for iso2 in iso2s:
        country = get_country_by_iso2(db, iso2)
        if not country:
            raise HTTPException(
                status_code=400,
                detail=f"Select a valid target country ({iso2}).",
            )
        destination_names.append(country.name)

    major_ids = list(payload.target_major_ids or [])
    resolved_ids: list[int] = []
    resolved_names: list[str] = []
    if major_ids:
        majors = (
            db.query(EducationMajor)
            .filter(
                EducationMajor.id.in_(major_ids),
                EducationMajor.is_active.is_(True),
                EducationMajor.program_id.is_(None),
            )
            .all()
        )
        majors_by_id = {major.id: major for major in majors}
        if len(majors_by_id) != len(set(major_ids)):
            raise HTTPException(status_code=400, detail="Select a valid target program.")
        for major_id in major_ids:
            major = majors_by_id[major_id]
            resolved_ids.append(major.id)
            resolved_names.append(str(major.label))

    destination_label = ", ".join(destination_names)
    majors_label = ", ".join(resolved_names)
    return {
        "target_destination_iso2s": iso2s,
        "target_destinations": destination_names,
        "target_destination_iso2": iso2s[0] if iso2s else None,
        "target_destination": destination_label or None,
        "target_major_ids": resolved_ids,
        "target_majors": resolved_names,
        "target_program_codes": [],
        "target_programs": resolved_names,
        "target_program_code": None,
        "target_program": majors_label or None,
    }


def _find_email_lead(db: Session, email: str) -> Lead | None:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(Lead)
        .filter(func.lower(Lead.email) == normalized)
        .first()
    )


def check_express_lead_duplicates(
    db: Session,
    *,
    email: str,
    phone_country_iso2: str,
    phone_local: str,
) -> dict[str, Any]:
    email_match = None
    normalized_email = (email or "").strip().lower()
    if normalized_email and "@" in normalized_email:
        existing = _find_email_lead(db, normalized_email)
        if existing:
            email_match = serialize_express_match(existing, "email")
        else:
            master = _find_email_students_master(db, normalized_email)
            if master:
                email_match = serialize_students_master_match(master, "email")

    phone_match = None
    local_digits = re.sub(r"\D", "", phone_local or "")
    if phone_country_iso2 and len(local_digits) == 10:
        phone = _format_phone(db, phone_country_iso2, local_digits)
        existing_phone = find_lead_by_phone(db, phone) or db.query(Lead).filter(
            Lead.phone_number == phone
        ).first()
        if existing_phone:
            phone_match = serialize_express_match(existing_phone, "phone")
        else:
            master = _find_phone_students_master(db, phone, local_digits)
            if master:
                phone_match = serialize_students_master_match(master, "phone")

    return {"email_match": email_match, "phone_match": phone_match}


def create_express_lead(db: Session, payload: ExpressLeadCreate) -> Lead:
    phone = _format_phone(db, payload.phone_country_iso2, payload.phone_local)
    email = _express_email(payload.email, phone)

    duplicates = check_express_lead_duplicates(
        db,
        email=str(payload.email or ""),
        phone_country_iso2=payload.phone_country_iso2,
        phone_local=payload.phone_local,
    )
    matches = [row for row in (duplicates["email_match"], duplicates["phone_match"]) if row]
    if matches:
        unique: dict[tuple[str, int], dict[str, Any]] = {}
        for row in matches:
            key = (str(row.get("record_kind") or "lead"), int(row["id"]))
            existing = unique.get(key)
            if existing and existing.get("matched_on") != row.get("matched_on"):
                existing["matched_on"] = "both"
            else:
                unique[key] = dict(row)
        merged = list(unique.values())
        first = merged[0]
        matched_on = str(first.get("matched_on") or "")
        if len(merged) > 1:
            message = (
                "These details match existing students. "
                "Review the matched records below instead of creating another lead."
            )
        elif matched_on == "both":
            message = (
                f"{first['full_name']} already exists — this email and phone are already registered. "
                f"Open {first['page_label']} or All Prospects to review this lead."
            )
        elif matched_on == "email":
            message = (
                f"{first['full_name']} already exists — this email is already registered. "
                f"Open {first['page_label']} or All Prospects to review this lead."
            )
        else:
            message = (
                f"{first['full_name']} already exists — this phone number is already registered. "
                f"Open {first['page_label']} or All Prospects to review this lead."
            )
        raise HTTPException(
            status_code=409,
            detail={"message": message, "matches": merged},
        )

    # Synthetic emails must still be unique at the DB layer.
    if _find_email_lead(db, email):
        raise HTTPException(status_code=409, detail="A lead with this email already exists.")

    study = resolve_express_study_interest(db, payload)
    full_name = _compose_full_name(payload.first_name, payload.last_name)
    additional: dict[str, Any] = {
        "entry_type": "express",
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
        "phone_country_iso2": payload.phone_country_iso2,
    }
    additional.update(study)

    majors = study.get("target_majors") or []
    academic_summary = ", ".join(str(item) for item in majors) if majors else None

    lead = Lead(
        full_name=full_name,
        email=email,
        phone_number=phone,
        channel=LeadChannel.OFFLINE,
        source=EXPRESS_SOURCE,
        stage=LeadStage.AI_ACTIVE,
        is_human_locked=False,
        preferred_country=str(study.get("target_destination") or "")[:100] or None,
        academic_summary=academic_summary,
        additional_data=additional,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    from app.services.student_status_service import on_lead_created

    on_lead_created(db, lead, source="Express Leads")
    return lead


def build_express_lead_response(lead: Lead) -> dict[str, Any]:
    extra = lead.additional_data if isinstance(lead.additional_data, dict) else {}
    stage = lead.stage.value if hasattr(lead.stage, "value") else str(lead.stage or "")
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "stage": stage,
        "source": lead.source,
        "target_destination_iso2s": extra.get("target_destination_iso2s") or [],
        "target_destinations": extra.get("target_destinations") or [],
        "target_major_ids": extra.get("target_major_ids") or [],
        "target_majors": extra.get("target_majors") or extra.get("target_programs") or [],
    }
