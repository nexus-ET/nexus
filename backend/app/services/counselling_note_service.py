from __future__ import annotations

import json
import re
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.counselling_booking import CounsellingBooking
from app.models.counselling_note import CounsellingNote
from app.schemas.counselling_note import (
    CounsellingSessionNoteOut,
    CounsellingSessionNoteSaveRequest,
    CounsellingSummarizeResponse,
)
from app.services.agent_runtime import get_runtime_agent_config
from app.services.ai_service import call_llm_json_content
from app.services.security_service import input_sanitizer

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
    note.preferred_universities = _encode_universities(payload.preferred_universities)
    note.scholarship_interests = (payload.scholarship_interests or "").strip() or None
    note.career_goals = (payload.career_goals or "").strip() or None
    note.officer_recommendations = (payload.officer_recommendations or "").strip() or None
    note.next_follow_up = payload.next_follow_up
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return _serialize_note(note)
