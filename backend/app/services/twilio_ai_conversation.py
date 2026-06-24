from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.services.admissions_intake_flow import (
    IntakeReply,
    get_current_step_reply,
    handle_post_intake_booking_message,
    is_intake_complete,
    process_flow_completion,
    process_intake_message,
    start_intake_message,
)
from app.services.agent_runtime import get_runtime_agent_config, should_escalate_message
from app.services.ai_service import _call_llm
from app.services.lead_conversation import ensure_handoff_for_inbound, touch_lead_activity
from app.services.phone_utils import clean_phone_number
from app.services.messaging import (
    PROVIDER_WHATSAPP,
    WhatsAppDeliveryError,
    get_active_provider,
    open_whatsapp_conversation_window,
    send_message,
)

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20


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


def load_conversation_history(db: Session, lead_id: int) -> list[tuple[str, str]]:
    rows = (
        db.query(Message)
        .filter(Message.lead_id == lead_id)
        .order_by(Message.created_at.asc())
        .limit(RECENT_HISTORY_LIMIT)
        .all()
    )

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


def build_llm_messages(system_prompt: str, history: list[tuple[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for role, text in history:
        messages.append({"role": role, "content": text})
    return messages


async def generate_ai_reply(db: Session, lead: Lead) -> str:
    runtime_config = get_runtime_agent_config(db)
    history = load_conversation_history(db, lead.id)
    student_name = first_name_from_lead(lead)
    has_prior_ai_turns = any(role == "assistant" for role, _ in history)

    booking_note = ""
    if lead.consultation_scheduled_at:
        booking_note = (
            f"Consultation booked at: {lead.consultation_scheduled_at.isoformat()}. "
            "If they ask to change it, tell them to reply *change slot* or *reschedule*."
        )

    enriched_prompt = (
        f"{runtime_config.system_prompt}\n\n"
        f"Student name: {lead.full_name or student_name}.\n"
        f"Location: {getattr(lead, 'current_location', None) or 'unknown'}.\n"
        f"Target country: {lead.preferred_country or 'unknown'}.\n"
        f"Test scores: {lead.test_scores or 'unknown'}.\n"
        f"{booking_note}\n"
        "Intake is complete. Continue helping on WhatsApp with concise, helpful admissions guidance."
    )

    llm_messages = build_llm_messages(enriched_prompt, history)
    return await _call_llm(
        runtime_config.ai_model,
        llm_messages,
        student_name=student_name,
        has_prior_ai_turns=has_prior_ai_turns,
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
            body = reply.text or "Please reply to continue."
            await _deliver_whatsapp_text(target_phone, body)
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
) -> Message:
    outbound = Message(
        lead_id=lead.id,
        sender="advisor",
        text=message_body,
        is_read=True,
    )
    db.add(outbound)
    touch_lead_activity(db, lead)
    db.commit()
    db.refresh(outbound)

    target_phone = clean_phone_number(phone or lead.phone_number or "")
    if target_phone:
        await _deliver_whatsapp_text(target_phone, message_body)
    return outbound


async def handle_ai_active_inbound(
    db: Session,
    lead: Lead,
    incoming_text: str,
    phone: str,
    flow_data: str | None = None,
) -> list[str]:
    runtime_config = get_runtime_agent_config(db)

    if flow_data:
        flow_reply = process_flow_completion(db, lead, flow_data)
        if flow_reply:
            await persist_and_send_intake_reply(db, lead, phone, flow_reply)
            return [flow_reply.text]

    if should_escalate_message(incoming_text, runtime_config, lead.ml_conversion_score or 0.0):
        ensure_handoff_for_inbound(db, lead)
        escalation = (
            f"Understood, {first_name_from_lead(lead)}. 🤝 I'm connecting you with a human "
            "admissions advisor now. They'll continue on this WhatsApp thread shortly."
        )
        await persist_and_send_ai_message(db, lead, phone, escalation)
        return [escalation]

    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False

    if not is_intake_complete(lead):
        reply = process_intake_message(db, lead, incoming_text)
        await persist_and_send_intake_reply(db, lead, phone, reply)
        return [reply.text]

    booking_reply = handle_post_intake_booking_message(db, lead, incoming_text)
    if booking_reply:
        await persist_and_send_intake_reply(db, lead, phone, booking_reply)
        return [booking_reply.text]

    ai_response = await generate_ai_reply(db, lead)
    await persist_and_send_ai_message(db, lead, phone, ai_response)
    return [ai_response]


async def initiate_ai_outreach(db: Session, lead: Lead) -> list[str]:
    phone = clean_phone_number(lead.phone_number or "")
    if not phone:
        raise ValueError("Lead does not have a phone number for WhatsApp outreach.")

    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False

    has_prior_outbound = lead_has_ai_outbound_messages(db, lead.id)

    if is_intake_complete(lead):
        if has_prior_outbound:
            outreach_text = await generate_ai_reply(db, lead)
        else:
            name = first_name_from_lead(lead)
            outreach_text = (
                f"Hi {name}! 👋 This is the Nexus Admissions AI Assistant on WhatsApp.\n\n"
                "How can I help you with your study abroad plans today?"
            )
    elif has_prior_outbound:
        if not getattr(lead, "intake_step", None):
            lead.intake_step = "FULL_NAME"
        reply = get_current_step_reply(db, lead)
        await open_whatsapp_conversation_window(phone)
        await persist_and_send_intake_reply(db, lead, phone, reply)
        return [reply.text]
    else:
        if not getattr(lead, "intake_step", None):
            lead.intake_step = "FULL_NAME"
        outreach_text = start_intake_message()

    await open_whatsapp_conversation_window(phone)
    await persist_and_send_ai_message(db, lead, phone, outreach_text)
    return [outreach_text]
