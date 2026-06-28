from __future__ import annotations

import asyncio
import logging
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
    language_code: str = "en_US",
) -> bool:
    """Send an approved Meta WhatsApp template (required to open business-initiated chats)."""
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    phone_number_id = resolve_whatsapp_phone_number_id()

    if not access_token or not phone_number_id:
        raise WhatsAppDeliveryError(
            "WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured."
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone_number(to_number),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    url = f"{WHATSAPP_GRAPH_API_BASE}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            detail = response.text
            try:
                err = response.json().get("error", {})
                detail = err.get("message") or detail
            except Exception:
                pass
            logger.error(
                "WhatsApp template delivery failed: template=%s status=%s body=%s",
                template_name,
                response.status_code,
                response.text,
            )
            raise WhatsAppDeliveryError(detail, status_code=response.status_code)
        return True


async def open_whatsapp_conversation_window(
    to_number: str,
    *,
    raise_on_failure: bool = False,
) -> None:
    """
    Open the Meta messaging window with an approved template before session messages.

    Skipped when PROVIDER is not WHATSAPP or WHATSAPP_OUTREACH_TEMPLATE is unset.
    When raise_on_failure is True, template delivery errors propagate to the caller.
    """
    if get_active_provider() != PROVIDER_WHATSAPP:
        return

    template_name = (settings.WHATSAPP_OUTREACH_TEMPLATE or "").strip()
    if not template_name:
        if raise_on_failure:
            raise WhatsAppDeliveryError(
                "WHATSAPP_OUTREACH_TEMPLATE is not configured for business-initiated outreach."
            )
        return

    try:
        await send_whatsapp_template(to_number, template_name)
        logger.info(
            "Sent WhatsApp outreach template %r to %s",
            template_name,
            clean_phone_number(to_number),
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
                detail = response.text
                try:
                    err = response.json().get("error", {})
                    detail = err.get("message") or detail
                    if err.get("code") == 131030:
                        detail = (
                            f"{detail} Add {clean_phone_number(to_number)} as a test recipient "
                            "in Meta Developer Console → WhatsApp → API Setup."
                        )
                except Exception:
                    pass
                logger.error(
                    "WhatsApp Graph API delivery failed: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
                raise WhatsAppDeliveryError(detail, status_code=response.status_code)
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
    from app.services.whatsapp_webhook_env import (
        extract_webhook_phone_number_id,
        should_process_inbound_phone_number_id,
    )

    inbound_phone_id = extract_webhook_phone_number_id(payload)
    if not should_process_inbound_phone_number_id(inbound_phone_id):
        return

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
