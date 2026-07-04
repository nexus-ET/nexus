"""Tests for security audit IDOR heuristics and red-flag alert controls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.audit_runner import _should_send_red_flag_alert
from app.services.security_audit import (
    _admin_id_scoped_booking_handler,
    check_idor_controls,
)


def test_admin_id_scoped_booking_handler_accepts_owned_booking_delegate() -> None:
    handler = "def get_my_booking_communications(...):\n    _get_owned_booking(db, user_id, booking_id)\n"
    owned = (
        "def _get_owned_booking(...):\n"
        "    .filter(CounsellingBooking.id == booking_id, CounsellingBooking.admin_id == user_id)\n"
    )
    assert _admin_id_scoped_booking_handler(handler, owned) is True


def test_admin_id_scoped_booking_handler_accepts_inline_filter() -> None:
    handler = "CounsellingBooking.admin_id == user_id"
    owned = ""
    assert _admin_id_scoped_booking_handler(handler, owned) is True


def test_my_booking_communications_idor_check_passes() -> None:
    idor = [check for check in check_idor_controls() if check.name == "my_booking_communications_admin_id_scope"]
    assert len(idor) == 1
    assert idor[0].passed is True


def test_should_send_red_flag_alert_respects_master_switch() -> None:
    with patch("app.services.audit_runner.settings") as settings:
        settings.SECURITY_AUDIT_RED_ALERTS_ENABLED = False
        settings.SECURITY_AUDIT_ALERT_MANUAL_ONLY = False
        assert _should_send_red_flag_alert(triggered_by="scheduled") is False
        assert _should_send_red_flag_alert(triggered_by="manual") is False


def test_should_send_red_flag_alert_manual_only() -> None:
    with patch("app.services.audit_runner.settings") as settings:
        settings.SECURITY_AUDIT_RED_ALERTS_ENABLED = True
        settings.SECURITY_AUDIT_ALERT_MANUAL_ONLY = True
        assert _should_send_red_flag_alert(triggered_by="scheduled") is False
        assert _should_send_red_flag_alert(triggered_by="manual") is True


def test_should_send_red_flag_alert_default_allows_scheduled() -> None:
    with patch("app.services.audit_runner.settings") as settings:
        settings.SECURITY_AUDIT_RED_ALERTS_ENABLED = True
        settings.SECURITY_AUDIT_ALERT_MANUAL_ONLY = False
        assert _should_send_red_flag_alert(triggered_by="scheduled") is True
