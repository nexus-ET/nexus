from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.counselling_booking import CounsellingBooking
from app.models.counselling_note import CounsellingNote
from app.models.academia_institution import Campus, College, Institution
from app.models.academia_wizard import InstitutionCourseOffering
from app.models.program import Program
from app.models.target_course import TargetCourse
from app.schemas.counselling_note import (
    CounsellingSessionNoteOut,
    CounsellingSessionNoteSaveRequest,
    CounsellingSummarizeResponse,
    RecommendedInstitutionOption,
    RecommendedInstitutionOptionsResponse,
)
from app.services.agent_runtime import get_runtime_agent_config
from app.services.ai_service import call_llm_json_content
from app.services.security_service import input_sanitizer
from app.utils.timezone import utc_now

SUMMARIZE_JSON_DIRECTIVE = (
    "\n\nRespond with valid JSON only using this schema: "
    '{"preferred_universities": ["University A", "University B"], '
    '"scholarship_interests": "only scholarship or financial-aid interests mentioned", '
    '"career_goals": "only career goals mentioned", '
    '"recommendations": "counsellor recommendations and next steps", '
    '"next_follow_up": "YYYY-MM-DD or empty string"}'
    "\n\nRules:"
    "\n- Never paste the full transcript into scholarship_interests."
    "\n- Leave fields empty when the topic was not discussed."
    "\n- Put general session guidance in recommendations."
)


def _get_assigned_booking(db: Session, user_id: int, booking_id: int) -> CounsellingBooking:
    booking = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.id == booking_id, CounsellingBooking.admin_id == user_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you.")
    return booking


def _decode_universities(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _institution_option_value(institution_id: int) -> str:
    return f"institution:{institution_id}"


def _college_option_value(college_id: int) -> str:
    return f"college:{college_id}"


def _parse_uuid_list(values: list[str] | None) -> list[uuid.UUID]:
    parsed: list[uuid.UUID] = []
    for raw in values or []:
        token = str(raw or "").strip()
        if not token:
            continue
        try:
            parsed.append(uuid.UUID(token))
        except ValueError:
            continue
    return parsed


def _matching_institution_ids_for_study_interest(
    db: Session,
    *,
    level_id: int | None = None,
    major_ids: list[int] | None = None,
    program_ids: list[uuid.UUID] | None = None,
) -> set[int] | None:
    """Return matching institution IDs, or None when no academic filter is applied."""
    cleaned_majors = [int(item) for item in (major_ids or []) if int(item) > 0]
    cleaned_programs = list(program_ids or [])
    if not level_id and not cleaned_majors and not cleaned_programs:
        return None

    offering_q = (
        db.query(InstitutionCourseOffering.institution_id)
        .join(TargetCourse, TargetCourse.id == InstitutionCourseOffering.course_id)
        .filter(InstitutionCourseOffering.is_active.is_(True))
    )

    if cleaned_programs:
        offering_q = offering_q.filter(
            TargetCourse.qualification_program_id.in_(cleaned_programs)
        )
    elif cleaned_majors:
        offering_q = offering_q.filter(TargetCourse.education_major_id.in_(cleaned_majors))
    elif level_id:
        offering_q = offering_q.join(
            Program, Program.id == TargetCourse.qualification_program_id
        ).filter(Program.level_id == level_id)

    return {int(row[0]) for row in offering_q.distinct().all()}


def list_recommended_institution_options(
    db: Session,
    *,
    country_ids: list[int] | None = None,
    level_id: int | None = None,
    major_ids: list[int] | None = None,
    program_ids: list[str] | None = None,
) -> RecommendedInstitutionOptionsResponse:
    query = (
        db.query(Institution)
        .options(
            joinedload(Institution.country),
            joinedload(Institution.state),
            joinedload(Institution.city),
        )
        .filter(Institution.is_active.is_(True))
    )
    if country_ids is not None:
        cleaned_ids = [int(item) for item in country_ids if int(item) > 0]
        if not cleaned_ids:
            return RecommendedInstitutionOptionsResponse(options=[])
        query = query.filter(Institution.country_id.in_(cleaned_ids))

    academic_ids = _matching_institution_ids_for_study_interest(
        db,
        level_id=level_id,
        major_ids=major_ids,
        program_ids=_parse_uuid_list(program_ids),
    )
    if academic_ids is not None:
        if not academic_ids:
            return RecommendedInstitutionOptionsResponse(options=[])
        query = query.filter(Institution.id.in_(academic_ids))

    institutions = query.order_by(Institution.sort_order.asc(), Institution.name.asc()).all()
    active_institution_ids = {row.id for row in institutions}
    institution_by_id = {row.id: row for row in institutions}
    colleges: list[College] = []
    if active_institution_ids:
        colleges = (
            db.query(College)
            .options(
                joinedload(College.campus).joinedload(Campus.location),
                joinedload(College.campus).joinedload(Campus.state),
                joinedload(College.campus).joinedload(Campus.country),
            )
            .filter(
                College.is_active.is_(True),
                College.institution_id.in_(active_institution_ids),
            )
            .order_by(College.sort_order.asc(), College.name.asc())
            .all()
        )

    options: list[RecommendedInstitutionOption] = []
    for row in institutions:
        options.append(
            RecommendedInstitutionOption(
                value=_institution_option_value(row.id),
                label=f"{row.name} (Institution)",
                kind="institution",
                name=row.name,
                country_id=row.country_id,
                country_name=row.country.name if row.country else None,
                state_name=row.state.name if row.state else None,
                city_name=row.city.name if row.city else None,
            )
        )
    for row in colleges:
        parent = institution_by_id.get(row.institution_id)
        parent_name = parent.name if parent else "Institution"
        campus = row.campus
        country_name = None
        state_name = None
        city_name = None
        if campus:
            country_name = campus.country.name if campus.country else None
            state_name = campus.state.name if campus.state else None
            city_name = campus.location.name if campus.location else campus.city
        if parent:
            country_name = country_name or (parent.country.name if parent.country else None)
            state_name = state_name or (parent.state.name if parent.state else None)
            city_name = city_name or (parent.city.name if parent.city else None)
        options.append(
            RecommendedInstitutionOption(
                value=_college_option_value(row.id),
                label=f"{row.name} · {parent_name} (College)",
                kind="college",
                name=row.name,
                country_id=parent.country_id if parent else None,
                country_name=country_name,
                state_name=state_name,
                city_name=city_name,
            )
        )
    return RecommendedInstitutionOptionsResponse(options=options)


def _filter_recommended_institutions(db: Session, values: list[str]) -> list[str]:
    options = list_recommended_institution_options(db).options
    allowed = {option.value for option in options}
    by_label = {option.label.strip().lower(): option.value for option in options}
    by_name: dict[str, str] = {}
    for option in options:
        key = option.name.strip().lower()
        # Prefer institution matches when names collide.
        if key not in by_name or option.kind == "institution":
            by_name[key] = option.value

    resolved: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = (raw or "").strip()
        if not token:
            continue
        value = token if token in allowed else (
            by_label.get(token.lower()) or by_name.get(token.lower()) or ""
        )
        if not value or value not in allowed or value in seen:
            continue
        seen.add(value)
        resolved.append(value)
    return resolved


def _encode_universities(values: list[str]) -> str | None:
    cleaned = [value.strip() for value in values if value and value.strip()]
    return json.dumps(cleaned) if cleaned else None


def _parse_follow_up(value: object) -> date | None:
    if not value:
        return None
    token = str(value).strip()
    if not token:
        return None
    try:
        return date.fromisoformat(token[:10])
    except ValueError:
        return None


def _parse_summarize_payload(content: str) -> CounsellingSummarizeResponse:
    cleaned = (content or "").strip()
    candidates = [cleaned]
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidates.insert(0, cleaned[brace_start : brace_end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        universities_raw = payload.get("preferred_universities", [])
        universities: list[str] = []
        if isinstance(universities_raw, list):
            universities = [str(item).strip() for item in universities_raw if str(item).strip()]
        elif isinstance(universities_raw, str) and universities_raw.strip():
            universities = [part.strip() for part in universities_raw.split(",") if part.strip()]

        return CounsellingSummarizeResponse(
            preferred_universities=universities,
            scholarship_interests=str(payload.get("scholarship_interests") or "").strip(),
            career_goals=str(payload.get("career_goals") or "").strip(),
            recommendations=str(
                payload.get("recommendations")
                or payload.get("officer_recommendations")
                or payload.get("counsellor_recommendations")
                or ""
            ).strip(),
            next_follow_up=_parse_follow_up(payload.get("next_follow_up")),
        )

    return CounsellingSummarizeResponse()


def _normalize_summarize_response(
    parsed: CounsellingSummarizeResponse,
    raw_text: str,
) -> CounsellingSummarizeResponse:
    """Prevent full transcript dumps into a single field."""
    raw = raw_text.strip()
    if not raw:
        return parsed

    scholarship = (parsed.scholarship_interests or "").strip()
    if scholarship and (
        scholarship == raw
        or len(scholarship) >= int(len(raw) * 0.65)
        or raw.startswith(scholarship[: min(40, len(scholarship))])
    ):
        return CounsellingSummarizeResponse(
            preferred_universities=parsed.preferred_universities,
            scholarship_interests="",
            career_goals=parsed.career_goals,
            recommendations=parsed.recommendations or scholarship,
            next_follow_up=parsed.next_follow_up,
        )

    return parsed


def _summarize_has_structured_content(parsed: CounsellingSummarizeResponse) -> bool:
    return bool(
        parsed.preferred_universities
        or (parsed.scholarship_interests or "").strip()
        or (parsed.career_goals or "").strip()
        or (parsed.recommendations or "").strip()
        or parsed.next_follow_up
    )


def _serialize_note(note: CounsellingNote) -> CounsellingSessionNoteOut:
    return CounsellingSessionNoteOut(
        booking_id=note.booking_id,
        ai_transcription=note.ai_transcription,
        preferred_universities=_decode_universities(note.preferred_universities),
        scholarship_interests=note.scholarship_interests,
        career_goals=note.career_goals,
        officer_recommendations=note.officer_recommendations,
        next_follow_up=note.next_follow_up,
        updated_at=note.updated_at.isoformat() if note.updated_at else None,
    )


async def summarize_counselling_text(db: Session, raw_text: str) -> CounsellingSummarizeResponse:
    runtime_config = get_runtime_agent_config(db)
    sanitized = input_sanitizer(raw_text.strip())
    system_prompt = (
        "You are an admissions documentation assistant. Extract structured counselling session notes "
        "from counsellor dictation or rough notes. Be concise and factual."
        + SUMMARIZE_JSON_DIRECTIVE
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Counselling session notes to summarize:\n\n{sanitized}",
        },
    ]
    content = await call_llm_json_content(runtime_config.ai_model, messages)
    parsed = _normalize_summarize_response(_parse_summarize_payload(content), sanitized)
    if not _summarize_has_structured_content(parsed):
        raise HTTPException(
            status_code=502,
            detail="AI could not extract structured session fields. Review the transcription and try again.",
        )
    return parsed


def get_session_note(db: Session, user_id: int, booking_id: int) -> CounsellingSessionNoteOut:
    _get_assigned_booking(db, user_id, booking_id)
    note = db.query(CounsellingNote).filter(CounsellingNote.booking_id == booking_id).first()
    if not note:
        return CounsellingSessionNoteOut(booking_id=booking_id)
    return _serialize_note(note)


def save_session_note(
    db: Session,
    user_id: int,
    booking_id: int,
    payload: CounsellingSessionNoteSaveRequest,
) -> CounsellingSessionNoteOut:
    _get_assigned_booking(db, user_id, booking_id)
    note = db.query(CounsellingNote).filter(CounsellingNote.booking_id == booking_id).first()
    if not note:
        note = CounsellingNote(booking_id=booking_id, admin_id=user_id)
        db.add(note)

    note.admin_id = user_id
    note.ai_transcription = (payload.ai_transcription or "").strip() or None
    note.preferred_universities = _encode_universities(
        _filter_recommended_institutions(db, payload.preferred_universities)
    )
    note.scholarship_interests = (payload.scholarship_interests or "").strip() or None
    note.career_goals = (payload.career_goals or "").strip() or None
    note.officer_recommendations = (payload.officer_recommendations or "").strip() or None
    note.next_follow_up = payload.next_follow_up
    note.updated_at = utc_now()
    db.commit()
    db.refresh(note)
    return _serialize_note(note)
