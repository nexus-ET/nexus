from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.lead import Lead

_COUNTRY_KEYS = (
    "preferred_country",
    "target_destination",
    "destination_country",
    "country",
    "study_destination",
)

_COURSE_KEYS = (
    "preferred_course",
    "target_course",
    "preferred_course_university",
    "course",
    "course_or_program",
    "program_of_interest",
    "intended_course",
)

_PROGRAM_KEYS = (
    "target_program",
    "preferred_program",
    "program",
    "study_program",
)


def _lead_additional(lead: Lead) -> dict[str, Any]:
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


def _extra_value(extra: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_country(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    from app.services.admissions_intake_flow import _normalize_country_name

    token = str(raw).strip()
    return _normalize_country_name(token) or token.title()


def resolve_lead_study_interest(lead: Lead) -> dict[str, str | None]:
    """Resolve target country / course / program from lead columns and Meta additional_data."""
    extra = _lead_additional(lead)
    context = _load_intake_context(lead)

    country_raw = (
        (getattr(lead, "preferred_country", None) or "").strip()
        or _extra_value(extra, *_COUNTRY_KEYS)
        or str(context.get("pending_country") or "").strip()
    )
    country = _normalize_country(country_raw) if country_raw else None

    course = (
        str(context.get("preferred_course") or "").strip()
        or _extra_value(extra, *_COURSE_KEYS)
    ) or None

    program = (
        str(context.get("target_program") or "").strip()
        or _extra_value(extra, *_PROGRAM_KEYS)
    ) or None
    if not program and course:
        program = course
    target_degree = str(context.get("target_degree") or "").strip()
    target_major = str(context.get("target_major") or "").strip()
    if not course and program and not (target_degree and not target_major):
        course = program

    return {
        "country": country,
        "course": course,
        "program": program,
    }


def lead_has_complete_study_interest(lead: Lead) -> bool:
    study = resolve_lead_study_interest(lead)
    return bool(study.get("country") and (study.get("course") or study.get("program")))


def build_target_intake_task(lead: Lead) -> str:
    """Build WhatsApp intake task for the target-country step based on prefilled Meta fields."""
    study = resolve_lead_study_interest(lead)
    country = (study.get("country") or "").strip()
    course = (study.get("course") or study.get("program") or "").strip()
    if country and not course:
        return (
            "INTAKE_STEP=TARGET; Country noted but course/program missing. "
            f"Pending country: {country}. Ask only for course/program."
        )
    if course and not country:
        return (
            "INTAKE_STEP=TARGET; Course/program noted but destination country missing. "
            f"Pending course/program: {course}. Ask only for destination country."
        )
    return "INTAKE_STEP=TARGET; Ask which destination country and course/program they want to study."


def enrich_lead_payload_from_meta_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Promote Meta form answers into top-level lead columns when present."""
    additional = payload.get("additional_data")
    if not isinstance(additional, dict):
        return payload

    country = _extra_value(additional, *_COUNTRY_KEYS)
    course = _extra_value(additional, *_COURSE_KEYS)
    program = _extra_value(additional, *_PROGRAM_KEYS)

    if country and not payload.get("preferred_country"):
        payload["preferred_country"] = _normalize_country(country)

    context: dict[str, Any] = {}
    if course:
        context["preferred_course"] = course
    if program:
        context["target_program"] = program
    elif course:
        context["target_program"] = course

    if context:
        payload["intake_context"] = json.dumps(context)

    return payload


def hydrate_lead_study_interest(
    db: Session,
    lead: Lead,
    *,
    commit: bool = False,
) -> bool:
    """Copy Meta / offline study-interest fields onto lead columns used by intake + UI."""
    study = resolve_lead_study_interest(lead)
    changed = False

    if study.get("country") and not (lead.preferred_country or "").strip():
        lead.preferred_country = study["country"]
        changed = True

    context = _load_intake_context(lead)
    if study.get("course") and not str(context.get("preferred_course") or "").strip():
        context["preferred_course"] = study["course"]
        changed = True
    if study.get("program") and not str(context.get("target_program") or "").strip():
        context["target_program"] = study["program"]
        changed = True

    if changed:
        lead.intake_context = json.dumps(context) if context else None

    if commit and changed:
        db.commit()
        db.refresh(lead)

    return changed


def clear_study_interest_sources(lead: Lead) -> None:
    """Remove study-interest answers so intake/profile cannot resurface them after a chat reset."""
    lead.preferred_country = None
    if not isinstance(lead.additional_data, dict):
        return

    drop_keys = {
        *_COUNTRY_KEYS,
        *_COURSE_KEYS,
        *_PROGRAM_KEYS,
        "target_degree",
        "target_major",
        "pending_country",
    }
    cleaned = {key: value for key, value in lead.additional_data.items() if key not in drop_keys}
    lead.additional_data = cleaned or None


def study_interest_profile_fields(lead: Lead) -> dict[str, Any]:
    study = resolve_lead_study_interest(lead)
    context = _load_intake_context(lead)
    target_degree = str(context.get("target_degree") or "").strip()
    target_major = str(context.get("target_major") or "").strip()
    if target_degree:
        return {
            "preferred_country": study.get("country") or getattr(lead, "preferred_country", None),
            "preferred_course": target_major or None,
            "target_program": target_degree,
            "study_interest_complete": lead_has_complete_study_interest(lead),
        }
    return {
        "preferred_country": study.get("country") or getattr(lead, "preferred_country", None),
        "preferred_course": study.get("course"),
        "target_program": study.get("program"),
        "study_interest_complete": lead_has_complete_study_interest(lead),
    }
