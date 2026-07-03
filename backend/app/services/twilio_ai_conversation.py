from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.services.admissions_intake_flow import (
    BRAND_NAME,
    IntakeReply,
    begin_whatsapp_intake_session,
    handle_post_intake_booking_message,
    is_intake_complete,
    process_flow_completion,
    process_intake_message,
)
from app.services.intake_templates import render_outreach_intake_followup
from app.services.agent_runtime import (
    RuntimeAgentConfig,
    get_runtime_agent_config,
    should_escalate_before_llm,
)
from app.services.ai_service import LlmResult, compose_agent_message, compose_handoff_acknowledgement
from app.services.handoff_notifications import notify_advisors_of_handoff
from app.services.lead_conversation import ensure_handoff_for_inbound, touch_lead_activity
from app.services.phone_utils import clean_phone_number
from app.config import settings
from app.services.messaging import (
    OUTREACH_POST_TEMPLATE_CONFIRMED_DELAY_SECONDS,
    OUTREACH_POST_TEMPLATE_UNCONFIRMED_DELAY_SECONDS,
    OUTREACH_TEMPLATE_FOLLOWUP_DELAY_SECONDS,
    PROVIDER_WHATSAPP,
    WhatsAppDeliveryError,
    assert_whatsapp_business_outreach_allowed,
    get_active_provider,
    outreach_template_is_configured,
    record_ai_conversation_audit,
    send_message,
    send_whatsapp_outreach_template,
    send_whatsapp_text_message,
)
from app.services.whatsapp_outreach_delivery import (
    wait_for_outbound_delivery_outcome,
    wait_for_whatsapp_template_delivered,
)

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20


async def _send_outreach_session_followup(
    phone: str,
    text: str,
    *,
    retry_delay: float,
    delivery_wait_seconds: float,
    max_attempts: int = 2,
) -> None:
    """
    Send the post-template intake prompt and confirm Meta accepted/delivered it.

    Retries only when Meta reports failed — not on timeout (avoids duplicate texts).
    """
    last_error: WhatsAppDeliveryError | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(
                "Retrying outreach session follow-up (attempt %s/%s) after Meta failure",
                attempt,
                max_attempts,
            )
            await asyncio.sleep(retry_delay)

        message_id = await send_whatsapp_text_message(phone, text)
        outcome = await wait_for_outbound_delivery_outcome(
            message_id,
            timeout_seconds=delivery_wait_seconds,
        )
        logger.info(
            "Outreach session follow-up message_id=%s outcome=%s attempt=%s",
            message_id,
            outcome,
            attempt,
        )

        if outcome in {"delivered", "read", "sent", "timeout"}:
            return

        last_error = WhatsAppDeliveryError(
            f"WhatsApp reported follow-up delivery failed (message_id={message_id})."
        )

    if last_error is not None:
        raise last_error
    raise WhatsAppDeliveryError("WhatsApp follow-up could not be delivered.")


def lead_has_prior_ai_outreach(db: Session, lead_id: int) -> bool:
    """True when the AI agent has already sent at least one WhatsApp message."""
    return (
        db.query(Message.id)
        .filter(Message.lead_id == lead_id, Message.sender == "advisor")
        .first()
        is not None
    )


def assert_ai_outreach_allowed(db: Session, lead: Lead, *, force_restart: bool = False) -> None:
    if lead_has_prior_ai_outreach(db, lead.id) and not force_restart:
        raise ValueError(
            "An AI WhatsApp conversation is already in progress for this student. "
            "Duplicate outreach is blocked to avoid restarting the intake flow."
        )
OUTREACH_SESSION_MARKER = f"{BRAND_NAME} Admissions AI Assistant on WhatsApp"
INTAKE_SESSION_MARKER = f"{BRAND_NAME} Admissions AI Assistant"


def _session_start_index(rows: list[Message]) -> int:
    """Ignore stale test messages before the latest outreach/intake welcome."""
    start_idx = 0
    for i, row in enumerate(rows):
        text = (row.text or "").strip()
        if row.sender not in ("advisor", "system") or not text:
            continue
        if OUTREACH_SESSION_MARKER in text or INTAKE_SESSION_MARKER in text:
            start_idx = i
    return start_idx


def load_conversation_history(db: Session, lead_id: int) -> list[tuple[str, str]]:
    rows = (
        db.query(Message)
        .filter(Message.lead_id == lead_id)
        .order_by(Message.created_at.desc())
        .limit(max(RECENT_HISTORY_LIMIT * 3, 50))
        .all()
    )
    rows = list(reversed(rows))
    rows = rows[_session_start_index(rows) :]
    if len(rows) > RECENT_HISTORY_LIMIT:
        rows = rows[-RECENT_HISTORY_LIMIT:]

    history: list[tuple[str, str]] = []
    for row in rows:
        text = (row.text or "").strip()
        if not text:
            continue
        if row.sender in ("student", "candidate"):
            history.append(("user", text))
        elif row.sender in ("advisor", "system"):
            history.append(("assistant", text))
    return history


def first_name_from_lead(lead: Lead) -> str:
    name = (lead.full_name or "there").strip()
    if not name:
        return "there"
    return name.split()[0]


def lead_has_ai_outbound_messages(db: Session, lead_id: int) -> bool:
    return (
        db.query(Message.id)
        .filter(Message.lead_id == lead_id, Message.sender.in_(["advisor", "system"]))
        .first()
        is not None
    )


async def generate_ai_reply(
    db: Session,
    lead: Lead,
    runtime_config: RuntimeAgentConfig,
    incoming_text: str | None = None,
) -> LlmResult:
    history = load_conversation_history(db, lead.id)
    latest_user = (incoming_text or "").strip()
    if latest_user and (not history or history[-1] != ("user", latest_user)):
        history = [*history, ("user", latest_user)]

    extra_context = "Intake is complete. Continue helping on WhatsApp with concise admissions guidance."
    if lead.consultation_scheduled_at:
        extra_context += (
            f" Consultation booked at {lead.consultation_scheduled_at.isoformat()}. "
            "If they ask to change it, explain they can reply with reschedule or cancel."
        )

    return await compose_agent_message(
        db,
        runtime_config,
        lead,
        task="Post-intake Q&A: answer the student's admissions question on WhatsApp.",
        incoming_text=latest_user,
        conversation_history=history,
        extra_context=extra_context,
    )


async def _deliver_whatsapp_text(target_phone: str, message_body: str) -> bool:
    if not target_phone or not message_body:
        raise WhatsAppDeliveryError("Missing phone number or message body for WhatsApp delivery.")
    if get_active_provider() == PROVIDER_WHATSAPP:
        return await send_message(to_number=target_phone, body=message_body)
    from app.services.twilio_outbound import dispatch_live_whatsapp_message

    if not dispatch_live_whatsapp_message(to_phone=target_phone, message_body=message_body):
        raise WhatsAppDeliveryError("Twilio WhatsApp delivery failed.")
    return True


async def persist_and_send_intake_reply(
    db: Session,
    lead: Lead,
    phone: str,
    reply: IntakeReply,
) -> Message:
    from app.services.twilio_whatsapp_interactive import dispatch_whatsapp_flow, dispatch_whatsapp_interactive

    stored_text = reply.text
    target_phone = clean_phone_number(phone or lead.phone_number or "")

    if not target_phone:
        raise WhatsAppDeliveryError("Missing phone number for WhatsApp delivery.")

    use_meta = get_active_provider() == PROVIDER_WHATSAPP
    if use_meta:
        from app.services.meta_whatsapp_interactive import deliver_meta_intake_reply

        stored_text = await deliver_meta_intake_reply(target_phone, reply)
    elif reply.whatsapp_flow:
        sent, delivered_text = dispatch_whatsapp_flow(target_phone, reply.whatsapp_flow)
        if sent:
            stored_text = f"{reply.text}\n\n[WhatsApp Flow: {reply.whatsapp_flow.button}]"
        else:
            stored_text = delivered_text
            await _deliver_whatsapp_text(target_phone, delivered_text)
    else:
        interactive = reply.quick_reply or reply.list_picker
        if interactive:
            sent, delivered_text = dispatch_whatsapp_interactive(target_phone, interactive)
            if sent:
                label = (
                    reply.quick_reply.actions[0].get("title", "Quick reply")
                    if reply.quick_reply
                    else reply.list_picker.button
                )
                stored_text = (
                    f"{reply.text}\n\n[WhatsApp interactive: {label}]"
                    if reply.text
                    else f"[WhatsApp interactive: {label}]"
                )
            else:
                stored_text = delivered_text
                await _deliver_whatsapp_text(target_phone, delivered_text)
        else:
            await _deliver_whatsapp_text(target_phone, reply.text)

    outbound = Message(
        lead_id=lead.id,
        sender="advisor",
        text=stored_text,
        ai_confidence=reply.confidence,
        is_read=True,
    )
    db.add(outbound)
    touch_lead_activity(db, lead)
    db.commit()
    db.refresh(outbound)
    return outbound


async def persist_advisor_message(
    db: Session,
    lead: Lead,
    message_body: str,
    *,
    ai_confidence: float | None = None,
) -> Message:
    """Save an advisor message to chat history without sending to WhatsApp."""
    outbound = Message(
        lead_id=lead.id,
        sender="advisor",
        text=message_body,
        ai_confidence=ai_confidence,
        is_read=True,
    )
    db.add(outbound)
    touch_lead_activity(db, lead)
    db.commit()
    db.refresh(outbound)
    return outbound


async def persist_and_send_ai_message(
    db: Session,
    lead: Lead,
    phone: str,
    message_body: str,
    *,
    ai_confidence: float | None = None,
) -> Message:
    target_phone = clean_phone_number(phone or lead.phone_number or "")
    if target_phone:
        await _deliver_whatsapp_text(target_phone, message_body)

    outbound = Message(
        lead_id=lead.id,
        sender="advisor",
        text=message_body,
        ai_confidence=ai_confidence,
        is_read=True,
    )
    db.add(outbound)
    touch_lead_activity(db, lead)
    db.commit()
    db.refresh(outbound)
    return outbound


async def _execute_escalation_handoff(
    db: Session,
    lead: Lead,
    phone: str,
    runtime_config: RuntimeAgentConfig,
    incoming_text: str,
    *,
    reason: str,
    ai_confidence: float | None = None,
) -> list[str]:
    ensure_handoff_for_inbound(db, lead)
    lead.handoff_reason = reason
    lead.handoff_ai_confidence = ai_confidence
    notify_advisors_of_handoff(
        db,
        lead,
        reason=reason,
        message_preview=incoming_text,
        ai_confidence=ai_confidence,
    )
    ack = await compose_handoff_acknowledgement(db, runtime_config, lead, incoming_text)
    await persist_and_send_ai_message(db, lead, phone, ack.text, ai_confidence=ack.confidence)
    record_ai_conversation_audit(
        db,
        lead_id=lead.id,
        student_message=incoming_text,
        ai_reply=ack.text,
        ai_model=runtime_config.ai_model,
        confidence_score=ai_confidence if ai_confidence is not None else ack.confidence,
        escalated=True,
        commit=False,
    )
    db.commit()
    return [ack.text]


def _audit_ai_turn(
    db: Session,
    *,
    lead: Lead,
    runtime_config: RuntimeAgentConfig,
    student_message: str,
    ai_reply: str,
    confidence_score: float | None,
    escalated: bool,
) -> None:
    record_ai_conversation_audit(
        db,
        lead_id=lead.id,
        student_message=student_message,
        ai_reply=ai_reply,
        ai_model=runtime_config.ai_model,
        confidence_score=confidence_score,
        escalated=escalated,
        commit=False,
    )


async def handle_ai_active_inbound(
    db: Session,
    lead: Lead,
    incoming_text: str,
    phone: str,
    flow_data: str | None = None,
) -> list[str]:
    runtime_config = get_runtime_agent_config(db)
    cleaned_incoming = (incoming_text or "").strip()

    if flow_data:
        flow_reply = process_flow_completion(db, lead, flow_data)
        if flow_reply:
            await persist_and_send_intake_reply(db, lead, phone, flow_reply)
            _audit_ai_turn(
                db,
                lead=lead,
                runtime_config=runtime_config,
                student_message=cleaned_incoming or "[flow completion]",
                ai_reply=flow_reply.text,
                confidence_score=getattr(flow_reply, "confidence", None),
                escalated=False,
            )
            db.commit()
            return [flow_reply.text]

    db.refresh(lead)

    if not is_intake_complete(lead):
        reply = await process_intake_message(db, lead, cleaned_incoming, runtime_config)
        if getattr(reply, "suppress_outbound", False):
            db.commit()
            return []
        if not reply.text.strip():
            return await _execute_escalation_handoff(
                db,
                lead,
                phone,
                runtime_config,
                cleaned_incoming,
                reason="AI could not generate a reliable answer during intake",
                ai_confidence=reply.confidence,
            )
        await persist_and_send_intake_reply(db, lead, phone, reply)
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        _audit_ai_turn(
            db,
            lead=lead,
            runtime_config=runtime_config,
            student_message=cleaned_incoming,
            ai_reply=reply.text,
            confidence_score=reply.confidence,
            escalated=False,
        )
        db.commit()
        return [reply.text]

    if should_escalate_before_llm(cleaned_incoming, runtime_config):
        reason = "agent inactive" if not runtime_config.is_active else "keyword trigger"
        return await _execute_escalation_handoff(
            db,
            lead,
            phone,
            runtime_config,
            cleaned_incoming,
            reason=reason,
            ai_confidence=None,
        )

    booking_reply = handle_post_intake_booking_message(db, lead, cleaned_incoming)
    if booking_reply:
        if getattr(booking_reply, "suppress_outbound", False):
            db.commit()
            return []
        await persist_and_send_intake_reply(db, lead, phone, booking_reply)
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        _audit_ai_turn(
            db,
            lead=lead,
            runtime_config=runtime_config,
            student_message=cleaned_incoming,
            ai_reply=booking_reply.text,
            confidence_score=getattr(booking_reply, "confidence", 1.0),
            escalated=False,
        )
        db.commit()
        return [booking_reply.text]

    if is_intake_complete(lead) and lead.consultation_scheduled_at:
        db.commit()
        return []

    from app.config import settings

    if settings.NEXUS_APPOINTMENTS_ONLY:
        from app.services.intake_templates import render_appointment_only_reply

        appointment_reply = IntakeReply(
            text=render_appointment_only_reply(lead, cleaned_incoming),
            confidence=1.0,
        )
        await persist_and_send_intake_reply(db, lead, phone, appointment_reply)
        lead.stage = LeadStage.AI_ACTIVE
        lead.is_human_locked = False
        _audit_ai_turn(
            db,
            lead=lead,
            runtime_config=runtime_config,
            student_message=cleaned_incoming,
            ai_reply=appointment_reply.text,
            confidence_score=1.0,
            escalated=False,
        )
        db.commit()
        return [appointment_reply.text]

    llm_result = await generate_ai_reply(db, lead, runtime_config, cleaned_incoming)
    if not llm_result.text.strip():
        return await _execute_escalation_handoff(
            db,
            lead,
            phone,
            runtime_config,
            cleaned_incoming,
            reason="AI could not generate a reliable answer",
            ai_confidence=llm_result.confidence if llm_result.confidence is not None else 0.0,
        )

    await persist_and_send_ai_message(
        db,
        lead,
        phone,
        llm_result.text,
        ai_confidence=llm_result.confidence,
    )
    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    _audit_ai_turn(
        db,
        lead=lead,
        runtime_config=runtime_config,
        student_message=cleaned_incoming,
        ai_reply=llm_result.text,
        confidence_score=llm_result.confidence,
        escalated=False,
    )
    db.commit()
    return [llm_result.text]


async def initiate_ai_outreach(
    db: Session,
    lead: Lead,
    *,
    force_restart: bool = False,
) -> list[str]:
    phone = clean_phone_number(lead.phone_number or "")
    if not phone:
        raise ValueError("Lead does not have a phone number for WhatsApp outreach.")

    assert_ai_outreach_allowed(db, lead, force_restart=force_restart)

    if get_active_provider() == PROVIDER_WHATSAPP:
        assert_whatsapp_business_outreach_allowed(db, lead.id)

    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    begin_whatsapp_intake_session(db, lead, force_full_restart=True)

    sent_messages: list[str] = []
    followup_delay = float(
        settings.WHATSAPP_OUTREACH_FOLLOWUP_DELAY_SECONDS
        or OUTREACH_TEMPLATE_FOLLOWUP_DELAY_SECONDS
    )

    if get_active_provider() == PROVIDER_WHATSAPP and outreach_template_is_configured():
        template_send = await send_whatsapp_outreach_template(
            phone,
            lead=lead,
            raise_on_failure=True,
        )
        if template_send is None:
            raise WhatsAppDeliveryError(
                "WhatsApp outreach template was not sent. Check WHATSAPP_OUTREACH_TEMPLATE and Meta approval."
            )
        await persist_advisor_message(db, lead, template_send.display_text)
        sent_messages.append(template_send.display_text)

        delivery_confirmed = await wait_for_whatsapp_template_delivered(
            template_send.message_id,
            timeout_seconds=float(settings.WHATSAPP_OUTREACH_DELIVERY_WAIT_SECONDS or 15.0),
        )
        post_template_confirmed = float(
            settings.WHATSAPP_OUTREACH_POST_TEMPLATE_DELAY_SECONDS
            or OUTREACH_POST_TEMPLATE_CONFIRMED_DELAY_SECONDS
        )
        post_template_unconfirmed = float(
            settings.WHATSAPP_OUTREACH_UNCONFIRMED_TEMPLATE_DELAY_SECONDS
            or OUTREACH_POST_TEMPLATE_UNCONFIRMED_DELAY_SECONDS
        )
        post_template_delay = post_template_confirmed if delivery_confirmed else max(
            followup_delay, post_template_unconfirmed
        )
        if delivery_confirmed:
            logger.info(
                "Template delivery confirmed for %s; waiting %.1fs before session follow-up",
                template_send.message_id,
                post_template_delay,
            )
        else:
            logger.warning(
                "Template delivery webhook not received for %s; waiting %.1fs before follow-up",
                template_send.message_id,
                post_template_delay,
            )
        await asyncio.sleep(post_template_delay)

    followup_text = render_outreach_intake_followup()
    followup_delivery_wait = float(
        settings.WHATSAPP_OUTREACH_FOLLOWUP_DELIVERY_WAIT_SECONDS or 20.0
    )
    if get_active_provider() == PROVIDER_WHATSAPP:
        try:
            await _send_outreach_session_followup(
                phone,
                followup_text,
                retry_delay=followup_delay,
                delivery_wait_seconds=followup_delivery_wait,
            )
        except WhatsAppDeliveryError as exc:
            detail = str(exc).lower()
            if "24-hour" in detail or "131047" in detail or "customer care window" in detail:
                logger.warning(
                    "Follow-up rejected outside customer care window; retrying after %.1fs: %s",
                    followup_delay,
                    exc,
                )
                await asyncio.sleep(followup_delay)
                await _send_outreach_session_followup(
                    phone,
                    followup_text,
                    retry_delay=followup_delay,
                    delivery_wait_seconds=followup_delivery_wait,
                )
            else:
                raise
        await persist_advisor_message(db, lead, followup_text, ai_confidence=1.0)
    else:
        followup = IntakeReply(text=followup_text, confidence=1.0)
        await persist_and_send_intake_reply(db, lead, phone, followup)
    sent_messages.append(followup_text)

    from app.services.student_status_service import ensure_lead_new_status, on_whatsapp_outreach

    ensure_lead_new_status(db, lead, source="AI outreach")
    on_whatsapp_outreach(db, lead, source="AI outreach")
    db.refresh(lead)
    return sent_messages
