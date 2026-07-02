from types import SimpleNamespace

from app.services.counselling_service import (
    _booking_session_status_label,
    _build_data_exchange,
    _communications_to_timeline,
    _is_audio_media,
    _resolve_lead_jump_path,
)
from app.services.pipeline_service import resolve_admission_stage_meta


def test_booking_session_status_label():
    assert _booking_session_status_label("SCHEDULED") == "Counselling: Scheduled"
    assert _booking_session_status_label("COMPLETED") == "Counselling: Finished"


def test_resolve_admission_stage_meta_categories():
    key, label, category = resolve_admission_stage_meta("COUNSELLING")
    assert key == "COUNSELLING"
    assert label == "Counselling"
    assert category == "Acquisition"

    _, _, logistics = resolve_admission_stage_meta("AWAITING_DOCS")
    assert logistics == "Logistics"

    _, _, closure = resolve_admission_stage_meta("APPLIED")
    assert closure == "Closure"


def test_resolve_lead_jump_path_pipeline():
    lead = SimpleNamespace(id=42, admission_stage="APPLIED", stage="AI_ACTIVE")
    assert _resolve_lead_jump_path(lead) == "/prospects/42"


def test_resolve_lead_jump_path_by_stage():
    lead = SimpleNamespace(id=7, admission_stage=None, stage=SimpleNamespace(value="HANDOFF"))
    assert _resolve_lead_jump_path(lead) == "/handoffs"


def test_is_audio_media_detects_audio_extensions():
    assert _is_audio_media("https://cdn.example.com/note.webm", None) is True
    assert _is_audio_media("https://cdn.example.com/doc.pdf", "brochure.pdf") is False


def test_build_data_exchange_splits_by_participant():
    messages = [
        {
            "id": 1,
            "participant": "candidate",
            "text": "Transcript",
            "media_url": "https://example.com/transcript.pdf",
            "file_name": "transcript.pdf",
            "created_at": "2026-06-12T10:00:00",
        },
        {
            "id": 2,
            "participant": "handoff_admin",
            "text": "Brochure",
            "media_url": "https://example.com/brochure.pdf",
            "file_name": "brochure.pdf",
            "created_at": "2026-06-12T10:05:00",
        },
    ]
    student, admin = _build_data_exchange(messages)
    assert len(student) == 1
    assert student[0]["shared_by"] == "student"
    assert len(admin) == 1
    assert admin[0]["shared_by"] == "admin"


def test_communications_to_timeline_marks_audio():
    timeline = _communications_to_timeline(
        [
            {
                "id": 9,
                "participant": "candidate",
                "participant_label": "Alex",
                "text": "Voice note",
                "media_url": "https://example.com/voice.mp3",
                "file_name": "voice.mp3",
                "created_at": "2026-06-12T10:00:00",
            }
        ]
    )
    assert timeline[0]["kind"] == "audio"
