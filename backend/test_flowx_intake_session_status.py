"""Intake Session (1.1) status mapping from status_definitions / bookings."""

from app.services.flowx import resolve_intake_session_state


def test_intake_planned_when_session_booked_or_rescheduled():
    assert resolve_intake_session_state(status_definition_id=4) == ("todo", "on_track", 25)
    assert resolve_intake_session_state(status_definition_id=5) == ("todo", "on_track", 25)


def test_intake_in_progress_when_counselling_scheduled():
    assert resolve_intake_session_state(status_definition_id=12) == (
        "in_progress",
        "on_track",
        50,
    )


def test_intake_delayed_when_cancelled():
    assert resolve_intake_session_state(status_definition_id=6) == ("todo", "breached", 0)
    assert resolve_intake_session_state(status_definition_id=7) == ("todo", "breached", 0)


def test_intake_complete_when_finished_or_qualified():
    assert resolve_intake_session_state(status_definition_id=13) == ("approved", "on_track", 100)
    assert resolve_intake_session_state(status_definition_id=14) == ("approved", "on_track", 100)
    assert resolve_intake_session_state(status_definition_id=15) == ("approved", "on_track", 100)


def test_intake_booking_status_fallback():
    assert resolve_intake_session_state(status_definition_id=None, booking_status="PENDING") == (
        "todo",
        "on_track",
        25,
    )
    assert resolve_intake_session_state(status_definition_id=None, booking_status="SCHEDULED") == (
        "in_progress",
        "on_track",
        50,
    )
    assert resolve_intake_session_state(status_definition_id=None, booking_status="CANCELLED") == (
        "todo",
        "breached",
        0,
    )
    assert resolve_intake_session_state(status_definition_id=None, booking_status="COMPLETED") == (
        "approved",
        "on_track",
        100,
    )


def test_intake_default_without_booking():
    assert resolve_intake_session_state(status_definition_id=1) == ("todo", "on_track", 0)


def test_intake_merge_booked_lead_with_scheduled_booking():
    """Lead still Session Booked (4) + booking SCHEDULED → In progress 50%."""
    assert resolve_intake_session_state(
        status_definition_id=4,
        booking_status="SCHEDULED",
    ) == ("in_progress", "on_track", 50)
    assert resolve_intake_session_state(
        status_definition_id=5,
        booking_status="SCHEDULED",
    ) == ("in_progress", "on_track", 50)


def test_intake_delayed_wins_over_scheduled_booking():
    assert resolve_intake_session_state(
        status_definition_id=6,
        booking_status="SCHEDULED",
    ) == ("todo", "breached", 0)


def test_intake_overdue_slot_is_delayed_zero():
    """Past appointment without Finished → Delayed 0%, even if still Scheduled/Booked."""
    assert resolve_intake_session_state(
        status_definition_id=12,
        booking_status="SCHEDULED",
        is_overdue=True,
    ) == ("todo", "breached", 0)
    assert resolve_intake_session_state(
        status_definition_id=4,
        booking_status="PENDING",
        is_overdue=True,
    ) == ("todo", "breached", 0)


def test_intake_finished_wins_over_overdue():
    assert resolve_intake_session_state(
        status_definition_id=13,
        booking_status="COMPLETED",
        is_overdue=True,
    ) == ("approved", "on_track", 100)


def test_intake_delay_parts_format():
    from app.services.flowx import _format_intake_delay_parts

    assert _format_intake_delay_parts(7) == {
        "delay_days": 7,
        "delay_weeks": 1,
        "delay_months": 0,
        "delay_label": "7 days · 1 week · 0 months",
    }
    assert _format_intake_delay_parts(1)["delay_label"] == "1 day · 0 weeks · 0 months"
    assert _format_intake_delay_parts(45) == {
        "delay_days": 45,
        "delay_weeks": 6,
        "delay_months": 1,
        "delay_label": "45 days · 6 weeks · 1 month",
    }
