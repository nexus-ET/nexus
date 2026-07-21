from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.services.countries import get_country_by_iso2, list_active_countries
from app.services.lead_study_interest import resolve_lead_study_interest


def _extract_additional(lead: Lead) -> dict[str, Any]:
    raw = getattr(lead, "additional_data", None)
    return raw if isinstance(raw, dict) else {}


def _load_intake_context(lead: Lead) -> dict[str, Any]:
    raw = getattr(lead, "intake_context", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, (str, bytes, bytearray)):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _split_full_name(full_name: str) -> tuple[str | None, str | None, str | None]:
    parts = [part for part in (full_name or "").split() if part.strip()]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _resolve_country_iso2(db: Session, iso2: str | None, name: str | None) -> str | None:
    if iso2 and iso2.strip():
        normalized = iso2.strip().upper()
        if get_country_by_iso2(db, normalized):
            return normalized
    if not name or not name.strip():
        return None
    token = name.strip().lower()
    for country in list_active_countries(db):
        if country.name.lower() == token:
            return country.iso2
    return None


def _parse_stored_phone(db: Session, stored: str | None) -> tuple[str | None, str | None]:
    trimmed = (stored or "").strip()
    if not trimmed:
        return None, None

    countries = sorted(list_active_countries(db), key=lambda item: len(item.dial_code), reverse=True)
    if trimmed.startswith("+"):
        digits = re.sub(r"\D", "", trimmed[1:])
        for country in countries:
            dial = country.dial_code
            if digits.startswith(dial) and len(digits) == len(dial) + 10:
                return country.iso2, digits[len(dial) :]

    digits = re.sub(r"\D", "", trimmed)
    if len(digits) == 10:
        return None, digits
    if len(digits) > 10:
        return None, digits[-10:]
    return None, digits or None


def _mask_offline_email(email: str | None) -> str | None:
    if not email:
        return None
    normalized = email.strip().lower()
    if normalized.endswith("@edutrust.nexus"):
        return None
    return email.strip()


def _normalize_date_of_birth(value: Any) -> str | None:
    if value is None:
        return None
    from datetime import date as date_type

    if isinstance(value, date_type):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def _empty_profile() -> dict[str, Any]:
    return {
        "lead_id": None,
        "first_name": None,
        "middle_name": None,
        "last_name": None,
        "date_of_birth": None,
        "email": None,
        "phone_country_iso2": None,
        "phone_local": None,
        "phone_number": None,
        "phone_country_iso2_secondary": None,
        "phone_local_secondary": None,
        "phone_number_secondary": None,
        "location": {
            "address1": None,
            "address2": None,
            "address3": None,
            "city": None,
            "state": None,
            "country_iso2": None,
            "country": None,
            "zipcode": None,
        },
        "education": {
            "degree_code": None,
            "degree": None,
            "degree_other": None,
            "major": None,
            "university": None,
            "graduation_year": None,
            "gpa_cgpa_code": None,
            "gpa_cgpa": None,
            "gpa_cgpa_other": None,
        },
        "study_interest": {
            "target_destination_iso2": None,
            "target_destination": None,
            "target_program_code": None,
            "target_program": None,
            "target_course_code": None,
            "target_course": None,
        },
        "aptitude_scores": {
            "english_test_scores": None,
            "gre_score": None,
            "gmat_score": None,
        },
    }


def _coalesce_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def apply_booking_contact_overrides(profile: dict[str, Any], booking: Any) -> dict[str, Any]:
    """Fill profile gaps from the counselling booking record."""
    candidate_name = _coalesce_text(getattr(booking, "candidate_name", None))
    if candidate_name and not _coalesce_text(profile.get("first_name"), profile.get("last_name")):
        first_name, middle_name, last_name = _split_full_name(candidate_name)
        profile["first_name"] = profile.get("first_name") or first_name
        profile["middle_name"] = profile.get("middle_name") or middle_name
        profile["last_name"] = profile.get("last_name") or last_name

    email = _coalesce_text(getattr(booking, "candidate_email", None))
    if email and not profile.get("email"):
        profile["email"] = email

    phone = _coalesce_text(getattr(booking, "candidate_phone", None))
    if phone and not profile.get("phone_number"):
        profile["phone_number"] = phone

    return profile


def build_candidate_profile(db: Session, lead: Lead | None, booking: Any | None = None) -> dict[str, Any]:
    if lead is None:
        profile = _empty_profile()
        if booking is not None:
            return apply_booking_contact_overrides(profile, booking)
        return profile

    extra = _extract_additional(lead)
    context = _load_intake_context(lead)
    education = extra.get("education") if isinstance(extra.get("education"), dict) else {}
    location = extra.get("location") if isinstance(extra.get("location"), dict) else {}
    study = resolve_lead_study_interest(lead)

    first_name = extra.get("first_name")
    middle_name = extra.get("middle_name")
    last_name = extra.get("last_name")
    if not first_name and not last_name:
        first_name, middle_name, last_name = _split_full_name(lead.full_name or "")

    phone_country_iso2 = extra.get("phone_country_iso2")
    inferred_iso2, parsed_local = _parse_stored_phone(db, lead.phone_number)
    phone_local = parsed_local
    if not phone_country_iso2:
        phone_country_iso2 = inferred_iso2

    secondary_country_iso2 = extra.get("phone_country_iso2_secondary")
    secondary_local = extra.get("phone_local_secondary") or extra.get("phone_secondary_local")
    secondary_number = extra.get("phone_number_secondary") or extra.get("phone_secondary")

    target_destination_iso2 = extra.get("target_destination_iso2")
    if not target_destination_iso2:
        target_destination_iso2 = _resolve_country_iso2(
            db,
            None,
            extra.get("target_destination") or study.get("country") or lead.preferred_country,
        )

    location_country_iso2 = location.get("country_iso2")
    location_country_name = location.get("country")
    if not location_country_iso2:
        location_country_iso2 = _resolve_country_iso2(
            db,
            None,
            location_country_name or _country_from_current_location(lead.current_location),
        )
    if not location_country_name and location_country_iso2:
        country = get_country_by_iso2(db, str(location_country_iso2))
        location_country_name = country.name if country else None
    if not location_country_name:
        location_country_name = _country_from_current_location(lead.current_location)

    target_degree = str(context.get("target_degree") or "").strip()
    target_major = str(context.get("target_major") or "").strip()
    degree = education.get("degree") or None
    degree_code = education.get("degree_code")
    major = education.get("major") or None

    target_program = extra.get("target_program") or study.get("program") or target_degree or None
    target_course = extra.get("target_course") or study.get("course") or None
    if not target_course and target_major:
        target_course = target_major

    profile = {
        "lead_id": lead.id,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "date_of_birth": _normalize_date_of_birth(extra.get("date_of_birth")),
        "email": _mask_offline_email(lead.email),
        "phone_country_iso2": phone_country_iso2,
        "phone_local": phone_local,
        "phone_number": lead.phone_number,
        "phone_country_iso2_secondary": secondary_country_iso2,
        "phone_local_secondary": secondary_local,
        "phone_number_secondary": secondary_number,
        "location": {
            "address1": location.get("address1") or location.get("address_1"),
            "address2": location.get("address2") or location.get("address_2"),
            "address3": location.get("address3") or location.get("address_3"),
            "city": location.get("city") or _city_from_current_location(lead.current_location),
            "state": location.get("state") or _state_from_current_location(lead.current_location),
            "country_iso2": location_country_iso2,
            "country": location_country_name,
            "zipcode": location.get("zipcode") or location.get("zip_code") or location.get("postal_code"),
        },
        "education": {
            "degree_code": degree_code,
            "degree": degree,
            "degree_other": education.get("degree_other"),
            "major": major,
            "university": education.get("university"),
            "graduation_year": education.get("graduation_year"),
            "gpa_cgpa_code": education.get("gpa_cgpa_code"),
            "gpa_cgpa": education.get("gpa_cgpa"),
            "gpa_cgpa_other": education.get("gpa_cgpa_other"),
        },
        "study_interest": {
            "target_destination_iso2": target_destination_iso2,
            "target_destination": extra.get("target_destination") or study.get("country") or lead.preferred_country,
            "target_program_code": extra.get("target_program_code"),
            "target_program": target_program,
            "target_course_code": extra.get("target_course_code"),
            "target_course": target_course,
        },
        "aptitude_scores": {
            "english_test_scores": getattr(lead, "english_test_scores", None),
            "gre_score": getattr(lead, "gre_score", None),
            "gmat_score": getattr(lead, "gmat_score", None),
        },
    }

    if booking is not None:
        profile = apply_booking_contact_overrides(profile, booking)
        if not profile["phone_local"] and profile.get("phone_number"):
            inferred_iso2, parsed_local = _parse_stored_phone(db, profile["phone_number"])
            profile["phone_local"] = parsed_local
            if not profile["phone_country_iso2"]:
                profile["phone_country_iso2"] = inferred_iso2

    return profile


def _city_from_current_location(current_location: str | None) -> str | None:
    if not current_location or not current_location.strip():
        return None
    parts = [part.strip() for part in current_location.split(",") if part.strip()]
    return parts[0] if parts else None


def _state_from_current_location(current_location: str | None) -> str | None:
    if not current_location or not current_location.strip():
        return None
    parts = [part.strip() for part in current_location.split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[1]
    return None


def _country_from_current_location(current_location: str | None) -> str | None:
    if not current_location or not current_location.strip():
        return None
    parts = [part.strip() for part in current_location.split(",") if part.strip()]
    if len(parts) >= 3:
        return parts[2]
    if len(parts) == 2:
        return parts[1]
    return None
