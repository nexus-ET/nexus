from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import student_status_service as service


def test_on_whatsapp_outreach_requests_commit(monkeypatch):
    captured: dict = {}

    def _fake_try(db, lead, **kwargs):
        captured.update(kwargs)
        return {"changed": True}

    monkeypatch.setattr(service, "try_automated_status_transition", _fake_try)

    lead = SimpleNamespace(id=27)
    service.on_whatsapp_outreach(MagicMock(), lead, source="AI outreach")

    assert captured["status_id"] == service.STATUS_LEAD_OUTREACH
    assert captured["commit"] is True


def test_on_whatsapp_inbound_requests_commit(monkeypatch):
    captured: dict = {}

    def _fake_try(db, lead, **kwargs):
        captured.update(kwargs)
        return {"changed": True}

    monkeypatch.setattr(service, "try_automated_status_transition", _fake_try)

    lead = SimpleNamespace(id=27)
    service.on_whatsapp_inbound(MagicMock(), lead)

    assert captured["status_id"] == service.STATUS_LEAD_ENGAGEMENT
    assert captured["commit"] is True
