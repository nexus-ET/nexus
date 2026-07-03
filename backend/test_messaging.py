"""Tests for Meta webhook payload parsing and messaging provider routing."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app.services.messaging import (
    PROVIDER_TWILIO,
    PROVIDER_WHATSAPP,
    MetaTemplateSendSpec,
    WhatsAppDeliveryError,
    assert_whatsapp_business_outreach_allowed,
    build_outreach_template_body_parameters,
    extract_meta_message_id,
    format_meta_graph_error,
    get_active_provider,
    parse_whatsapp_payload,
    resolve_outreach_template_language,
    _build_template_components,
    _parse_body_parameter_spec,
)


def test_parse_whatsapp_payload_extracts_text_message() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "919876543210"}],
                            "messages": [
                                {
                                    "id": "wamid.test",
                                    "from": "919876543210",
                                    "type": "text",
                                    "text": {"body": "Hello Nexus"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    parsed = parse_whatsapp_payload(payload)
    assert parsed is not None
    assert parsed.sender_id == "919876543210"
    assert parsed.message_body == "Hello Nexus"
    assert parsed.message_id == "wamid.test"


def test_parse_whatsapp_payload_ignores_status_updates() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"id": "wamid.test", "status": "delivered"}]
                        }
                    }
                ]
            }
        ]
    }

    assert parse_whatsapp_payload(payload) is None


def test_get_active_provider_defaults_to_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "PROVIDER", "")
    assert get_active_provider() == PROVIDER_TWILIO

    monkeypatch.setattr(settings, "PROVIDER", PROVIDER_WHATSAPP)
    assert get_active_provider() == PROVIDER_WHATSAPP


def test_format_meta_graph_error_re_engagement() -> None:
    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "(#131047) Re-engagement message",
                "type": "OAuthException",
                "code": 131047,
            }
        },
    )
    detail = format_meta_graph_error(response)
    assert "24-hour customer care window" in detail
    assert "WHATSAPP_OUTREACH_TEMPLATE" in detail


def test_format_meta_graph_error_template_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE", "et_student_welcome")
    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE", "en_US")

    response = httpx.Response(
        404,
        json={
            "error": {
                "message": "(#132001) Template name does not exist in the translation",
                "type": "OAuthException",
                "code": 132001,
            }
        },
    )
    detail = format_meta_graph_error(response)
    assert "et_student_welcome" in detail
    assert "en_US" in detail
    assert "WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE" in detail


def test_resolve_outreach_template_language_defaults_to_en(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE", "")
    assert resolve_outreach_template_language() == "en"


def test_parse_body_parameter_spec_ignores_square_bracket_labels() -> None:
    count, names = _parse_body_parameter_spec(
        {
            "type": "BODY",
            "text": "Hi [Student Name]! Thanks for reaching [Company Name].",
        }
    )
    assert count == 0
    assert names == ()


def test_parse_body_parameter_spec_counts_curly_placeholders() -> None:
    count, names = _parse_body_parameter_spec(
        {
            "type": "BODY",
            "text": "Hi {{1}}! Thanks for reaching {{2}}.",
            "example": {"body_text": [["Priya", "Edutrust"]]},
        }
    )
    assert count == 2
    assert names == ()


def test_build_outreach_template_body_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_COMPANY_NAME", "Edutrust")
    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS", "student,company")

    lead = SimpleNamespace(full_name="Priya Sharma", phone_number="+919876543210")
    spec = MetaTemplateSendSpec(parameter_format="POSITIONAL", body_parameter_count=2)
    params = build_outreach_template_body_parameters(lead, spec=spec)
    assert params is not None
    assert [(param.text, param.parameter_name) for param in params] == [
        ("Priya Sharma", None),
        ("Edutrust", None),
    ]

    components = _build_template_components(params)
    assert components == [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Priya Sharma"},
                {"type": "text", "text": "Edutrust"},
            ],
        }
    ]

    named_spec = MetaTemplateSendSpec(
        parameter_format="NAMED",
        body_parameter_count=2,
        body_named_parameter_names=("student_name", "company_name"),
    )
    named = build_outreach_template_body_parameters(lead, spec=named_spec)
    assert named is not None
    assert [(param.text, param.parameter_name) for param in named] == [
        ("Priya Sharma", "student_name"),
        ("Edutrust", "company_name"),
    ]

    empty_spec = MetaTemplateSendSpec(parameter_format="POSITIONAL", body_parameter_count=0)
    assert build_outreach_template_body_parameters(lead, spec=empty_spec) is None


def test_format_meta_graph_error_parameter_count(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE", "et_student_welcome")
    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS", "student,company")

    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "(#132000) Number of parameters does not match the expected number of params",
                "type": "OAuthException",
                "code": 132000,
            }
        },
    )
    detail = format_meta_graph_error(response)
    assert "et_student_welcome" in detail
    assert "Add variable" in detail


def test_extract_meta_message_id_requires_wamid() -> None:
    ok = httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})
    assert extract_meta_message_id(ok) == "wamid.test"

    missing = httpx.Response(200, json={"messages": []})
    with pytest.raises(WhatsAppDeliveryError):
        extract_meta_message_id(missing)


def test_assert_whatsapp_business_outreach_allowed_without_template_or_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE", "")

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    db = SimpleNamespace(query=lambda *args, **kwargs: _Query())
    with pytest.raises(ValueError, match="WHATSAPP_OUTREACH_TEMPLATE"):
        assert_whatsapp_business_outreach_allowed(db, lead_id=1)


def test_assert_whatsapp_business_outreach_allowed_with_recent_inbound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_TEMPLATE", "")

    recent = SimpleNamespace(id=1, created_at=datetime.utcnow())
    calls = {"count": 0}

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            calls["count"] += 1
            return recent if calls["count"] == 1 else None

    db = SimpleNamespace(query=lambda *args, **kwargs: _Query())
    assert_whatsapp_business_outreach_allowed(db, lead_id=1)


def test_outreach_followup_template_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings
    from app.services.messaging import outreach_followup_template_is_configured

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE", "")
    assert outreach_followup_template_is_configured() is False
    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE", "et_intake_fullname")
    assert outreach_followup_template_is_configured() is True


def test_format_outreach_template_display_text_includes_intake_when_combined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.messaging import (
        MetaTemplateSendSpec,
        OutreachTemplateParameter,
        format_outreach_template_display_text,
    )

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP", True)
    params = [
        OutreachTemplateParameter(text="Priya"),
        OutreachTemplateParameter(text="Edutrust"),
    ]
    text = format_outreach_template_display_text(params, template_name="et_student_welcome")
    assert "Thanks for reaching Edutrust" in text
    assert "reply with your full name" in text.lower()


def test_format_outreach_template_display_text_uses_meta_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from app.services.messaging import (
        MetaTemplateSendSpec,
        OutreachTemplateParameter,
        format_outreach_template_display_text,
    )

    monkeypatch.setattr(settings, "WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP", False)
    spec = MetaTemplateSendSpec(
        parameter_format="POSITIONAL",
        body_parameter_count=2,
        body_text=(
            "Hi {{1}}! Thanks for reaching {{2}}.\n\n"
            "To book your free study abroad consultation, simply reply with your full name."
        ),
    )
    params = [
        OutreachTemplateParameter(text="Priya"),
        OutreachTemplateParameter(text="Edutrust"),
    ]
    text = format_outreach_template_display_text(
        params,
        template_name="et_student_welcome",
        spec=spec,
    )
    assert "Hi Priya! Thanks for reaching Edutrust." in text
    assert "simply reply with your full name" in text
    assert "We're excited to help" not in text


def test_template_body_includes_intake_prompt() -> None:
    from app.services.messaging import template_body_includes_intake_prompt

    assert template_body_includes_intake_prompt(
        "To book your free study abroad consultation, simply reply with your full name."
    )
    assert not template_body_includes_intake_prompt(
        "Hi {{1}}! Thanks for reaching {{2}}. We're excited to help you get started."
    )
