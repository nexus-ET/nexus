from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.counselling_service import (
    _booking_session_status_label,
    _build_data_exchange,
    _communications_to_timeline,
    _is_audio_media,
    _my_bookings_view_all,
    _resolve_lead_jump_path,
    get_my_bookings_overview,
)
from app.services.pipeline_service import resolve_admission_stage_meta


def _user(user_id: int, *, superuser: bool = False, role_name: str = "") -> SimpleNamespace:
    admin_role = SimpleNamespace(name=role_name) if role_name else None
    return SimpleNamespace(
        id=user_id,
        is_superuser=superuser,
        admin_role_ref=admin_role,
        role=role_name,
    )


def test_my_bookings_view_all_for_super_admin() -> None:
    assert _my_bookings_view_all(_user(1, superuser=True)) is True


def test_my_bookings_view_all_for_counselling_admin_role() -> None:
    assert _my_bookings_view_all(_user(2, role_name="Web Admin")) is True


def test_my_bookings_view_all_for_regular_counsellor() -> None:
    assert _my_bookings_view_all(_user(3, role_name="Counsellor")) is False


def test_get_my_bookings_overview_counts_all_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    calendar_today = date(2026, 7, 5)
    monkeypatch.setattr(
        "app.services.counselling_service.office_today",
        lambda db: calendar_today,
    )

    bookings = [
        SimpleNamespace(
            scheduled_time=datetime(2026, 7, 3, 10, 0),
            status="COMPLETED",
        ),
        SimpleNamespace(
            scheduled_time=datetime(2026, 7, 5, 11, 0),
            status="SCHEDULED",
        ),
        SimpleNamespace(
            scheduled_time=datetime(2026, 7, 8, 9, 0),
            status="CANCELLED",
        ),
    ]

    db = MagicMock()
    monkeypatch.setattr(
        "app.services.counselling_service._my_bookings_query",
        lambda db, user: MagicMock(all=MagicMock(return_value=bookings)),
    )

    overview = get_my_bookings_overview(db, _user(42))

    assert overview == {
        "past_count": 1,
        "today_count": 1,
        "upcoming_count": 1,
        "calendar_today": calendar_today,
        "view_all_bookings": False,
    }


def test_is_forward_status_change_uses_stage_id_order() -> None:
    from app.services.counselling_service import _is_forward_status_change

    db = MagicMock()
    assert _is_forward_status_change(db, 12, 13) is True
    assert _is_forward_status_change(db, 12, 4) is False
    assert _is_forward_status_change(db, 12, 12) is False


def test_follow_up_blocked_before_appointment_even_as_backward_transition() -> None:
    from app.services.counselling_service import _is_status_change_blocked_before_appointment
    from app.services.status_definition_service import STATUS_COUNSELLING_FOLLOW_UP

    db = MagicMock()
    assert _is_status_change_blocked_before_appointment(db, 12, STATUS_COUNSELLING_FOLLOW_UP) is True
    assert _is_status_change_blocked_before_appointment(db, 12, 11) is False


def test_is_backward_transition_uses_transition_graph() -> None:
    from app.models.status_transition import TransitionType
    from app.services.status_transition_service import is_backward_transition

    db = MagicMock()
    backward_row = SimpleNamespace(transition_type=TransitionType.BACKWARD)
    forward_row = SimpleNamespace(transition_type=TransitionType.FORWARD)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "app.services.status_transition_service._lookup_transition_row",
            lambda db, current, next, transition_type=None: backward_row if next == 11 else forward_row,
        )
        assert is_backward_transition(db, 12, 12) is True
        assert is_backward_transition(db, 12, 11) is True
        assert is_backward_transition(db, 12, 13) is False


def test_booking_session_status_label():
    assert _booking_session_status_label("SCHEDULED") == "Counselling: Scheduled"
    assert _booking_session_status_label("COMPLETED") == "Counselling: Finished"
    assert _booking_session_status_label("CANCELLED") == "Counselling: Cancelled"
    assert _booking_session_status_label("PENDING") == "Counselling: Pending Assignment"


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
