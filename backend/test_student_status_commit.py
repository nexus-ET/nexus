from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import student_status_service as service


def test_on_whatsapp_outreach_requests_commit(monkeypatch):
    captured: dict = {}

    def _fake_try(db, lead, **kwargs):
        captured.update(kwargs)
        return {"changed": True}

    monkeypatch.setattr(service, "try_automated_status_transition", _fake_try)
    monkeypatch.setattr(service, "sync_lead_pipeline_status_id", lambda db, lead: False)
    monkeypatch.setattr(service, "resolve_status_id_by_name", lambda db, name, fallback=None: fallback)

    lead = SimpleNamespace(id=27, status_definition_id=1)
    service.on_whatsapp_outreach(MagicMock(), lead, source="AI outreach")

    assert captured["status_id"] == service.STATUS_LEAD_OUTREACH
    assert captured["commit"] is True


def test_on_whatsapp_inbound_requests_commit(monkeypatch):
    captured: dict = {}

    def _fake_try(db, lead, **kwargs):
        captured.update(kwargs)
        return {"changed": True}

    monkeypatch.setattr(service, "try_automated_status_transition", _fake_try)
    monkeypatch.setattr(service, "sync_lead_pipeline_status_id", lambda db, lead: False)
    monkeypatch.setattr(service, "resolve_status_id_by_name", lambda db, name, fallback=None: fallback)

    lead = SimpleNamespace(id=27, status_definition_id=2)
    service.on_whatsapp_inbound(MagicMock(), lead)

    assert captured["status_id"] == service.STATUS_LEAD_ENGAGEMENT
    assert captured["commit"] is True
