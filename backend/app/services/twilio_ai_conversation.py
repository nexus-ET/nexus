from __future__ import annotations

import asyncio
from app.utils.timezone import utc_now
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
    is_post_intake_management_command,
    process_flow_completion,
    process_intake_message,
    _repair_intake_if_booking_already_active,
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
from app.config import settings
from app.services.messaging import (
    PROVIDER_WHATSAPP,
    WhatsAppDeliveryError,
    assert_whatsapp_business_outreach_allowed,
    get_active_provider,
    outreach_followup_template_is_configured,
    outreach_template_is_configured,
    record_ai_conversation_audit,
    send_message,
    send_whatsapp_outreach_followup_template,
    send_whatsapp_outreach_template,
    send_whatsapp_text_message,
    template_body_includes_continue_prompt,
)
from app.services.whatsapp_outreach_delivery import (
    wait_for_outbound_delivery_outcome,
)

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20


async def _send_outreach_session_followup(
    phone: str,
    text: str,
    *,
    context_message_id: str | None = None,
    retry_delay: float,
    delivery_wait_seconds: float,
    max_attempts: int = 3,
) -> str:
    """
    Send the post-template continue nudge as session text (fallback path).

    Returns the wamid when Meta accepts the message. Retries only when Meta
    reports failed — never resend after a successful accept (avoids duplicates).
    """
    last_error: WhatsAppDeliveryError | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.info(
                "Retrying outreach session follow-up (attempt %s/%s)",
                attempt,
                max_attempts,
            )
            await asyncio.sleep(retry_delay)

        message_id = await send_whatsapp_text_message(
            phone,
            text,
            context_message_id=context_message_id,
        )
        outcome = await wait_for_outbound_delivery_outcome(
            message_id,
            timeout_seconds=delivery_wait_seconds,
        )
        logger.info(
            "Outreach session follow-up message_id=%s outcome=%s attempt=%s context=%s",
            message_id,
            outcome,
            attempt,
            bool(context_message_id),
        )

        # Meta accepted the send — do not resend (duplicate risk).
        if outcome in {"delivered", "read", "sent"}:
            return message_id

        if outcome == "failed":
            last_error = WhatsAppDeliveryError(
                f"WhatsApp reported follow-up delivery failed (message_id={message_id})."
            )
            continue

        last_error = WhatsAppDeliveryError(
            f"WhatsApp follow-up delivery not confirmed (message_id={message_id}, outcome={outcome})."
        )
        # Unknown outcome after accept is still treated as sent once — stop retrying.
        return message_id

    if last_error is not None:
        raise last_error
    raise WhatsAppDeliveryError("WhatsApp follow-up could not be delivered.")


async def _deliver_outreach_followup(
    phone: str,
    followup_text: str,
    *,
    lead: Lead,
    template_context_wamid: str | None,
    retry_delay: float,
    delivery_wait_seconds: float,
) -> str:
    """Send continue follow-up via template (preferred) or session text (fallback)."""
    if settings.WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP:
        logger.info(
            "Skipping WhatsApp follow-up send (WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP); "
            "only the welcome template will be delivered."
        )
        return template_context_wamid or ""

    if outreach_followup_template_is_configured():
        last_error: WhatsAppDeliveryError | None = None
        for attempt in range(1, 4):
            if attempt > 1:
                logger.info(
                    "Retrying outreach follow-up template (attempt %s/3)",
                    attempt,
                )
                await asyncio.sleep(retry_delay)

            template_send = await send_whatsapp_outreach_followup_template(
                phone,
                lead=lead,
                raise_on_failure=True,
            )
            outcome = await wait_for_outbound_delivery_outcome(
                template_send.message_id,
                timeout_seconds=max(delivery_wait_seconds, 25.0),
            )
            logger.info(
                "Outreach follow-up template message_id=%s outcome=%s attempt=%s",
                template_send.message_id,
                outcome,
                attempt,
            )
            # Accepted by Meta — never resend the same follow-up (duplicate on WhatsApp + AI Active).
            if outcome in {"delivered", "read", "sent"}:
                return template_send.message_id
            if outcome == "failed":
                last_error = WhatsAppDeliveryError(
                    f"WhatsApp follow-up template delivery failed (message_id={template_send.message_id})."
                )
                continue
            last_error = WhatsAppDeliveryError(
                f"WhatsApp follow-up template not confirmed (message_id={template_send.message_id}, "
                f"outcome={outcome})."
            )
            return template_send.message_id

        if last_error is not None:
            raise last_error
        raise WhatsAppDeliveryError("WhatsApp follow-up template could not be delivered.")

    if settings.WHATSAPP_OUTREACH_REQUIRE_FOLLOWUP_TEMPLATE:
        raise WhatsAppDeliveryError(
            "WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE is required on this environment. "
            "Session text after a template often does not reach the device. "
            "Create Utility template et_intake_continue in Meta Business Manager and set "
            "WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE in .env, or set "
            "WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP=true if you want only the welcome "
            "template (no follow-up nudge)."
        )

    return await _send_outreach_session_followup(
        phone,
        followup_text,
        context_message_id=template_context_wamid,
        retry_delay=retry_delay,
        delivery_wait_seconds=delivery_wait_seconds,
    )


def lead_has_prior_ai_outreach(db: Session, lead_id: int) -> bool:
    """True when the AI agent has already sent at least one WhatsApp message."""
    return (
        db.query(Message.id)
        .filter(Message.lead_id == lead_id, Message.sender == "advisor")
        .first()
        is not None
    )


def _lead_already_has_continue_prompt(db: Session, lead_id: int) -> bool:
    """True when an advisor message already contains the hi/hello continue nudge."""
    rows = (
        db.query(Message.text)
        .filter(Message.lead_id == lead_id, Message.sender == "advisor")
        .order_by(Message.created_at.desc())
        .limit(8)
        .all()
    )
    return any(template_body_includes_continue_prompt(text or "") for (text,) in rows)


def assert_ai_outreach_allowed(db: Session, lead: Lead, *, force_restart: bool = False) -> None:
    from app.services.student_status_service import is_lead_communication_opted_out

    if is_lead_communication_opted_out(db, lead):
        raise ValueError(
            "This candidate has opted out of communication. Outreach and marketing are disabled."
        )
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

    from app.services.student_status_service import is_lead_communication_opted_out

    if is_lead_communication_opted_out(db, lead):
        db.commit()
        return []

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

    # Heal drift: active counselling booking but intake still on PICK_* .
    _repair_intake_if_booking_already_active(db, lead)
    db.refresh(lead)

    if is_post_intake_management_command(cleaned_incoming):
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


async def _record_whatsapp_outreach_status(db: Session, lead: Lead) -> None:
    """Persist Lead: New baseline then Lead: Outreach as soon as outreach is queued."""
    from app.services.student_status_service import ensure_lead_new_status, on_whatsapp_outreach

    ensure_lead_new_status(db, lead, source="AI outreach")
    on_whatsapp_outreach(db, lead, source="AI outreach")
    db.refresh(lead)


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
    outreach_status_recorded = False

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
        await _record_whatsapp_outreach_status(db, lead)
        outreach_status_recorded = True
        logger.info(
            "Outreach welcome template %s sent (message_id=%s); "
            "no continue-prompt follow-up — intake starts when the student messages",
            template_send.template_name,
            template_send.message_id,
        )
    elif get_active_provider() == PROVIDER_WHATSAPP:
        raise WhatsAppDeliveryError(
            "WHATSAPP_OUTREACH_TEMPLATE is not configured. "
            "Set an approved welcome template name in .env. "
            "Students reply hi/hello to start intake questions (no separate continue nudge is sent)."
        )
    else:
        # Non-WhatsApp providers: welcome via a short opener only (no continue nudge).
        opener = IntakeReply(
            text=(
                "Hi! Thanks for connecting with Edutrust. "
                "Reply *hi* when you're ready and we'll continue with a few quick questions."
            ),
            confidence=1.0,
        )
        await persist_and_send_intake_reply(db, lead, phone, opener)
        sent_messages.append(opener.text)

    if not outreach_status_recorded:
        await _record_whatsapp_outreach_status(db, lead)

    db.refresh(lead)
    return sent_messages


def _delete_lead_booking_details(db: Session, lead: Lead) -> tuple[int, list[dict]]:
    """Release consultation slots and permanently remove counselling bookings for a lead."""
    from app.models.consultation_slot import ConsultationSlot
    from app.models.counselling_booking import CounsellingBooking
    from app.services.counselling_service import SCHEDULED_STATUS

    for slot in db.query(ConsultationSlot).filter(ConsultationSlot.lead_id == lead.id).all():
        slot.lead_id = None

    bookings = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.lead_id == lead.id)
        .all()
    )
    alert_snapshots: list[dict] = []
    for booking in bookings:
        if booking.admin_id and booking.status == SCHEDULED_STATUS:
            alert_snapshots.append(
                {
                    "admin_id": booking.admin_id,
                    "candidate_name": booking.candidate_name,
                    "scheduled_time": booking.scheduled_time,
                    "booking_id": booking.id,
                    "lead_id": booking.lead_id,
                    "alert_reason": "reset",
                }
            )

    deleted_bookings = (
        db.query(CounsellingBooking)
        .filter(CounsellingBooking.lead_id == lead.id)
        .delete(synchronize_session=False)
    )
    return int(deleted_bookings or 0), alert_snapshots


def _wipe_lead_intake_profile(lead: Lead) -> None:
    """Clear every chat-collected intake / booking profile field on the lead."""
    from app.services.admissions_intake_flow import INTAKE_STEP_TARGET_DEGREE
    from app.services.lead_study_interest import clear_study_interest_sources

    lead.stage = LeadStage.AI_ACTIVE
    lead.is_human_locked = False
    lead.admission_stage = None
    lead.admission_stage_entered_at = None
    lead.current_location = None
    lead.preferred_country = None
    lead.budget_tier = None
    lead.test_scores = None
    lead.academic_summary = None
    lead.english_test_scores = None
    lead.gre_score = None
    lead.gmat_score = None
    lead.wants_consultation_call = None
    lead.consultation_scheduled_at = None
    lead.calendar_booking_id = None
    lead.intake_context = None
    lead.intake_step = INTAKE_STEP_TARGET_DEGREE
    clear_study_interest_sources(lead)


def reset_whatsapp_conversation(db: Session, lead: Lead) -> dict:
    """Clear WhatsApp chat history, bookings, and intake session so outreach can start fresh."""
    from datetime import datetime

    from sqlalchemy import inspect as sa_inspect

    from app.models.message_history import MessageHistory
    from app.services.counselling_service import dispatch_admin_booking_release_alerts
    from app.services.status_definition_service import (
        STAGE_LEAD_NEW,
        STATUS_LEAD_NEW,
        resolve_status_id_by_name,
    )
    from app.services.student_status_service import update_student_status

    # Status helpers refresh the ORM row (Session autoflush is False), so they must
    # run before we wipe intake fields — otherwise refresh restores the old answers.
    new_status_id = (
        resolve_status_id_by_name(db, STAGE_LEAD_NEW, fallback=STATUS_LEAD_NEW)
        or STATUS_LEAD_NEW
    )
    status_result = update_student_status(
        db,
        student_id=lead.id,
        status_id=new_status_id,
        changed_by_type="system",
        comments="WhatsApp conversation reset — pipeline returned to Lead: New.",
        allow_override=True,
        transition_type="backward",
        commit=False,
    )
    if status_result.get("blocked") or (
        not status_result.get("changed") and not status_result.get("skipped")
    ):
        lead.status_definition_id = new_status_id
        lead.status_entered_at = utc_now()

    deleted_bookings, alert_snapshots = _delete_lead_booking_details(db, lead)

    deleted_messages = (
        db.query(Message)
        .filter(Message.lead_id == lead.id)
        .delete(synchronize_session=False)
    )

    deleted_history = 0
    try:
        bind = db.get_bind()
        if sa_inspect(bind).has_table(MessageHistory.__tablename__):
            deleted_history = (
                db.query(MessageHistory)
                .filter(MessageHistory.lead_id == lead.id)
                .delete(synchronize_session=False)
            )
    except Exception:
        logger.exception(
            "Unable to clear message_history for lead_id=%s; continuing with messages reset",
            lead.id,
        )

    # Re-load the same row after status refresh, then wipe profile last.
    lead = db.query(Lead).filter(Lead.id == lead.id).first() or lead
    _wipe_lead_intake_profile(lead)
    touch_lead_activity(db, lead)
    db.flush()
    db.commit()
    db.refresh(lead)
    dispatch_admin_booking_release_alerts(alert_snapshots)

    logger.info(
        "Reset WhatsApp conversation for lead_id=%s (messages=%s history=%s bookings=%s "
        "country=%s wants_call=%s scheduled=%s)",
        lead.id,
        deleted_messages,
        deleted_history,
        deleted_bookings,
        lead.preferred_country,
        lead.wants_consultation_call,
        lead.consultation_scheduled_at,
    )
    return {
        "deleted_messages": int(deleted_messages or 0),
        "deleted_history": int(deleted_history or 0),
        "deleted_bookings": int(deleted_bookings or 0),
    }
