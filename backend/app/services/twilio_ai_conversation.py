from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.services.admissions_intake_flow import (
    BRAND_NAME,
    IntakeReply,
    begin_whatsapp_intake_session,
    get_current_step_reply,
    handle_post_intake_booking_message,
    is_intake_complete,
    process_flow_completion,
    process_intake_message,
)
from app.services.agent_runtime import (
    RuntimeAgentConfig,
    get_runtime_agent_config,
    should_escalate_before_llm,
)
from app.services.ai_service import LlmResult, compose_agent_message, compose_handoff_acknowledgement
from app.services.handoff_notifications import notify_advisors_of_handoff
from app.services.lead_conversation import ensure_handoff_for_inbound, touch_lead_activity
from app.services.phone_utils import clean_phone_number
from app.services.messaging import (
    PROVIDER_WHATSAPP,
    WhatsAppDeliveryError,
    get_active_provider,
    open_whatsapp_conversation_window,
    record_ai_conversation_audit,
    send_message,
)

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20
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

    if target_phone:
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

    if not is_intake_complete(lead):
        reply = await process_intake_message(db, lead, cleaned_incoming, runtime_config)
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

    booking_reply = handle_post_intake_booking_message(db, lead, cleaned_incoming)
    if booking_reply:
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


async def initiate_ai_outreach(db: Session, lead: Lead) -> list[str]:
    phone = clean_phone_number(lead.phone_number or "")
    if not phone:
        raise ValueError("Lead does not have a phone number for WhatsApp outreach.")

    runtime_config = get_runtime_agent_config(db)
    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False

    if is_intake_complete(lead) or not getattr(lead, "intake_step", None):
        begin_whatsapp_intake_session(db, lead, force_full_restart=True)
    elif lead_has_ai_outbound_messages(db, lead.id):
        reply = await get_current_step_reply(db, lead, runtime_config)
        await open_whatsapp_conversation_window(phone, raise_on_failure=True)
        await persist_and_send_intake_reply(db, lead, phone, reply)
        return [reply.text]

    begin_whatsapp_intake_session(db, lead, force_full_restart=True)
    reply = await get_current_step_reply(db, lead, runtime_config)
    await open_whatsapp_conversation_window(phone, raise_on_failure=True)
    await persist_and_send_intake_reply(db, lead, phone, reply)
    return [reply.text]
