import os
import traceback
import mimetypes
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import cast, String, or_, func
from sqlalchemy.orm import Session, joinedload

# 🔗 CRITICAL TWILIO IMPORTS
from twilio.twiml.messaging_response import MessagingResponse  

# 🎯 MODULE DATABASE PATH PATCH
from app.db.database import get_db
from app.models.lead import Lead, LeadChannel, LeadStage
from app.models.message import Message
from app.services.lead_conversation import (
    ensure_handoff_for_inbound,
    find_lead_for_inbound_whatsapp,
    touch_lead_activity,
)
from app.services.phone_utils import (
    build_inbound_whatsapp_lead_name,
    clean_phone_number,
    extract_inbound_whatsapp_text,
    find_lead_by_phone,
)
from app.services.admissions_intake_flow import build_intake_profile_summary, is_booking_management_message
from app.services.prospects_service import get_prospects_summary, list_prospects_keyset, resolve_platform_badge
from app.services.messaging import WhatsAppDeliveryError
from app.services.twilio_ai_conversation import handle_ai_active_inbound, initiate_ai_outreach
from app.services.twilio_outbound import dispatch_live_whatsapp_message

router = APIRouter()
logger = logging.getLogger(__name__)

# Schema for incoming PATCH requests
class StatusUpdate(BaseModel):
    status: str


class LeadNotesUpdate(BaseModel):
    notes: str = Field(..., max_length=10000)

# Global directory where your workspace panel saves files
UPLOAD_DIRECTORY = "uploads" 
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True) 

# ---------------------------------------------------------
# 🛠️ NEW PATCH ROUTE TO FIX 404
# ---------------------------------------------------------
@router.get("/queue")
@router.get("/queue/")
@router.get("/handoffs")
@router.get("/handoffs/")
@router.get("/handoff")
@router.get("/handoff/")
async def get_handoff_queue(db: Session = Depends(get_db)):
    """
    Fetches leads flagged as HANDOFF or manually locked by a human.
    """
    try:
        handoff_list = (
            db.query(Lead)
            .filter(
                or_(
                    cast(Lead.stage, String).ilike("%HANDOFF%"),
                    cast(Lead.stage, String).ilike("%HUMAN%"),
                    Lead.is_human_locked == True,
                )
            )
            .order_by(Lead.updated_at.desc())
            .all()
        )
        stats_by_id = _load_message_stats_for_leads(db, [lead.id for lead in handoff_list])
        return [
            build_handoff_queue_item(lead, stats_by_id.get(lead.id, {}))
            for lead in handoff_list
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_dynamic_env_tunnel_base() -> str:
    """ Scan runtime directories, safely load environment states, and extract the host tunnel base. """
    current_dir = Path(__file__).resolve().parent
    env_path = None
    
    for parent in [current_dir] + list(current_dir.parents):
        target_env = parent / ".env"
        if target_env.exists():
            env_path = target_env
            break

    if env_path:
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
        
    return os.getenv("PUBLIC_TUNNEL_BASE", "").rstrip("/")


def normalize_lead_stage(stage) -> str:
    if stage is None:
        return "AI_ACTIVE"
    if hasattr(stage, "value"):
        return str(stage.value).upper().replace("-", "_")
    raw = str(stage).upper().replace("-", "_")
    if raw.startswith("LEADSTAGE."):
        return raw.split(".", 1)[1]
    return raw


def build_universal_lead_payload(lead: Lead, db: Session) -> dict:
    all_msgs = (
        db.query(Message)
        .filter(Message.lead_id == lead.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    
    unread_count = sum(1 for m in all_msgs if m.sender in ["student", "candidate"] and not m.is_read)
    total_received = sum(1 for m in all_msgs if m.sender in ["student", "candidate"])

    latest_msg = all_msgs[-1] if all_msgs else None
    
    fallback_text = "No messages exchanged yet."
    if latest_msg:
        fallback_text = latest_msg.text
    elif hasattr(lead, 'last_message') and lead.last_message:
        fallback_text = lead.last_message

    raw_stage = lead.stage or LeadStage.AI_ACTIVE
    clean_stage = normalize_lead_stage(raw_stage)

    base_time = lead.created_at.isoformat() if lead.created_at else datetime.utcnow().isoformat()
    updated_time = lead.updated_at.isoformat() if hasattr(lead, 'updated_at') and lead.updated_at else base_time

    def serialize_sender(sender: str) -> str:
        if sender in ["student", "candidate"]:
            return "candidate"
        if sender == "system":
            return "system"
        return "advisor"

    serialized_messages = [
        {
            "id": m.id,
            "sender": serialize_sender(m.sender),
            "senderName": (
                "Candidate"
                if m.sender in ["student", "candidate"]
                else "System" if m.sender == "system" else "Advisor"
            ),
            "text": m.text or "",
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat() if m.created_at else base_time,
            "media_url": getattr(m, 'media_url', None),
            "file_name": getattr(m, 'file_name', None) 
        } for m in all_msgs
    ]

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone": lead.phone_number,
        "stage": clean_stage,
        "status": clean_stage,
        "current_stage": clean_stage,
        "stage_lowercase": clean_stage.lower(), 
        "status_lowercase": clean_stage.lower(),
        "is_human_locked": getattr(lead, 'is_human_locked', False),
        "human_locked": getattr(lead, 'is_human_locked', False),
        "last_message": fallback_text,
        "last_message_text": fallback_text,
        "latest_message": fallback_text,
        "unread_count": unread_count,
        "total_messages_received": total_received,
        "latest_interaction_time": latest_msg.created_at.isoformat() if latest_msg and latest_msg.created_at else base_time,
        "updated_at": updated_time,
        "created_at": base_time,
        "academic_summary": getattr(lead, "academic_summary", None),
        "last_interaction_summary": getattr(lead, "academic_summary", None),
        "intake_context": getattr(lead, "intake_context", None),
        "source": getattr(lead, "source", None),
        "platform_badge": resolve_platform_badge(lead),
        "meta_campaign_name": getattr(lead, "meta_campaign_name", None),
        "meta_form_id": getattr(lead, "meta_form_id", None),
        "meta_ad_id": getattr(lead, "meta_ad_id", None),
        "additional_data": getattr(lead, "additional_data", None) or {},
        "messages": serialized_messages,
        "chat_history": serialized_messages,
        "history": serialized_messages,
        "logs": serialized_messages,
        **build_intake_profile_summary(lead, db),
    }


def _load_message_stats_for_leads(db: Session, lead_ids: list[int]) -> dict[int, dict]:
    if not lead_ids:
        return {}

    rows = (
        db.query(
            Message.lead_id,
            func.count()
            .filter(Message.sender.in_(["student", "candidate"]))
            .label("total_received"),
            func.count()
            .filter(
                Message.sender.in_(["student", "candidate"]),
                Message.is_read.is_(False),
            )
            .label("unread_count"),
            func.max(Message.created_at).label("latest_msg_at"),
            func.count()
            .filter(Message.sender.in_(["advisor", "system"]))
            .label("ai_msg_count"),
        )
        .filter(Message.lead_id.in_(lead_ids))
        .group_by(Message.lead_id)
        .all()
    )

    return {
        row.lead_id: {
            "total_messages_received": int(row.total_received or 0),
            "unread_count": int(row.unread_count or 0),
            "latest_interaction_time": (
                row.latest_msg_at.isoformat() if row.latest_msg_at else None
            ),
            "has_ai_messages": int(row.ai_msg_count or 0) > 0,
        }
        for row in rows
    }


def build_active_queue_item(lead: Lead, stats: dict | None = None) -> dict:
    """Lightweight AI Active list payload without full message history."""
    stats = stats or {}
    raw_stage = lead.stage or LeadStage.AI_ACTIVE
    clean_stage = normalize_lead_stage(raw_stage)
    base_time = lead.created_at.isoformat() if lead.created_at else datetime.utcnow().isoformat()
    updated_time = (
        lead.updated_at.isoformat()
        if hasattr(lead, "updated_at") and lead.updated_at
        else base_time
    )
    latest_time = stats.get("latest_interaction_time") or updated_time

    summary = getattr(lead, "academic_summary", None) or ""
    fallback_text = summary.split("\n")[0].strip() if summary else "No messages exchanged yet."
    if len(fallback_text) > 240:
        fallback_text = f"{fallback_text[:237]}..."

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone": lead.phone_number,
        "stage": clean_stage,
        "status": clean_stage,
        "current_stage": clean_stage,
        "unread_count": stats.get("unread_count", 0),
        "total_messages_received": stats.get("total_messages_received", 0),
        "has_ai_messages": stats.get("has_ai_messages", False),
        "latest_interaction_time": latest_time,
        "updated_at": updated_time,
        "created_at": base_time,
        "last_message": fallback_text,
        "messages": [],
        "intake_step": getattr(lead, "intake_step", None),
        "intake_complete": getattr(lead, "intake_step", None) == "COMPLETE",
    }


def build_handoff_queue_item(lead: Lead, stats: dict | None = None) -> dict:
    """Lightweight handoff queue payload without full message history."""
    stats = stats or {}
    raw_stage = lead.stage or LeadStage.HANDOFF
    clean_stage = normalize_lead_stage(raw_stage)
    base_time = lead.created_at.isoformat() if lead.created_at else datetime.utcnow().isoformat()
    updated_time = (
        lead.updated_at.isoformat()
        if hasattr(lead, "updated_at") and lead.updated_at
        else base_time
    )
    latest_time = stats.get("latest_interaction_time") or updated_time

    summary = getattr(lead, "academic_summary", None) or ""
    fallback_text = summary.split("\n")[0].strip() if summary else "No messages exchanged yet."
    if len(fallback_text) > 240:
        fallback_text = f"{fallback_text[:237]}..."

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone": lead.phone_number,
        "stage": clean_stage,
        "status": clean_stage,
        "current_stage": clean_stage,
        "is_human_locked": getattr(lead, "is_human_locked", False),
        "human_locked": getattr(lead, "is_human_locked", False),
        "unread_count": stats.get("unread_count", 0),
        "total_messages_received": stats.get("total_messages_received", 0),
        "latest_interaction_time": latest_time,
        "updated_at": updated_time,
        "created_at": base_time,
        "last_message": fallback_text,
        "academic_summary": summary or None,
        "last_interaction_summary": summary or None,
        "messages": [],
    }


def build_lead_list_payload(lead: Lead) -> dict:
    """Lightweight list payload for /leads/all without loading full message history."""
    raw_stage = lead.stage or LeadStage.AI_ACTIVE
    clean_stage = normalize_lead_stage(raw_stage)
    base_time = lead.created_at.isoformat() if lead.created_at else datetime.utcnow().isoformat()
    updated_time = (
        lead.updated_at.isoformat()
        if hasattr(lead, "updated_at") and lead.updated_at
        else base_time
    )
    summary = getattr(lead, "academic_summary", None) or ""
    fallback_text = summary.split("\n")[0].strip() if summary else "No messages exchanged yet."
    if len(fallback_text) > 240:
        fallback_text = f"{fallback_text[:237]}..."

    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "phone": lead.phone_number,
        "stage": clean_stage,
        "status": clean_stage,
        "current_stage": clean_stage,
        "stage_lowercase": clean_stage.lower(),
        "status_lowercase": clean_stage.lower(),
        "is_human_locked": getattr(lead, "is_human_locked", False),
        "human_locked": getattr(lead, "is_human_locked", False),
        "source": getattr(lead, "source", None),
        "meta_leadgen_id": getattr(lead, "meta_leadgen_id", None),
        "meta_campaign_name": getattr(lead, "meta_campaign_name", None),
        "last_message": fallback_text,
        "last_message_text": fallback_text,
        "latest_message": fallback_text,
        "unread_count": 0,
        "total_messages_received": 0,
        "latest_interaction_time": updated_time,
        "updated_at": updated_time,
        "created_at": base_time,
        "academic_summary": summary or None,
        "last_interaction_summary": summary or None,
        "messages": [],
        "chat_history": [],
        "history": [],
        "logs": [],
    }


@router.post("/webhook/whatsapp-reply")
@router.post("/webhook/whatsapp-reply/")
async def handle_inbound_whatsapp_reply(request: Request, db: Session = Depends(get_db)):
    try:
        form_data = await request.form()
        incoming_msg_raw = extract_inbound_whatsapp_text(form_data)
        flow_data_raw = form_data.get("FlowData") or form_data.get("flow_data")
        sender_phone_raw = form_data.get("From", "")
        whatsapp_profile_name = form_data.get("ProfileName") or form_data.get("WaId")
        sender_phone_clean = clean_phone_number(sender_phone_raw.replace("whatsapp:", "").strip())
        media_url_0 = form_data.get("MediaUrl0")
        media_type_0 = form_data.get("ContentType0", "")

        logger.info(
            "Twilio WhatsApp inbound: from=%s body_len=%s body=%r button=%r interactive=%s",
            sender_phone_clean,
            len(incoming_msg_raw),
            incoming_msg_raw[:120],
            form_data.get("ButtonPayload"),
            bool(form_data.get("InteractiveData")),
        )
        
        if not incoming_msg_raw and media_url_0:
            incoming_msg_raw = f"📁 Received Attachment ({media_type_0 or 'File Matrix Reference'})"

        if not incoming_msg_raw and not media_url_0 and not flow_data_raw:
            return Response(content="Empty body parsed", media_type="text/plain")

        lead = find_lead_for_inbound_whatsapp(db, sender_phone_clean)

        if not lead:
            lead = Lead(
                full_name=build_inbound_whatsapp_lead_name(
                    sender_phone_clean, whatsapp_profile_name
                ),
                email=f"{sender_phone_clean.lstrip('+')}@whatsapp.nexus",
                phone_number=sender_phone_clean,
                channel=LeadChannel.WHATSAPP,
                stage=LeadStage.AI_ACTIVE,
                is_human_locked=False,
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
        elif sender_phone_clean and lead.phone_number != sender_phone_clean:
            lead.phone_number = sender_phone_clean

        inbound_db_row = Message(
            lead_id=lead.id,
            sender="candidate",
            text=incoming_msg_raw if incoming_msg_raw else ("📁 Received Attachment" if media_url_0 else "[WhatsApp Flow submission]"),
            is_read=False,
            media_url=media_url_0,
        )
        db.add(inbound_db_row)
        touch_lead_activity(db, lead)
        db.commit()

        logger.info(
            "Saved inbound WhatsApp message lead_id=%s message_id=%s",
            lead.id,
            inbound_db_row.id,
        )

        db.refresh(lead)

        if (lead.is_human_locked or normalize_lead_stage(lead.stage) == "HANDOFF") and not (
            is_booking_management_message(incoming_msg_raw, lead, str(flow_data_raw) if flow_data_raw else None)
        ):
            ensure_handoff_for_inbound(db, lead)
            touch_lead_activity(db, lead)
            db.commit()
            twiml = MessagingResponse()
            return Response(content=str(twiml), media_type="application/xml")

        await handle_ai_active_inbound(
            db,
            lead,
            incoming_msg_raw,
            sender_phone_clean,
            flow_data=str(flow_data_raw) if flow_data_raw else None,
        )

        twiml = MessagingResponse()
        return Response(content=str(twiml), media_type="application/xml")
        
    except Exception as err:
        db.rollback()
        return Response(content=str(err), status_code=500)

@router.post("/{lead_id}/ai-outreach")
@router.post("/{lead_id}/ai-outreach/")
async def start_ai_whatsapp_outreach(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")

    if normalize_lead_stage(lead.stage) != "AI_ACTIVE":
        raise HTTPException(status_code=400, detail="Lead is not in AI Active status.")

    try:
        sent_messages = await initiate_ai_outreach(db, lead)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WhatsAppDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("AI outreach failed for lead_id=%s", lead_id)
        raise HTTPException(status_code=500, detail="Failed to start AI WhatsApp conversation.") from exc

    refreshed = db.query(Lead).filter(Lead.id == lead.id).first()
    return {
        "status": "success",
        "messages_sent": sent_messages,
        "lead": build_universal_lead_payload(refreshed, db),
    }

@router.post("/webhook/social-ingress")
@router.post("/webhook/social-ingress/")
async def handle_external_social_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        content_type = request.headers.get("content-type", "")
        attachment_asset = None
        phone = None
        msg_body = None
        debug_bypass_twilio = False
        lead_id_raw = None

        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form_data = await request.form()
            phone = form_data.get("phone") or form_data.get("phone_number")
            msg_body = form_data.get("message") or form_data.get("body")
            debug_bypass_twilio = form_data.get("debug_bypass_twilio", "false").lower() in ["true", "1"]
            lead_id_raw = form_data.get("lead_id")
            
            file_field = form_data.get("attachment") or form_data.get("file") or form_data.get("media_url")
            if file_field is not None:
                if hasattr(file_field, "filename") and file_field.filename:
                    filename = file_field.filename
                    target_path = os.path.join(UPLOAD_DIRECTORY, filename)
                    file_contents = await file_field.read()
                    with open(target_path, "wb") as buffer:
                        buffer.write(file_contents)
                    attachment_asset = filename
                else:
                    attachment_asset = str(file_field)
        else:
            data = await request.json()
            phone = data.get("phone") or data.get("phone_number")
            msg_body = data.get("message") or data.get("body")
            attachment_asset = data.get("attachment") or data.get("file") or data.get("media_url")
            debug_bypass_twilio = data.get("debug_bypass_twilio", False)
            lead_id_raw = data.get("lead_id")

        clean_phone = clean_phone_number(phone)
        lead = None

        if lead_id_raw is not None:
            try:
                lead = db.query(Lead).filter(Lead.id == int(lead_id_raw)).first()
            except (TypeError, ValueError):
                lead = None

        if not lead and clean_phone:
            lead = find_lead_for_inbound_whatsapp(db, clean_phone) or find_lead_by_phone(
                db, clean_phone
            )

        if not msg_body and attachment_asset:
            msg_body = f"Shared media file: {attachment_asset}"
        elif not msg_body:
            msg_body = "Message update from advisor."

        target_phone = clean_phone or clean_phone_number(getattr(lead, "phone_number", None))

        if not lead:
            lead = Lead(
                full_name=build_inbound_whatsapp_lead_name(clean_phone or target_phone),
                email=f"intake_{(clean_phone or target_phone or 'unknown').lstrip('+')}@whatsapp.nexus",
                phone_number=clean_phone or target_phone,
                stage="HANDOFF",
                is_human_locked=True,
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
        else:
            ensure_handoff_for_inbound(db, lead)
            if target_phone and lead.phone_number != target_phone:
                lead.phone_number = target_phone

        passed_media_url = None
        if isinstance(attachment_asset, str) and attachment_asset.strip():
            asset_str = attachment_asset.strip()
            if asset_str.startswith("http"):
                passed_media_url = asset_str
            else:
                PUBLIC_TUNNEL_BASE = get_dynamic_env_tunnel_base()
                if "data:" in asset_str and "base64," in asset_str:
                    try:
                        import uuid
                        import base64
                        header, base64_data = asset_str.split("base64,", 1)
                        ext = ".png"
                        if "image/jpeg" in header: ext = ".jpg"
                        generated_filename = f"upload_{uuid.uuid4().hex}{ext}"
                        target_file_path = os.path.join(UPLOAD_DIRECTORY, generated_filename)
                        file_bytes = base64.b64decode(base64_data.strip())
                        with open(target_file_path, "wb") as f: f.write(file_bytes)
                        passed_media_url = f"{PUBLIC_TUNNEL_BASE}/api/v1/leads/attachments/{generated_filename.replace(' ', '%20')}"
                    except: pass
                else:
                    passed_media_url = f"{PUBLIC_TUNNEL_BASE}/api/v1/leads/attachments/{asset_str.replace(' ', '%20')}"

        outbound_msg = Message(lead_id=lead.id, sender="advisor", text=msg_body, is_read=True, media_url=passed_media_url)
        db.add(outbound_msg)
        touch_lead_activity(db, lead)
        db.commit()

        if not debug_bypass_twilio and target_phone:
            dispatch_live_whatsapp_message(
                to_phone=target_phone, message_body=msg_body, media_url=passed_media_url
            )
        
        refreshed_lead = db.query(Lead).options(joinedload(Lead.messages)).filter(Lead.id == lead.id).first()
        return build_universal_lead_payload(refreshed_lead, db)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active")
@router.get("/active/")
@router.get("/active-stream")
@router.get("/active-stream/")
async def get_active_leads_queue(db: Session = Depends(get_db)):
    """Returns leads currently managed by the AI agent (not in handoff)."""
    try:
        active_leads = (
            db.query(Lead)
            .filter(
                Lead.stage == LeadStage.AI_ACTIVE,
                Lead.is_human_locked == False,
            )
            .order_by(Lead.updated_at.desc())
            .all()
        )
        stats_by_id = _load_message_stats_for_leads(db, [lead.id for lead in active_leads])
        return [
            build_active_queue_item(lead, stats_by_id.get(lead.id, {}))
            for lead in active_leads
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pipeline")
async def get_pipeline_compatibility(limit: int = 5, db: Session = Depends(get_db)):
    sort_column = Lead.updated_at if hasattr(Lead, 'updated_at') else Lead.created_at
    leads = db.query(Lead).options(joinedload(Lead.messages)).order_by(sort_column.desc()).limit(int(limit)).all()
    return [build_universal_lead_payload(l, db) for l in leads]

@router.get("/prospects/summary")
@router.get("/prospects/summary/")
async def get_prospects_dashboard_summary(db: Session = Depends(get_db)):
    try:
        return get_prospects_summary(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/prospects")
@router.get("/prospects/")
async def get_prospects_paginated(
    db: Session = Depends(get_db),
    limit: int = 50,
    cursor: str | None = None,
    q: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    stage: str | None = None,
):
    try:
        return list_prospects_keyset(
            db,
            limit=limit,
            cursor=cursor,
            q=q,
            source=source,
            date_from=date_from,
            date_to=date_to,
            stage=stage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/all")
@router.get("")
@router.get("/")
async def get_all_leads_ledger(db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.updated_at.desc()).all()
    return [build_lead_list_payload(lead) for lead in leads]

@router.post("/{lead_id}/override")
@router.post("/{lead_id}/override/")
async def human_takeover_override(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).options(joinedload(Lead.messages)).filter(Lead.id == lead_id).first()
    if not lead: raise HTTPException(status_code=404, detail="Not found")
    lead.is_human_locked = True
    lead.stage = "HANDOFF"
    db.commit()
    db.refresh(lead)
    return build_universal_lead_payload(lead, db)

@router.post("/{lead_id}/mark-read")
@router.post("/{lead_id}/mark-read/")
async def clear_unread_notifications_badge(lead_id: int, db: Session = Depends(get_db)):
    db.query(Message).filter(Message.lead_id == lead_id, Message.sender.in_(["student", "candidate"])).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"status": "read"}

@router.get("/archive")
@router.get("/archive/")
async def get_archived_leads_compatibility(status: Optional[str] = None, db: Session = Depends(get_db)):
    target_stage = "ARCHIVE" if (status and status.upper() in ["ENROLLED", "ARCHIVE"]) else "AI_ACTIVE"
    leads = db.query(Lead).options(joinedload(Lead.messages)).filter(Lead.stage == target_stage).all()
    return [build_universal_lead_payload(l, db) for l in leads]

@router.get("/attachments/{file_name}")
async def serve_whatsapp_attachment(file_name: str):
    file_path = os.path.join(UPLOAD_DIRECTORY, file_name)
    if not os.path.exists(file_path): raise HTTPException(status_code=404)
    return FileResponse(file_path)


@router.get("/{lead_id}")
@router.get("/{lead_id}/")
async def get_lead_detail(lead_id: int, db: Session = Depends(get_db)):
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.messages))
        .filter(Lead.id == lead_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")
    return build_universal_lead_payload(lead, db)


@router.patch("/{lead_id}/notes")
@router.patch("/{lead_id}/notes/")
async def update_lead_notes(lead_id: int, payload: LeadNotesUpdate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")
    lead.intake_context = payload.notes.strip()
    lead.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return build_universal_lead_payload(lead, db)


@router.patch("/{lead_id}/status")
@router.patch("/{lead_id}/status/")
async def update_lead_status(lead_id: int, update: StatusUpdate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")

    new_stage = update.status.upper().replace("-", "_")
    if new_stage == "ARCHIVED":
        new_stage = "ARCHIVE"

    lead.stage = new_stage
    lead.updated_at = datetime.utcnow()

    if new_stage == "AI_ACTIVE":
        lead.is_human_locked = False
    elif new_stage == "ARCHIVE":
        lead.is_human_locked = False
    elif new_stage in ("HANDOFF", "HANDOFF_ARCHIVE"):
        lead.is_human_locked = True

    db.commit()
    db.refresh(lead)

    return build_universal_lead_payload(lead, db)