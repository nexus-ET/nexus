"""Extract study level, field, and destination country from WhatsApp intake messages."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

STUDY_PLAN_EXTRACTION_PROMPT = """Act as a Data Extraction AI for my CRM. I am receiving WhatsApp messages from students regarding their study plans. Your goal is to extract three specific entities from their text and normalize them.

Entities to extract:

Level: Normalize to 'Undergraduate' or 'Postgraduate'.

Field: Extract the specific field of study (e.g., 'Business Administration', 'Science').

Location: Normalize to the full country name (e.g., 'USA', 'Japan', 'United Kingdom').

Rules:

If an entity is missing from the user's message, set its value to 'NULL'.

Map variations (e.g., 'UG', 'Bachelors', 'B.S.' -> 'Undergraduate') and ('Masters', 'M.S.', 'MBA' -> 'Postgraduate').

Map location aliases (e.g., 'US', 'U.S.A.' -> 'United States') and ('JP' -> 'Japan').

Output Requirement:
Always return a valid JSON object in this exact format:
{
"level": "Value or NULL",
"field": "Value or NULL",
"location": "Value or NULL",
"status": "complete"
}

Set status to 'complete' if all 3 are found, otherwise 'incomplete'. Do not guess missing values."""


@dataclass(frozen=True)
class StudyPlanExtraction:
    level: str | None
    field: str | None
    location: str | None

    @property
    def status(self) -> str:
        if self.level and self.field and self.location:
            return "complete"
        return "incomplete"

    def to_context(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.level:
            payload["pending_study_level"] = self.level
        if self.field:
            payload["pending_study_field"] = self.field
            payload["pending_program"] = self.field
        if self.location:
            payload["pending_country"] = self.location
        return payload


def _nullish(value: Any) -> bool:
    if value is None:
        return True
    token = str(value).strip()
    if not token:
        return True
    return token.upper() in {"NULL", "NONE", "N/A", "NA", "UNKNOWN"}


def _normalize_level(raw: str | None) -> str | None:
    if _nullish(raw):
        return None
    token = re.sub(r"\s+", " ", str(raw).strip().lower())
    undergraduate = {
        "undergraduate",
        "under grad",
        "undergrad",
        "ug",
        "bachelor",
        "bachelors",
        "bachelor's",
        "bs",
        "b.s.",
        "ba",
        "b.a.",
    }
    postgraduate = {
        "postgraduate",
        "post graduate",
        "postgrad",
        "pg",
        "master",
        "masters",
        "master's",
        "ms",
        "m.s.",
        "msc",
        "m.sc.",
        "ma",
        "m.a.",
        "mba",
        "phd",
        "doctorate",
    }
    if token in undergraduate or any(token.startswith(item + " ") for item in undergraduate):
        return "Undergraduate"
    if token in postgraduate or any(token.startswith(item + " ") for item in postgraduate):
        return "Postgraduate"
    if "undergraduate" in token:
        return "Undergraduate"
    if "postgraduate" in token or "graduate" in token:
        return "Postgraduate"
    return None


def _normalize_location(raw: str | None) -> str | None:
    if _nullish(raw):
        return None
    from app.services.admissions_intake_flow import _normalize_country_name

    token = str(raw).strip()
    normalized = _normalize_country_name(token)
    if normalized:
        return normalized
    if len(token.split()) > 3:
        return None
    return None


def _normalize_field(raw: str | None) -> str | None:
    if _nullish(raw):
        return None
    field = re.sub(r"\s+", " ", str(raw).strip(" ."))
    if not field:
        return None
    lowered = field.lower()
    if lowered == "mba":
        return "Business Administration"
    if lowered in {"ms", "m.s.", "masters", "master"}:
        return None
    if lowered in {"bs", "b.s.", "bachelors", "bachelor"}:
        return None
    return field[:120].title() if field.islower() else field[:120]


def _extract_location_from_tail(text: str) -> str | None:
    parts = re.split(r"\s+in\s+", (text or "").strip(), flags=re.IGNORECASE)
    if len(parts) < 2:
        return None
    candidate = parts[-1].strip(" .")
    return _normalize_location(candidate)


def _infer_level_and_field_from_text(text: str) -> tuple[str | None, str | None]:
    cleaned = (text or "").strip()
    lowered = cleaned.lower()

    if re.search(r"\bmba\b", lowered):
        return "Postgraduate", "Business Administration"
    if re.search(r"\b(m\.?s\.?|masters?|postgraduate|post graduate|postgrad)\b", lowered):
        level = "Postgraduate"
        field_match = re.search(
            r"(?:m\.?s\.?|masters?|postgraduate|post graduate|postgrad)\s+(?:in\s+)?(.+?)(?:\s+in\s+[a-z]|$)",
            cleaned,
            re.IGNORECASE,
        )
        if field_match:
            return level, _normalize_field(field_match.group(1))
        science_match = re.search(r"\b(science|engineering|robotics|design|finance|law)\b", lowered)
        if science_match:
            return level, _normalize_field(science_match.group(1).title())
        return level, None
    if re.search(r"\b(undergraduate|undergrad|bachelors?|b\.?s\.?|b\.?a\.?)\b", lowered):
        level = "Undergraduate"
        field_match = re.search(
            r"(?:undergraduate|undergrad|bachelors?|b\.?s\.?|b\.?a\.?)\s+(?:in\s+)?(.+?)(?:\s+in\s+[a-z]|$)",
            cleaned,
            re.IGNORECASE,
        )
        if field_match:
            return level, _normalize_field(field_match.group(1))
        science_match = re.search(r"\b(science|engineering|design|arts|commerce)\b", lowered)
        if science_match:
            return level, _normalize_field(science_match.group(1).title())
        return level, None
    return None, None


def parse_study_plan_payload(raw: str | dict[str, Any] | None) -> StudyPlanExtraction | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        payload = raw
    else:
        cleaned = str(raw).strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
            if match:
                cleaned = match.group(1)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None

    level = _normalize_level(payload.get("level"))
    field = _normalize_field(payload.get("field"))
    location = _normalize_location(payload.get("location"))
    extraction = StudyPlanExtraction(level=level, field=field, location=location)
    status = str(payload.get("status") or extraction.status).strip().lower()
    if status == "complete" and extraction.status != "complete":
        return StudyPlanExtraction(level=level, field=field, location=location)
    return extraction


def load_pending_study_plan(context: dict[str, Any], lead) -> StudyPlanExtraction:
    from app.services.lead_study_interest import resolve_lead_study_interest

    study = resolve_lead_study_interest(lead)
    level = str(context.get("pending_study_level") or "").strip() or None
    field = (
        str(context.get("pending_study_field") or context.get("pending_program") or "").strip()
        or study.get("course")
        or study.get("program")
        or None
    )
    location = (
        str(context.get("pending_country") or "").strip()
        or study.get("country")
        or getattr(lead, "preferred_country", None)
        or None
    )
    return StudyPlanExtraction(
        level=_normalize_level(level),
        field=_normalize_field(field),
        location=_normalize_location(location),
    )


def merge_study_plan_extraction(
    primary: StudyPlanExtraction,
    *,
    pending: StudyPlanExtraction | None = None,
    regex_interest: dict[str, str] | None = None,
) -> StudyPlanExtraction:
    level = primary.level or (pending.level if pending else None)
    field = primary.field or (pending.field if pending else None)
    location = primary.location or (pending.location if pending else None)

    if regex_interest:
        if not location and regex_interest.get("country"):
            candidate = _normalize_location(regex_interest["country"])
            if candidate:
                location = candidate
        if regex_interest.get("program"):
            inferred_level, inferred_field = _infer_level_and_field_from_text(regex_interest["program"])
            level = level or inferred_level
            field = field or inferred_field or _normalize_field(regex_interest["program"])

    return StudyPlanExtraction(level=level, field=field, location=location)


def _extract_standalone_country(text: str) -> str | None:
    """Recognize follow-up replies that are just a destination country (UK, U.k, Japan)."""
    cleaned = (text or "").strip().strip(".")
    if not cleaned or len(cleaned) > 60 or len(cleaned.split()) > 4:
        return None

    candidates = [cleaned, re.sub(r"[\s.\-_]+", "", cleaned)]
    for candidate in candidates:
        if not candidate:
            continue
        location = _normalize_location(candidate)
        if location:
            return location
    return None


_KNOWN_STANDALONE_FIELDS = frozenset(
    {
        "science",
        "engineering",
        "medicine",
        "law",
        "finance",
        "design",
        "arts",
        "commerce",
        "architecture",
        "nursing",
        "psychology",
        "education",
        "hospitality",
        "robotics",
    }
)


def _extract_standalone_field(text: str) -> str | None:
    """Recognize short follow-up replies that are just a field of study (science, MBA)."""
    cleaned = (text or "").strip().strip(".")
    if not cleaned or len(cleaned.split()) > 4:
        return None
    if _extract_standalone_country(cleaned):
        return None
    inferred_level, inferred_field = _infer_level_and_field_from_text(cleaned)
    if inferred_field:
        return inferred_field
    lowered = re.sub(r"[\s.\-_]+", " ", cleaned.lower()).strip()
    if lowered in _KNOWN_STANDALONE_FIELDS:
        return _normalize_field(cleaned)
    if len(cleaned.split()) >= 2:
        return _normalize_field(cleaned)
    return None


def coalesce_study_plan_extractions(*extractions: StudyPlanExtraction | None) -> StudyPlanExtraction:
    level = field = location = None
    for extraction in extractions:
        if extraction is None:
            continue
        level = level or extraction.level
        field = field or extraction.field
        location = location or extraction.location
    return StudyPlanExtraction(level=level, field=field, location=location)


def rule_based_study_plan_extraction(
    text: str,
    pending: StudyPlanExtraction | None = None,
) -> StudyPlanExtraction:
    from app.services.admissions_intake_flow import _extract_study_interest

    cleaned = (text or "").strip()
    inferred_level, inferred_field = _infer_level_and_field_from_text(cleaned)
    regex_interest = _extract_study_interest(cleaned)

    location = _normalize_location(regex_interest.get("country")) if regex_interest.get("country") else None
    field = inferred_field or _normalize_field(regex_interest.get("program"))
    level = inferred_level

    if not location:
        location = _extract_location_from_tail(cleaned)
        multi_tail = re.search(
            r"\bin\s+([A-Za-z][A-Za-z\s\-]{1,40})\s+in\s+([A-Za-z][A-Za-z\-]{1,40})$",
            cleaned,
            re.IGNORECASE,
        )
        if multi_tail:
            field = field or _normalize_field(multi_tail.group(1))
            location = location or _normalize_location(multi_tail.group(2))

    if not location:
        location = _extract_standalone_country(cleaned)

    if not field:
        science_match = re.search(r"\bin\s+(science|engineering|robotics|design|finance|law)\b", cleaned, re.I)
        if science_match:
            field = _normalize_field(science_match.group(1).title())

    if not field:
        field = _extract_standalone_field(cleaned)

    primary = StudyPlanExtraction(level=level, field=field, location=location)
    return merge_study_plan_extraction(primary, pending=pending, regex_interest=regex_interest)


async def extract_study_plan_from_message(
    text: str,
    *,
    runtime_config,
    pending: StudyPlanExtraction | None = None,
) -> StudyPlanExtraction:
    pending = pending or StudyPlanExtraction(level=None, field=None, location=None)
    cleaned = (text or "").strip()
    if not cleaned:
        return pending

    rule_based = rule_based_study_plan_extraction(cleaned, pending=pending)

    from app.services.ai_service import call_agent_llm

    known_bits = []
    if pending.level:
        known_bits.append(f"level={pending.level}")
    if pending.field:
        known_bits.append(f"field={pending.field}")
    if pending.location:
        known_bits.append(f"location={pending.location}")
    user_content = cleaned
    if known_bits:
        user_content += "\n\nAlready captured from earlier messages: " + ", ".join(known_bits)
    if pending.field and not pending.location:
        user_content += (
            "\n\nThe student's latest message may be ONLY a destination country "
            "(for example: UK, USA, Japan). Extract it as location."
        )

    messages = [
        {"role": "system", "content": STUDY_PLAN_EXTRACTION_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        result = await call_agent_llm(runtime_config.ai_model, messages)
        parsed = parse_study_plan_payload(result.text)
        if parsed:
            llm_merged = merge_study_plan_extraction(parsed, pending=pending)
            return coalesce_study_plan_extractions(rule_based, llm_merged)
    except Exception:
        logger.exception("Study plan LLM extraction failed.")

    return rule_based


def build_study_plan_confirmation_message(first: str, extraction: StudyPlanExtraction) -> str:
    return (
        f"Thanks, {first}! I have you down for a *{extraction.level}* in *{extraction.field}* "
        f"in *{extraction.location}*. Does that look right?\n\n"
        "Reply *yes* to confirm or *no* to change it."
    )


def build_study_plan_followup_message(extraction: StudyPlanExtraction) -> str:
    if not extraction.location:
        if extraction.level and extraction.field:
            return "*That sounds like a great plan!* Which *country* are you planning to study in?"
        return "*Which country are you targeting?*"
    if not extraction.level:
        return "*Are you looking at Undergraduate or Postgraduate programs?*"
    if not extraction.field:
        return "*What course or field of study* are you interested in?"
    return (
        "Tell me your *target country* and the *course or program* you want to study "
        "(for example: *MBA in UK*)."
    )


def persist_confirmed_study_plan(
    db,
    lead,
    context: dict[str, Any],
    extraction: StudyPlanExtraction,
) -> None:
    from app.services.admissions_intake_flow import _normalize_country_name, _save_context

    location = _normalize_location(extraction.location) or extraction.location
    field = _normalize_field(extraction.field) or extraction.field
    level = _normalize_level(extraction.level) or extraction.level

    if location:
        lead.preferred_country = _normalize_country_name(location) or location
    if field:
        context["preferred_course"] = field
        context["target_program"] = f"{level} in {field}" if level else field
    if level:
        context["study_level"] = level

    summary_bits = [bit for bit in [level, field, location] if bit]
    if summary_bits:
        lead.academic_summary = " / ".join(summary_bits)

    for key in (
        "pending_study_level",
        "pending_study_field",
        "pending_program",
        "pending_country",
        "awaiting_study_confirmation",
    ):
        context.pop(key, None)
    _save_context(db, lead, context)
