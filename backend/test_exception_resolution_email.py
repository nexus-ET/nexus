"""Resolution confirmation emails must not fire for page-refresh auto-resolves."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.exception_log_service import (
    RESOLVER_CURSOR,
    RESOLVER_PAGE_REFRESH,
    _recent_exception_alert_keys,
    _send_exception_resolved_email,
    schedule_exception_resolved_email,
    update_exception_log_status,
)


def _resolved_row(**overrides):
    data = dict(
        id=5656,
        severity="ERROR",
        source="api_client",
        category="request_timeout",
        status="RESOLVED",
        triggered_by_user="SYSTEM",
        triggered_by_user_id=None,
        message="Client request timed out after 60s: scanx/ocr",
        details_json="[]",
        page_path="/document-readiness",
        exception_type="AbortError",
        related_resource="api",
        related_id="scanx/ocr",
        attempt_timestamp=None,
        resolved_at=None,
        resolution_comment="Resolved automatically after a successful page load/refresh.",
        resolved_by=RESOLVER_PAGE_REFRESH,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def setup_function() -> None:
    _recent_exception_alert_keys.clear()


def test_page_refresh_resolution_does_not_email() -> None:
    row = _resolved_row()
    with (
        patch(
            "app.services.exception_log_service._alert_recipients",
            return_value=["ishtiaque.s@gmail.com", "ishq@edutrust.in"],
        ),
        patch("app.services.email_service.send_email", return_value=True) as mail,
    ):
        _send_exception_resolved_email(row)
    mail.assert_not_called()


def test_schedule_page_refresh_does_not_start_mail_thread() -> None:
    row = _resolved_row()
    with patch("app.services.exception_log_service.threading.Thread") as thread_cls:
        schedule_exception_resolved_email(row, resolved_by=RESOLVER_PAGE_REFRESH)
    thread_cls.assert_not_called()


def test_cursor_agent_resolution_still_emails() -> None:
    row = _resolved_row(id=42, resolved_by=RESOLVER_CURSOR, category="general")
    with (
        patch(
            "app.services.exception_log_service._alert_recipients",
            return_value=["ops@example.com"],
        ),
        patch("app.services.email_service.send_email", return_value=True) as mail,
    ):
        _send_exception_resolved_email(row)
    mail.assert_called_once()
    recipients, subject, _body = mail.call_args.args
    assert recipients == ["ops@example.com"]
    assert "Exception Report #42 resolved" in subject
    assert "Cursor agent" in subject


def test_manual_admin_resolve_does_not_email() -> None:
    row = _resolved_row(id=99, status="OPEN", resolution_comment=None, resolved_at=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    with patch(
        "app.services.exception_log_service.schedule_exception_resolved_email"
    ) as schedule:
        updated = update_exception_log_status(
            db,
            99,
            status="RESOLVED",
            resolution_comment="Fixed after reviewing Document Readiness timeouts.",
            resolved_by="admin",
            allow_auto_comment=False,
        )

    assert updated is row
    schedule.assert_not_called()
