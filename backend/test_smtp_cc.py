"""SMTP_CC applies only to student-facing send_email calls."""
from email.message import EmailMessage

from app.services.email_service import parse_smtp_cc, send_email


def test_parse_smtp_cc_separators_dedupe_and_invalid():
    assert parse_smtp_cc(
        "a@ex.com, b@ex.com; C@ex.com  a@ex.com\nnot-an-email  ,  "
    ) == ["a@ex.com", "b@ex.com", "C@ex.com"]
    assert parse_smtp_cc(None) == []
    assert parse_smtp_cc("") == []


def test_student_send_builds_cc_from_smtp_cc(monkeypatch):
    captured: dict = {}

    def fake_deliver(message: EmailMessage, *, recipients: list[str]) -> None:
        captured["message"] = message
        captured["recipients"] = list(recipients)

    monkeypatch.setattr("app.services.email_service._smtp_configured", lambda: True)
    monkeypatch.setattr(
        "app.services.email_service.settings.SMTP_FROM_EMAIL",
        "noreply@example.com",
    )
    monkeypatch.setattr("app.services.email_service.settings.SMTP_USER", "noreply@example.com")
    monkeypatch.setattr(
        "app.services.email_service.settings.SMTP_CC",
        "application@edutrust.in,arunpk@edutrust.in;saviarun@edutrust.in student@example.com",
    )
    monkeypatch.setattr("app.services.email_service.resolve_outbound_from_name", lambda: "Nexus")
    monkeypatch.setattr("app.services.email_service._deliver", fake_deliver)

    assert send_email(["student@example.com"], "Checklist", "Body", student=True) is True

    msg = captured["message"]
    assert msg["To"] == "student@example.com"
    assert msg["Cc"] == "application@edutrust.in, arunpk@edutrust.in, saviarun@edutrust.in"
    # Envelope includes Cc; To address already in To is not duplicated in Cc.
    assert captured["recipients"] == [
        "student@example.com",
        "application@edutrust.in",
        "arunpk@edutrust.in",
        "saviarun@edutrust.in",
    ]


def test_non_student_send_does_not_apply_smtp_cc(monkeypatch):
    captured: dict = {}

    def fake_deliver(message: EmailMessage, *, recipients: list[str]) -> None:
        captured["message"] = message
        captured["recipients"] = list(recipients)

    monkeypatch.setattr("app.services.email_service._smtp_configured", lambda: True)
    monkeypatch.setattr(
        "app.services.email_service.settings.SMTP_FROM_EMAIL",
        "noreply@example.com",
    )
    monkeypatch.setattr("app.services.email_service.settings.SMTP_USER", "noreply@example.com")
    monkeypatch.setattr(
        "app.services.email_service.settings.SMTP_CC",
        "application@edutrust.in,arunpk@edutrust.in",
    )
    monkeypatch.setattr("app.services.email_service.resolve_outbound_from_name", lambda: "Nexus")
    monkeypatch.setattr("app.services.email_service._deliver", fake_deliver)

    assert send_email(["admin@example.com"], "Alert", "Body") is True

    msg = captured["message"]
    assert msg["To"] == "admin@example.com"
    assert msg.get("Cc") is None
    assert captured["recipients"] == ["admin@example.com"]
