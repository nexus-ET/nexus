"""Tests for conditional uptime monitoring (Active guard)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.monitoring_uptime_service import run_uptime_monitoring_check


def test_inactive_status_skips_ping_and_email():
    settings_map = {
        "MONITORING_STATUS": "Inactive",
        "UPTIME_TARGET_URL": "https://example.com/health",
        "ALERT_EMAIL": "admin@example.com",
    }

    def fake_get_setting(key, default="", db=None):
        return settings_map.get(key, default)

    with (
        patch("app.services.monitoring_uptime_service.get_setting", side_effect=fake_get_setting),
        patch("app.services.monitoring_uptime_service._ping_uptime_target") as ping,
        patch("app.services.monitoring_uptime_service.send_email") as mail,
        patch("app.db.database.SessionLocal", return_value=MagicMock()),
    ):
        run_uptime_monitoring_check()

    ping.assert_not_called()
    mail.assert_not_called()


def test_active_status_pings_and_alerts_on_failure():
    settings_map = {
        "MONITORING_STATUS": "Active",
        "UPTIME_TARGET_URL": "https://example.com/health",
        "ALERT_EMAIL": "admin@example.com, ops@example.com",
    }

    def fake_get_setting(key, default="", db=None):
        return settings_map.get(key, default)

    with (
        patch("app.services.monitoring_uptime_service.get_setting", side_effect=fake_get_setting),
        patch(
            "app.services.monitoring_uptime_service._ping_uptime_target",
            return_value=(False, "HTTP 503 (expected 200)"),
        ) as ping,
        patch("app.services.monitoring_uptime_service.send_email", return_value=True) as mail,
        patch("app.db.database.SessionLocal", return_value=MagicMock()),
    ):
        run_uptime_monitoring_check()

    ping.assert_called_once_with("https://example.com/health")
    mail.assert_called_once()
    assert mail.call_args.args[0] == ["admin@example.com", "ops@example.com"]


def test_active_but_not_exact_active_string_skips():
    """Strict equality: only the exact string Active enables monitoring."""
    settings_map = {
        "MONITORING_STATUS": "active",
        "UPTIME_TARGET_URL": "https://example.com/health",
        "ALERT_EMAIL": "admin@example.com",
    }

    def fake_get_setting(key, default="", db=None):
        return settings_map.get(key, default)

    with (
        patch("app.services.monitoring_uptime_service.get_setting", side_effect=fake_get_setting),
        patch("app.services.monitoring_uptime_service._ping_uptime_target") as ping,
        patch("app.services.monitoring_uptime_service.send_email") as mail,
        patch("app.db.database.SessionLocal", return_value=MagicMock()),
    ):
        run_uptime_monitoring_check()

    ping.assert_not_called()
    mail.assert_not_called()
