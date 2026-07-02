from __future__ import annotations

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lead import Lead
from app.models.message import Message
from app.models.message_history import MessageHistory
from app.models.processed_message import ProcessedMessage
from app.services.messaging import dispatch_inbound_whatsapp_ai
from app.services.lead_conversation import ensure_handoff_for_inbound, is_human_handoff_lead
from app.services.whatsapp_helpers import extract_inbound_messages, get_or_create_lead_for_phone
from app.services.whatsapp_webhook_env import (
    extract_webhook_phone_number_id,
    should_process_inbound_phone_number_id,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _run_inbound_whatsapp_ai(
    sender_phone: str,
    message_text: str,
    wa_id: str,
    lead_id: int,
) -> None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            logger.warning("Inbound WhatsApp AI skipped: lead %s not found", lead_id)
            return
        db.refresh(lead)
        await dispatch_inbound_whatsapp_ai(db, lead, sender_phone or wa_id, message_text)
    except Exception:
        logger.exception(
            "Inbound WhatsApp AI failed for lead %s (phone=%s)",
            lead_id,
            sender_phone or wa_id,
        )
    finally:
        db.close()


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if hub_mode == "subscribe" and hub_verify_token == expected_token and hub_challenge:
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="WhatsApp webhook verification failed.")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception:
        logger.exception("Invalid WhatsApp webhook payload.")
        return {"status": "ignored", "reason": "invalid_json"}

    inbound_phone_id = extract_webhook_phone_number_id(payload)
    if not should_process_inbound_phone_number_id(inbound_phone_id):
        return {"status": "ignored", "reason": "foreign_phone_number_id"}

    inbound_messages = extract_inbound_messages(payload)
    if not inbound_messages:
        from app.services.whatsapp_outreach_delivery import process_whatsapp_status_webhook

        status_count = process_whatsapp_status_webhook(payload)
        if status_count:
            return {"status": "ok", "processed_statuses": status_count}
        return {"status": "ignored", "reason": "no_messages"}

    processed_count = 0

    for inbound in inbound_messages:
        try:
            already_processed = (
                db.query(ProcessedMessage)
                .filter(ProcessedMessage.message_id == inbound.message_id)
                .first()
            )
            if already_processed:
                logger.info("Duplicate WhatsApp message ignored: %s", inbound.message_id)
                continue

            lead = get_or_create_lead_for_phone(
                db,
                sender_phone=inbound.sender_phone,
                wa_id=inbound.wa_id,
            )

            if is_human_handoff_lead(lead):
                ensure_handoff_for_inbound(db, lead)

            db.add(
                MessageHistory(
                    lead_id=lead.id,
                    wa_id=inbound.wa_id,
                    sender_phone=inbound.sender_phone,
                    role="user",
                    message_text=inbound.message_text,
                    wa_message_id=inbound.message_id,
                )
            )
            db.add(
                Message(
                    lead_id=lead.id,
                    sender="candidate",
                    text=inbound.message_text,
                    is_read=False,
                )
            )
            db.add(ProcessedMessage(message_id=inbound.message_id))
            db.commit()

            background_tasks.add_task(
                _run_inbound_whatsapp_ai,
                inbound.sender_phone,
                inbound.message_text,
                inbound.wa_id,
                lead.id,
            )
            processed_count += 1
        except IntegrityError:
            db.rollback()
            logger.info("Duplicate WhatsApp message ignored via unique constraint: %s", inbound.message_id)
        except Exception:
            logger.exception(
                "Failed to persist inbound WhatsApp message %s",
                inbound.message_id,
            )
            db.rollback()

    return {"status": "ok", "processed": processed_count}
