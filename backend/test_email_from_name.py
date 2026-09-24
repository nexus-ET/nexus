"""Outbound From name comes from the organization business profile."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.email_service import resolve_outbound_from_name


def test_from_name_uses_organization_business_name():
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        short_name="Edutrust"
    )
    with patch("app.db.database.SessionLocal", return_value=session):
        assert resolve_outbound_from_name() == "Edutrust"
    session.close.assert_called_once()


def test_from_name_uses_business_name_when_short_name_blank(monkeypatch):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        short_name="  ",
        name="Edutrust Overseas Education",
    )
    monkeypatch.setattr(
        "app.services.email_service.settings.SMTP_FROM_NAME",
        "Nexus Counselling",
    )
    with patch("app.db.database.SessionLocal", return_value=session):
        assert resolve_outbound_from_name() == "Edutrust Overseas Education"
