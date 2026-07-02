from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.services.whatsapp_config import resolve_whatsapp_phone_number_id
from app.db.database import SessionLocal
from app.models.lead import Lead
from app.models.message import Message
from app.models.message_history import MessageHistory
from app.models.processed_message import ProcessedMessage
from app.services.conversation_audit_service import log_ai_interaction
from app.services.handoff_notifications import notify_advisors_of_handoff
from app.services.lead_conversation import ensure_handoff_for_inbound, is_human_handoff_lead
from app.services.phone_utils import clean_phone_number
from app.services.twilio_outbound import dispatch_live_whatsapp_message
from app.services.whatsapp_helpers import extract_inbound_messages, get_or_create_lead_for_phone

logger = logging.getLogger(__name__)


def record_ai_conversation_audit(
    db: Session,
    *,
    lead_id: int,
    student_message: str,
    ai_reply: str,
    ai_model: str,
    confidence_score: float | None,
    escalated: bool,
    commit: bool = True,
):
    """Capture one AI interaction turn for the Agent Console audit dashboard."""
    return log_ai_interaction(
        db,
        lead_id=lead_id,
        student_message=student_message,
        ai_reply=ai_reply,
        ai_model=ai_model,
        confidence_score=confidence_score,
        escalated=escalated,
        commit=commit,
    )


PROVIDER_WHATSAPP = "WHATSAPP"
PROVIDER_TWILIO = "TWILIO"
WHATSAPP_GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class WhatsAppDeliveryError(Exception):
    """Raised when Meta Graph API or Twilio outbound delivery fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ParsedWhatsAppPayload:
    sender_id: str
    message_body: str
    message_id: str | None = None
    sender_phone: str | None = None


def get_active_provider() -> str:
    provider = (settings.PROVIDER or PROVIDER_TWILIO).strip().upper()
    if provider not in {PROVIDER_WHATSAPP, PROVIDER_TWILIO}:
        logger.warning("Unknown PROVIDER=%r; defaulting to TWILIO", provider)
        return PROVIDER_TWILIO
    return provider


META_ERROR_TEST_RECIPIENT = 131030
META_ERROR_RE_ENGAGEMENT = 131047
META_ERROR_TEMPLATE_TRANSLATION = 132001
META_ERROR_PARAMETER_COUNT = 132000

OUTREACH_TEMPLATE_PARAMETER_SLOTS = frozenset({"student", "company"})
DEFAULT_NAMED_PARAMETER_NAMES = {
    "student": "student_name",
    "company": "company_name",
}


@dataclass(frozen=True)
class OutreachTemplateParameter:
    text: str
    parameter_name: str | None = None


@dataclass(frozen=True)
class OutreachTemplateSendResult:
    template_name: str
    message_id: str
    display_text: str


# Brief pause after Meta accepts the template so WhatsApp usually delivers it before session text.
OUTREACH_TEMPLATE_FOLLOWUP_DELAY_SECONDS = 8.0


def outreach_template_is_configured() -> bool:
    return bool((settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip())


def format_outreach_template_display_text(
    body_parameters: list[OutreachTemplateParameter] | None,
    *,
    template_name: str | None = None,
) -> str:
    """Human-readable preview of the outreach template for chat history."""
    name = (template_name or settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip() or "template"
    if not body_parameters:
        return f"[WhatsApp template: {name}]"
    student = body_parameters[0].text if body_parameters else "there"
    if len(body_parameters) >= 2:
        company = body_parameters[1].text
        return (
            f"Hi {student}! Thanks for reaching {company}. "
            "We're excited to help you get started with your study abroad plans."
        )
    return f"Hi {student}!"


@dataclass(frozen=True)
class MetaTemplateSendSpec:
    parameter_format: str
    body_parameter_count: int
    body_named_parameter_names: tuple[str, ...] = ()


_TEMPLATE_SPEC_CACHE: dict[str, MetaTemplateSendSpec] = {}
_NAMED_PLACEHOLDER_RE = re.compile(r"\{\{([^}]+)\}\}")


def resolve_outreach_template_language() -> str:
    """Language code for WHATSAPP_OUTREACH_TEMPLATE (must match Meta Business Manager)."""
    raw = (settings.WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE or "en").strip()
    return raw or "en"


def resolve_outreach_company_name() -> str:
    """Company/business name substituted into outreach template {{2}}."""
    raw = (settings.WHATSAPP_OUTREACH_COMPANY_NAME or "Edutrust").strip()
    return raw or "Edutrust"


def resolve_outreach_template_parameter_slots() -> tuple[str, ...]:
    """
    Which body placeholders to send, in template order.

    WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS examples:
    - student,company  → Student Name + Company Name (et_student_welcome)
    - student          → one variable only
    - (empty)          → static template, no components block
    """
    raw = (settings.WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS or "").strip()
    if not raw:
        return ()
    slots: list[str] = []
    for part in raw.split(","):
        slot = part.strip().lower()
        if slot in OUTREACH_TEMPLATE_PARAMETER_SLOTS and slot not in slots:
            slots.append(slot)
    return tuple(slots)


def outreach_template_uses_named_parameters() -> bool:
    fmt = (settings.WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT or "named").strip().lower()
    return fmt == "named"


def resolve_outreach_template_parameter_meta_names(slots: tuple[str, ...]) -> tuple[str, ...]:
    raw = (settings.WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_NAMES or "").strip()
    if raw:
        names = tuple(part.strip() for part in raw.split(",") if part.strip())
        if len(names) == len(slots):
            return names
    return tuple(DEFAULT_NAMED_PARAMETER_NAMES.get(slot, slot) for slot in slots)


def _parse_body_parameter_spec(body_component: dict[str, Any]) -> tuple[int, tuple[str, ...]]:
    example = body_component.get("example") or {}
    named_params = example.get("body_text_named_params") or []
    if named_params:
        names = tuple(
            str(item.get("param_name", "")).strip()
            for item in named_params
            if str(item.get("param_name", "")).strip()
        )
        return len(names), names

    body_text_rows = example.get("body_text") or []
    if body_text_rows and body_text_rows[0]:
        return len(body_text_rows[0]), ()

    text = str(body_component.get("text") or "")
    # Only {{...}} markers are real send-time variables. Square brackets like
    # [Student Name] in Meta's API text are often static labels, not parameters.
    named_in_text = _NAMED_PLACEHOLDER_RE.findall(text)
    if named_in_text:
        return len(named_in_text), tuple(name.strip() for name in named_in_text)

    positional_numeric = re.findall(r"\{\{(\d+)\}\}", text)
    if positional_numeric:
        return len(positional_numeric), ()

    return 0, ()


def _language_codes_match(template_language: str, requested_language: str) -> bool:
    left = (template_language or "").strip().lower().replace("-", "_")
    right = (requested_language or "").strip().lower().replace("-", "_")
    return left == right or left.split("_")[0] == right.split("_")[0]


async def fetch_meta_outreach_template_spec(
    template_name: str,
    language_code: str,
) -> MetaTemplateSendSpec | None:
    """Load approved template metadata from Meta so send payload matches parameter_format."""
    cache_key = f"{template_name}:{language_code}".lower()
    if cache_key in _TEMPLATE_SPEC_CACHE:
        return _TEMPLATE_SPEC_CACHE[cache_key]

    from app.services.whatsapp_config import resolve_whatsapp_waba_id

    waba_id = resolve_whatsapp_waba_id()
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    if not waba_id or not access_token:
        return None

    url = f"{WHATSAPP_GRAPH_API_BASE}/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                params={"name": template_name, "limit": "50"},
                headers=headers,
            )
            if response.status_code >= 400:
                logger.warning(
                    "Could not load WhatsApp template %r from Meta: status=%s body=%s",
                    template_name,
                    response.status_code,
                    response.text,
                )
                return None

            for template in response.json().get("data", []):
                if str(template.get("name") or "") != template_name:
                    continue
                if not _language_codes_match(str(template.get("language") or ""), language_code):
                    continue

                body_component = next(
                    (
                        component
                        for component in template.get("components", [])
                        if str(component.get("type") or "").upper() == "BODY"
                    ),
                    None,
                )
                if not body_component:
                    spec = MetaTemplateSendSpec(
                        parameter_format=str(template.get("parameter_format") or "POSITIONAL").upper(),
                        body_parameter_count=0,
                    )
                else:
                    count, names = _parse_body_parameter_spec(body_component)
                    spec = MetaTemplateSendSpec(
                        parameter_format=str(template.get("parameter_format") or "POSITIONAL").upper(),
                        body_parameter_count=count,
                        body_named_parameter_names=names,
                    )
                _TEMPLATE_SPEC_CACHE[cache_key] = spec
                logger.info(
                    "Loaded WhatsApp template spec for %r (%s): format=%s body_params=%s names=%s",
                    template_name,
                    language_code,
                    spec.parameter_format,
                    spec.body_parameter_count,
                    spec.body_named_parameter_names,
                )
                return spec
    except Exception:
        logger.exception("Failed to fetch WhatsApp template spec for %r", template_name)
    return None


def resolve_outreach_student_name(lead: Lead | None = None) -> str:
    from app.services.intake_templates import student_first_name

    if lead is None:
        return "there"
    raw_name = (lead.full_name or "").strip()
    if raw_name and "whatsapp contact" not in raw_name.lower():
        return raw_name
    return student_first_name(lead)


def build_outreach_template_body_parameters(
    lead: Lead | None = None,
    *,
    spec: MetaTemplateSendSpec | None = None,
) -> list[OutreachTemplateParameter] | None:
    """
    Body placeholders for et_student_welcome:
    Hi {{1}}! Thanks for reaching {{2}}... (Meta parameter_format=POSITIONAL)
    """
    slots = resolve_outreach_template_parameter_slots()
    if spec is not None:
        if spec.body_parameter_count <= 0:
            return None
        if len(slots) != spec.body_parameter_count:
            default_order = ("student", "company")
            slots = default_order[: spec.body_parameter_count]
        use_named = spec.parameter_format == "NAMED"
        meta_names = (
            spec.body_named_parameter_names or resolve_outreach_template_parameter_meta_names(slots)
            if use_named
            else ()
        )
    else:
        if not slots:
            return None
        use_named = outreach_template_uses_named_parameters()
        meta_names = resolve_outreach_template_parameter_meta_names(slots) if use_named else ()

    if not slots:
        return None

    values = {
        "student": resolve_outreach_student_name(lead),
        "company": resolve_outreach_company_name(),
    }

    parameters: list[OutreachTemplateParameter] = []
    for index, slot in enumerate(slots):
        parameter_name = meta_names[index] if use_named and index < len(meta_names) else None
        parameters.append(
            OutreachTemplateParameter(
                text=values[slot],
                parameter_name=parameter_name,
            )
        )
    return parameters


def _build_template_components(
    body_parameters: list[OutreachTemplateParameter] | None,
) -> list[dict[str, Any]] | None:
    if not body_parameters:
        return None
    parameters: list[dict[str, Any]] = []
    for param in body_parameters:
        entry: dict[str, Any] = {"type": "text", "text": str(param.text)[:1024]}
        if param.parameter_name:
            entry["parameter_name"] = param.parameter_name
        parameters.append(entry)
    return [{"type": "body", "parameters": parameters}]


def format_meta_graph_error(response: httpx.Response, *, to_number: str | None = None) -> str:
    """Turn a Meta Graph API error response into a user-facing message."""
    detail = response.text
    try:
        err = response.json().get("error", {})
        detail = err.get("message") or detail
        code = err.get("code")
        if code == META_ERROR_TEST_RECIPIENT and to_number:
            detail = (
                f"{detail} Add {clean_phone_number(to_number)} as a test recipient "
                "in Meta Developer Console → WhatsApp → API Setup."
            )
        elif code == META_ERROR_RE_ENGAGEMENT:
            detail = (
                "WhatsApp cannot deliver business-initiated session messages outside the "
                "24-hour customer care window. Set WHATSAPP_OUTREACH_TEMPLATE to an approved "
                "Meta template (for example et_student_welcome), or ask the student to message your "
                "business number first."
            )
        elif code == META_ERROR_TEMPLATE_TRANSLATION:
            template = (settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip() or "your template"
            language = resolve_outreach_template_language()
            detail = (
                f'Template "{template}" is not available for language code "{language}". '
                "In Meta Business Manager → WhatsApp Manager → Message templates, open the "
                "template and note its language (English = en, English (US) = en_US). "
                "Set WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE in .env to that exact code."
            )
        elif code == META_ERROR_PARAMETER_COUNT:
            template = (settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip() or "your template"
            meta_detail = err.get("error_data") or err.get("error_user_msg") or ""
            detail = (
                f'Template "{template}" parameter mismatch. {meta_detail} '
                "If details say expected number of params (0), the template body uses static text "
                'like [Student Name] instead of Meta variables — recreate the template in WhatsApp '
                "Manager using Add variable ({{1}}, {{2}}), not typed square brackets."
            )
    except Exception:
        pass
    return detail


def extract_meta_message_id(response: httpx.Response) -> str:
    """Require a wamid from a successful Meta /messages response."""
    try:
        data = response.json()
    except Exception as exc:
        raise WhatsAppDeliveryError(
            "Meta accepted the request but returned an unreadable response."
        ) from exc
    messages = data.get("messages") or []
    message_id = messages[0].get("id") if messages else None
    if not message_id:
        raise WhatsAppDeliveryError(
            "Meta accepted the request but did not return a WhatsApp message id; "
            "the message was likely not queued for delivery."
        )
    return str(message_id)


def lead_has_open_whatsapp_messaging_window(
    db: Session,
    lead_id: int,
    *,
    hours: int = 24,
) -> bool:
    """True when the student has messaged within Meta's customer care window."""
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    inbound_message = (
        db.query(Message.id)
        .filter(
            Message.lead_id == lead_id,
            Message.sender.in_(("student", "candidate")),
            Message.created_at >= cutoff,
        )
        .first()
    )
    if inbound_message:
        return True

    inbound_history = (
        db.query(MessageHistory.id)
        .filter(
            MessageHistory.lead_id == lead_id,
            MessageHistory.role == "user",
            MessageHistory.created_at >= cutoff,
        )
        .first()
    )
    return inbound_history is not None


def assert_whatsapp_business_outreach_allowed(db: Session, lead_id: int) -> None:
    """
    Meta only allows business-initiated chats via an approved template, unless the
    student has already opened a session within the last 24 hours.
    """
    template_name = (settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip()
    if template_name:
        return
    if lead_has_open_whatsapp_messaging_window(db, lead_id):
        return
    raise ValueError(
        "Cannot start WhatsApp outreach without an approved template: this student has not "
        "messaged your business number in the last 24 hours. Set WHATSAPP_OUTREACH_TEMPLATE "
        "in .env to an approved Meta template (for example et_student_welcome), or ask the student "
        "to message your WhatsApp business line first."
    )


def _lead_has_recent_handoff_notice(db: Session, lead_id: int, *, within_minutes: int = 240) -> bool:
    from datetime import datetime, timedelta

    from app.services.ai_service import HANDOFF_NOTICE_MARKERS

    cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
    recent = (
        db.query(Message)
        .filter(
            Message.lead_id == lead_id,
            Message.sender.in_(["advisor", "system"]),
            Message.created_at >= cutoff,
        )
        .order_by(Message.id.desc())
        .limit(8)
        .all()
    )
    for msg in recent:
        text = msg.text or ""
        if any(marker in text for marker in HANDOFF_NOTICE_MARKERS):
            return True
    return False


def _recent_identical_outbound(
    db: Session,
    lead_id: int,
    text: str,
    *,
    within_minutes: int = 2,
) -> bool:
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
    recent = (
        db.query(Message)
        .filter(
            Message.lead_id == lead_id,
            Message.sender.in_(["advisor", "system"]),
            Message.created_at >= cutoff,
        )
        .order_by(Message.id.desc())
        .limit(3)
        .all()
    )
    target = (text or "").strip()
    return any((msg.text or "").strip() == target for msg in recent)


async def acknowledge_handoff_inbound(
    db: Session,
    lead: Lead,
    sender_phone: str,
    message_text: str,
) -> None:
    """Keep the student informed while a human advisor owns the thread."""
    from app.services.ai_service import build_handoff_followup_notice, build_handoff_student_notice
    from app.services.twilio_ai_conversation import persist_and_send_ai_message

    ensure_handoff_for_inbound(db, lead)
    notify_advisors_of_handoff(
        db,
        lead,
        reason=lead.handoff_reason or "follow-up message during handoff",
        message_preview=message_text,
        ai_confidence=lead.handoff_ai_confidence,
    )

    if _lead_has_recent_handoff_notice(db, lead.id, within_minutes=240):
        notice = build_handoff_followup_notice(lead, message_text)
    else:
        notice = build_handoff_student_notice(lead)

    if _recent_identical_outbound(db, lead.id, notice.text, within_minutes=2):
        db.commit()
        return

    await persist_and_send_ai_message(db, lead, sender_phone, notice.text, ai_confidence=notice.confidence)


async def dispatch_inbound_whatsapp_ai(
    db: Session,
    lead: Lead,
    sender_phone: str,
    message_text: str,
    *,
    flow_data: str | None = None,
) -> None:
    """
    Route inbound WhatsApp text through the unified AI Active interceptor pipeline.
    """
    from app.services.lead_conversation import (
        release_ai_handoff,
        should_retry_ai_after_handoff,
    )

    if is_human_handoff_lead(lead):
        if should_retry_ai_after_handoff(lead):
            release_ai_handoff(db, lead)
            db.commit()
        else:
            await acknowledge_handoff_inbound(db, lead, sender_phone, message_text)
            return

    from app.services.twilio_ai_conversation import handle_ai_active_inbound

    await handle_ai_active_inbound(db, lead, message_text, sender_phone, flow_data=flow_data)


def parse_whatsapp_payload(data: dict[str, Any]) -> ParsedWhatsAppPayload | None:
    """
    Extract a single inbound text message from a Meta Cloud API webhook payload.

    Returns None for status updates, delivery receipts, media-only payloads, or
    malformed structures so callers can ignore non-message events quietly.
    """
    try:
        value = data["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        logger.debug("Meta webhook payload missing entry/changes/value structure")
        return None

    if "messages" not in value:
        logger.debug("Meta webhook payload has no messages key (likely status update)")
        return None

    messages = value.get("messages") or []
    if not messages:
        return None

    message = messages[0]
    message_type = message.get("type")

    message_body = ""
    if message_type == "text":
        message_body = ((message.get("text") or {}).get("body") or "").strip()
    elif message_type in {"button", "interactive"}:
        # Non-text interactive payloads are ignored here; extract_inbound_messages handles them.
        logger.debug("Meta webhook non-plain-text message type=%r skipped by parse_whatsapp_payload", message_type)
        return None
    else:
        logger.debug("Meta webhook unsupported message type=%r", message_type)
        return None

    if not message_body:
        return None

    contacts = value.get("contacts") or []
    sender_id = ""
    if contacts:
        sender_id = str(contacts[0].get("wa_id") or "").strip()
    if not sender_id:
        sender_id = str(message.get("from") or "").strip()

    if not sender_id:
        return None

    sender_phone = clean_phone_number(sender_id)
    return ParsedWhatsAppPayload(
        sender_id=sender_id,
        message_body=message_body,
        message_id=str(message.get("id") or "") or None,
        sender_phone=sender_phone or sender_id,
    )


async def send_message(to_number: str, body: str, *, media_url: str | None = None) -> bool:
    """
    Unified outbound WhatsApp send.

    Routes by settings.PROVIDER:
    - WHATSAPP: Meta Graph API (Bearer WHATSAPP_ACCESS_TOKEN)
    - TWILIO: existing Twilio client
    """
    provider = get_active_provider()
    if provider == PROVIDER_WHATSAPP:
        return await _send_via_whatsapp_graph(to_number, body)
    return await asyncio.to_thread(dispatch_live_whatsapp_message, to_number, body, media_url)


def send_message_sync(to_number: str, body: str, *, media_url: str | None = None) -> bool:
    """Synchronous wrapper for legacy call sites outside a running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(send_message(to_number, body, media_url=media_url))

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            asyncio.run, send_message(to_number, body, media_url=media_url)
        ).result()


async def send_whatsapp_template(
    to_number: str,
    template_name: str,
    *,
    language_code: str | None = None,
    body_parameters: list[OutreachTemplateParameter] | None = None,
) -> str:
    """Send an approved Meta WhatsApp template (required to open business-initiated chats)."""
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    phone_number_id = resolve_whatsapp_phone_number_id()
    resolved_language = (language_code or resolve_outreach_template_language()).strip()

    if not access_token or not phone_number_id:
        raise WhatsAppDeliveryError(
            "WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured."
        )

    template_payload: dict[str, Any] = {
        "name": template_name,
        "language": {"code": resolved_language},
    }
    components = _build_template_components(body_parameters)
    if components:
        template_payload["components"] = components

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "template",
        "template": template_payload,
    }
    url = f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            detail = format_meta_graph_error(response, to_number=to_number)
            logger.error(
                "WhatsApp template delivery failed: template=%s status=%s body=%s",
                template_name,
                response.status_code,
                response.text,
            )
            raise WhatsAppDeliveryError(detail, status_code=response.status_code)
        message_id = extract_meta_message_id(response)
        return message_id


async def send_whatsapp_outreach_template(
    to_number: str,
    *,
    lead: Lead | None = None,
    raise_on_failure: bool = False,
) -> OutreachTemplateSendResult | None:
    """
    Send the configured Meta outreach template and return only after Meta accepts it.
    """
    if get_active_provider() != PROVIDER_WHATSAPP:
        return None

    template_name = (settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip()
    if not template_name:
        logger.info(
            "WHATSAPP_OUTREACH_TEMPLATE is not set; skipping template send to %s.",
            clean_phone_number(to_number),
        )
        return None

    try:
        language_code = resolve_outreach_template_language()
        spec = await fetch_meta_outreach_template_spec(template_name, language_code)
        body_parameters = build_outreach_template_body_parameters(lead, spec=spec)
        if spec and spec.body_parameter_count == 0:
            logger.warning(
                "WhatsApp template %r has no Meta body variables (static text only). "
                "Recreate it in WhatsApp Manager with Add variable for student and company names.",
                template_name,
            )
        message_id = await send_whatsapp_template(
            to_number,
            template_name,
            language_code=language_code,
            body_parameters=body_parameters,
        )
        display_text = format_outreach_template_display_text(
            body_parameters,
            template_name=template_name,
        )
        logger.info(
            "Sent WhatsApp outreach template %r (%s) to %s message_id=%s",
            template_name,
            language_code,
            clean_phone_number(to_number),
            message_id,
        )
        return OutreachTemplateSendResult(
            template_name=template_name,
            message_id=message_id,
            display_text=display_text,
        )
    except WhatsAppDeliveryError as exc:
        logger.warning(
            "WhatsApp outreach template %r failed for %s: %s",
            template_name,
            clean_phone_number(to_number),
            exc,
        )
        if raise_on_failure:
            raise
        return None


async def open_whatsapp_conversation_window(
    to_number: str,
    *,
    lead: Lead | None = None,
    raise_on_failure: bool = False,
) -> OutreachTemplateSendResult | None:
    """Backward-compatible wrapper around send_whatsapp_outreach_template."""
    return await send_whatsapp_outreach_template(
        to_number,
        lead=lead,
        raise_on_failure=raise_on_failure,
    )


async def _send_via_whatsapp_graph(to_number: str, body: str) -> bool:
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    phone_number_id = resolve_whatsapp_phone_number_id()

    if not access_token or not phone_number_id:
        raise WhatsAppDeliveryError(
            "WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured."
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "text",
        "text": {"body": body},
    }
    url = f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                detail = format_meta_graph_error(response, to_number=to_number)
                logger.error(
                    "WhatsApp Graph API delivery failed: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
                raise WhatsAppDeliveryError(detail, status_code=response.status_code)
            extract_meta_message_id(response)
            return True
    except WhatsAppDeliveryError:
        raise
    except Exception as exc:
        logger.exception("WhatsApp Graph API request failed.")
        raise WhatsAppDeliveryError(str(exc)) from exc


async def process_meta_webhook_payload(payload: dict[str, Any]) -> None:
    """
    Background worker for POST /api/webhook (WhatsApp messaging only).

    Meta Lead Ads leadgen payloads are handled by process_leadgen_webhook_payload().
    """
    from app.services.whatsapp_outreach_delivery import process_whatsapp_status_webhook
    from app.services.whatsapp_webhook_env import (
        extract_webhook_phone_number_id,
        should_process_inbound_phone_number_id,
    )

    inbound_phone_id = extract_webhook_phone_number_id(payload)
    if not should_process_inbound_phone_number_id(inbound_phone_id):
        return

    status_count = process_whatsapp_status_webhook(payload)
    if status_count:
        logger.info("Meta webhook processed %s outbound status update(s)", status_count)

    parsed_preview = parse_whatsapp_payload(payload)
    if parsed_preview:
        logger.info(
            "Meta webhook parsed preview: sender_id=%r message_body=%r message_id=%r",
            parsed_preview.sender_id,
            parsed_preview.message_body,
            parsed_preview.message_id,
        )
        print(
            "[Meta Webhook] parsed: "
            f"sender_id={parsed_preview.sender_id!r} "
            f"message_body={parsed_preview.message_body!r}"
        )

    inbound_messages = extract_inbound_messages(payload)
    if not inbound_messages:
        logger.info(
            "Meta webhook: no inbound text messages (delivery receipt or unsupported type). object=%r",
            payload.get("object"),
        )
        print(
            "[Meta Webhook] no inbound text messages to save "
            f"(object={payload.get('object')!r} — may be a delivery status update only)"
        )
        return

    db = SessionLocal()
    try:
        processed_count = await _persist_inbound_messages(db, inbound_messages)
        logger.info("Meta webhook processed %s inbound message(s)", processed_count)
    finally:
        db.close()


async def _persist_inbound_messages(db: Session, inbound_messages) -> int:
    processed_count = 0

    for inbound in inbound_messages:
        try:
            already_processed = (
                db.query(ProcessedMessage)
                .filter(ProcessedMessage.message_id == inbound.message_id)
                .first()
            )
            if already_processed:
                logger.info("Duplicate Meta webhook message ignored: %s", inbound.message_id)
                continue

            lead = get_or_create_lead_for_phone(
                db,
                sender_phone=inbound.sender_phone,
                wa_id=inbound.wa_id,
            )

            if is_human_handoff_lead(lead):
                ensure_handoff_for_inbound(db, lead)

            display_text = inbound.message_text
            try:
                from app.services.admissions_intake_flow import format_inbound_booking_selection

                display_text = format_inbound_booking_selection(db, inbound.message_text)
            except Exception:
                display_text = inbound.message_text

            db.add(
                MessageHistory(
                    lead_id=lead.id,
                    wa_id=inbound.wa_id,
                    sender_phone=inbound.sender_phone,
                    role="user",
                    message_text=display_text,
                    wa_message_id=inbound.message_id,
                )
            )
            db.add(
                Message(
                    lead_id=lead.id,
                    sender="candidate",
                    text=display_text,
                    is_read=False,
                )
            )
            db.add(ProcessedMessage(message_id=inbound.message_id))
            db.commit()

            from app.services.student_status_service import on_whatsapp_inbound

            on_whatsapp_inbound(db, lead)

            try:
                await dispatch_inbound_whatsapp_ai(
                    db,
                    lead,
                    inbound.sender_phone,
                    inbound.message_text,
                )
            except Exception:
                logger.exception(
                    "AI reply failed for lead %s after inbound WhatsApp message",
                    lead.id,
                )

            processed_count += 1
        except IntegrityError:
            db.rollback()
            logger.info(
                "Duplicate Meta webhook message ignored via unique constraint: %s",
                inbound.message_id,
            )
        except Exception:
            logger.exception(
                "Failed to persist Meta webhook message %s",
                inbound.message_id,
            )
            db.rollback()

    return processed_count
