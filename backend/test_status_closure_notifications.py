from types import SimpleNamespace

from app.services.status_closure_notifications import (
    CLOSURE_WHATSAPP_STATUS_IDS,
    render_closure_whatsapp_message,
)
from app.services.status_definition_service import (
    STATUS_LEAD_CANCELLED_NO_ANSWER,
    STATUS_LEAD_CANCELLED_NOT_INTERESTED,
    STATUS_LEAD_DEFERRED,
)


def test_closure_whatsapp_status_ids():
    assert CLOSURE_WHATSAPP_STATUS_IDS == {7, 8, 9}


def test_render_closure_message_no_answer():
    lead = SimpleNamespace(full_name="Henry Ford")
    message = render_closure_whatsapp_message(
        lead=lead,
        status_id=STATUS_LEAD_CANCELLED_NO_ANSWER,
    )
    assert message is not None
    assert "Hi Henry," in message
    assert "questions or to book a consultation" in message


def test_render_closure_message_not_interested():
    lead = SimpleNamespace(full_name="Jane Doe")
    message = render_closure_whatsapp_message(
        lead=lead,
        status_id=STATUS_LEAD_CANCELLED_NOT_INTERESTED,
    )
    assert message is not None
    assert "respect your decision" in message
    assert "questions or to book a consultation" in message


def test_render_closure_message_deferred():
    lead = SimpleNamespace(full_name="Alex Smith")
    message = render_closure_whatsapp_message(
        lead=lead,
        status_id=STATUS_LEAD_DEFERRED,
    )
    assert message is not None
    assert "postpone" in message
    assert "questions or to book a consultation" in message


def test_render_closure_message_unknown_status():
    lead = SimpleNamespace(full_name="Alex Smith")
    assert render_closure_whatsapp_message(lead=lead, status_id=4) is None
