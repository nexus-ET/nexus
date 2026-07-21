import os
import re
import traceback
import mimetypes
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
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
from app.services.admissions_intake_flow import build_intake_profile_summary
from app.services.prospects_service import get_prospects_summary, list_prospects_keyset, resolve_platform_badge
from app.schemas.offline_lead import (
    OfflineLeadCreate,
    OfflineLeadDuplicateCheckResponse,
    OfflineLeadUpdate,
    SortDirection,
    SortField,
)
from app.services.offline_leads_service import (
    build_offline_lead_list_item,
    check_offline_lead_duplicates,
    create_offline_lead,
    list_offline_leads,
    update_offline_lead,
)
from app.services.messaging import WhatsAppDeliveryError
from app.services.twilio_ai_conversation import initiate_ai_outreach
from app.services.twilio_outbound import dispatch_live_whatsapp_message
from app.api import deps
from app.models.user import User
from app.schemas.status_definition import (
    PipelineStatusUpdateRequest,
    PipelineStatusUpdateResponse,
    StatusDefinitionsResponse,
    StudentJourneyResponse,
    ValidTransitionOption,
    ValidTransitionsResponse,
)
from app.models.status_definition import StatusDefinition
from app.services.status_definition_service import list_status_definitions, resolve_lead_status_meta
from app.services.status_transition_service import get_valid_transitions
from app.services.student_status_service import (
    get_student_journey,
    resolve_effective_lead_status_id,
    sync_lead_pipeline_status_id,
    update_student_status,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Schema for incoming PATCH requests
class StatusUpdate(BaseModel):
    status: str


class LeadNotesUpdate(BaseModel):
    notes: str = Field(..., max_length=10000)


class AiOutreachRequest(BaseModel):
    force_restart: bool = False

# Global directory where your workspace panel saves files
UPLOAD_DIRECTORY = "uploads" 
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True) 

# ---------------------------------------------------------
# 🛠️ NEW PATCH ROUTE TO FIX 404
# ---------------------------------------------------------
ALLOWED_QUEUE_INTERACTION_DAYS = {0, 5, 15, 30}


def _normalize_queue_interaction_days(days: int) -> int | None:
    """Return day window for queue filtering, or None for all time."""
    if days == 0:
        return None
    if days in ALLOWED_QUEUE_INTERACTION_DAYS:
        return days
    return 5


def _apply_lead_queue_search(query, q: str | None):
    term = (q or "").strip()
    if not term:
        return query

    pattern = f"%{term.lower()}%"
    filters = [
        func.lower(Lead.full_name).like(pattern),
        func.lower(Lead.email).like(pattern),
    ]
    digits = re.sub(r"\D", "", term)
    if digits:
        filters.append(Lead.phone_number.like(f"%{digits}%"))
    return query.filter(or_(*filters))


def _apply_lead_interaction_window(query, db: Session, days: int | None):
    if not days or days <= 0:
        return query

    cutoff = datetime.utcnow() - timedelta(days=days)
    latest_msg = (
        db.query(
            Message.lead_id.label("lead_id"),
            func.max(Message.created_at).label("latest_at"),
        )
        .group_by(Message.lead_id)
        .subquery()
    )
    activity_at = func.coalesce(latest_msg.c.latest_at, Lead.updated_at, Lead.created_at)
    return query.outerjoin(latest_msg, Lead.id == latest_msg.c.lead_id).filter(activity_at >= cutoff)


def _build_handoff_leads_query(db: Session):
    return db.query(Lead).filter(
        or_(
            cast(Lead.stage, String).ilike("%HANDOFF%"),
            cast(Lead.stage, String).ilike("%HUMAN%"),
            Lead.is_human_locked == True,
        )
    )


def _build_active_leads_query(db: Session):
    return db.query(Lead).filter(
        Lead.stage == LeadStage.AI_ACTIVE,
        Lead.is_human_locked == False,
    )


@router.get("/queue")
@router.get("/queue/")
@router.get("/handoffs")
@router.get("/handoffs/")
@router.get("/handoff")
@router.get("/handoff/")
async def get_handoff_queue(
    db: Session = Depends(get_db),
    days: int = Query(5, ge=0, le=365),
    q: str | None = Query(None, max_length=120),
):
    """
    Fetches leads flagged as HANDOFF or manually locked by a human.
    Default: activity within the last 5 days. Pass days=0 for all time.
    When q is set, the activity window is ignored and all matching candidates are returned.
    """
    try:
        query = _build_handoff_leads_query(db)
        if q and q.strip():
            query = _apply_lead_queue_search(query, q)
        else:
            query = _apply_lead_interaction_window(
                query, db, _normalize_queue_interaction_days(days)
            )
        handoff_list = query.order_by(Lead.updated_at.desc()).all()
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
    if "messages" in lead.__dict__ and lead.__dict__["messages"] is not None:
        all_msgs = sorted(lead.messages, key=lambda message: message.created_at or datetime.min)
    else:
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

    status_definition_id, status_stage_name, status_category = resolve_lead_status_meta(db, lead)
    status_description = None
    if status_definition_id:
        from app.models.status_definition import StatusDefinition

        definition = db.query(StatusDefinition).filter(StatusDefinition.id == status_definition_id).first()
        if definition:
            status_description = definition.description

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
        "status_definition_id": status_definition_id,
        "status_stage_name": status_stage_name,
        "status_category": status_category,
        "status_description": status_description,
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


def build_active_queue_item(
    lead: Lead,
    stats: dict | None = None,
    db: Session | None = None,
    *,
    status_by_id: dict | None = None,
) -> dict:
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

    status_definition_id = None
    status_stage_name = None
    status_category = None
    status_description = None
    if db is not None:
        cached = (
            status_by_id.get(lead.status_definition_id)
            if status_by_id and lead.status_definition_id
            else None
        )
        if cached is not None:
            status_definition_id = cached.id
            status_stage_name = cached.stage_name
            status_category = cached.category
            status_description = cached.description
        else:
            status_definition_id, status_stage_name, status_category = resolve_lead_status_meta(db, lead)
            if status_definition_id:
                definition = (
                    status_by_id.get(status_definition_id)
                    if status_by_id is not None
                    else db.query(StatusDefinition).filter(StatusDefinition.id == status_definition_id).first()
                )
                if definition:
                    status_description = definition.description

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
        "status_definition_id": status_definition_id,
        "status_stage_name": status_stage_name,
        "status_category": status_category,
        "status_description": status_description,
        "unread_count": stats.get("unread_count", 0),
        "total_messages_received": stats.get("total_messages_received", 0),
        "has_ai_messages": stats.get("has_ai_messages", False),
        "latest_interaction_time": latest_time,
        "updated_at": updated_time,
        "created_at": base_time,
        "last_message": fallback_text,
        "messages": [],
        **{
            key: value
            for key, value in build_intake_profile_summary(
                lead,
                db,
                refresh_lead=False,
                include_booking_options=False,
                include_session_fields=False,
            ).items()
            if key
            not in {
                "available_consultation_dates",
                "available_consultation_times",
            }
        },
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
        "handoff_ai_confidence": getattr(lead, "handoff_ai_confidence", None),
        "handoff_reason": getattr(lead, "handoff_reason", None),
        "messages": [],
        **{
            key: value
            for key, value in build_intake_profile_summary(lead, db=None).items()
            if key
            not in {
                "available_consultation_dates",
                "available_consultation_times",
                "selected_consultation_date",
            }
        },
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
            from app.services.student_status_service import on_lead_created

            on_lead_created(db, lead, source="WhatsApp inbound")
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

        from app.services.student_status_service import on_whatsapp_inbound

        on_whatsapp_inbound(db, lead)

        logger.info(
            "Saved inbound WhatsApp message lead_id=%s message_id=%s",
            lead.id,
            inbound_db_row.id,
        )

        db.refresh(lead)

        from app.services.messaging import dispatch_inbound_whatsapp_ai

        await dispatch_inbound_whatsapp_ai(
            db,
            lead,
            sender_phone_clean,
            incoming_msg_raw,
            flow_data=str(flow_data_raw) if flow_data_raw else None,
        )

        twiml = MessagingResponse()
        return Response(content=str(twiml), media_type="application/xml")
        
    except Exception as err:
        db.rollback()
        return Response(content=str(err), status_code=500)

@router.post("/{lead_id}/ai-outreach")
@router.post("/{lead_id}/ai-outreach/")
async def start_ai_whatsapp_outreach(
    lead_id: int,
    payload: AiOutreachRequest | None = None,
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")

    if normalize_lead_stage(lead.stage) != "AI_ACTIVE":
        raise HTTPException(status_code=400, detail="Lead is not in AI Active status.")

    force_restart = bool(payload.force_restart) if payload else False

    try:
        sent_messages = await initiate_ai_outreach(db, lead, force_restart=force_restart)
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
            from app.services.student_status_service import on_lead_created

            on_lead_created(db, lead, source="Admin message")
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
            from app.services.student_status_service import on_whatsapp_outreach

            on_whatsapp_outreach(db, lead, source="admin message")
        
        refreshed_lead = db.query(Lead).options(joinedload(Lead.messages)).filter(Lead.id == lead.id).first()
        return build_universal_lead_payload(refreshed_lead, db)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active")
@router.get("/active/")
@router.get("/active-stream")
@router.get("/active-stream/")
def get_active_leads_queue(
    db: Session = Depends(get_db),
    days: int = Query(5, ge=0, le=365),
    q: str | None = Query(None, max_length=120),
):
    """Returns leads currently managed by the AI agent (not in handoff)."""
    try:
        query = _build_active_leads_query(db)
        if q and q.strip():
            query = _apply_lead_queue_search(query, q)
        else:
            query = _apply_lead_interaction_window(
                query, db, _normalize_queue_interaction_days(days)
            )
        active_leads = query.order_by(Lead.updated_at.desc()).all()
        stats_by_id = _load_message_stats_for_leads(db, [lead.id for lead in active_leads])
        status_by_id = {
            row.id: row for row in db.query(StatusDefinition).all()
        }
        return [
            build_active_queue_item(
                lead,
                stats_by_id.get(lead.id, {}),
                db,
                status_by_id=status_by_id,
            )
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
    category: str | None = None,
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
            category=category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/offline")
@router.get("/offline/")
def get_offline_leads(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    status: str | None = None,
    sort_by: SortField = "created_at",
    sort_dir: SortDirection = "desc",
):
    """Server-side paginated list of offline-sourced leads."""
    try:
        return list_offline_leads(
            db,
            page=page,
            page_size=page_size,
            q=q,
            status=status,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/offline/check-duplicates", response_model=OfflineLeadDuplicateCheckResponse)
@router.get("/offline/check-duplicates/", response_model=OfflineLeadDuplicateCheckResponse)
def get_offline_lead_duplicate_check(
    db: Session = Depends(get_db),
    email: str = "",
    phone_country_iso2: str = "",
    phone_local: str = "",
    exclude_lead_id: int | None = None,
):
    """Check whether email or phone is already registered before saving an offline lead."""
    try:
        return check_offline_lead_duplicates(
            db,
            email=email,
            phone_country_iso2=phone_country_iso2,
            phone_local=phone_local,
            exclude_lead_id=exclude_lead_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/offline", status_code=status.HTTP_201_CREATED)
@router.post("/offline/", status_code=status.HTTP_201_CREATED)
def post_offline_lead(payload: OfflineLeadCreate, db: Session = Depends(get_db)):
    """Create a manually entered offline lead (defaults: source=Offline, stage=AI Active)."""
    try:
        lead = create_offline_lead(db, payload)

        return build_offline_lead_list_item(lead, db)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/offline/{lead_id}")
@router.patch("/offline/{lead_id}/")
def patch_offline_lead(lead_id: int, payload: OfflineLeadUpdate, db: Session = Depends(get_db)):
    """Update a manually entered offline lead."""
    try:
        lead = update_offline_lead(db, lead_id, payload)
        return build_offline_lead_list_item(lead, db)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
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


@router.get("/status-definitions", response_model=StatusDefinitionsResponse)
@router.get("/status-definitions/", response_model=StatusDefinitionsResponse)
async def list_pipeline_status_definitions(
    _: User = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    return {"items": list_status_definitions(db)}


@router.get("/{lead_id}/journey", response_model=StudentJourneyResponse)
@router.get("/{lead_id}/journey/", response_model=StudentJourneyResponse)
async def get_student_journey_timeline(
    lead_id: int,
    _: User = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")
    return {"student_id": lead_id, "items": get_student_journey(db, lead_id)}


@router.get("/{lead_id}/valid-transitions", response_model=ValidTransitionsResponse)
@router.get("/{lead_id}/valid-transitions/", response_model=ValidTransitionsResponse)
async def get_student_valid_transitions(
    lead_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")

    sync_lead_pipeline_status_id(db, lead)
    db.refresh(lead)
    current_status_id = resolve_effective_lead_status_id(db, lead)
    grouped = get_valid_transitions(db, current_status_id, user=current_user)
    return ValidTransitionsResponse(
        student_id=lead_id,
        current_status_id=current_status_id,
        forward=[ValidTransitionOption(**item) for item in grouped["forward"]],
        express=[ValidTransitionOption(**item) for item in grouped["express"]],
        backward=[ValidTransitionOption(**item) for item in grouped["backward"]],
        relaunch=[ValidTransitionOption(**item) for item in grouped["relaunch"]],
    )


@router.get("/{lead_id}/profile-booking")
@router.get("/{lead_id}/profile-booking/")
def get_lead_profile_booking(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    from app.services.counselling_service import get_lead_profile_booking_context

    return get_lead_profile_booking_context(db, current_user, lead_id)


@router.get("/{lead_id}/digital-presence-links")
@router.get("/{lead_id}/digital-presence-links/")
def get_lead_digital_presence_links(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")
    from app.services.digital_presence_link_service import get_digital_presence_links_for_lead

    return get_digital_presence_links_for_lead(db, lead_id).model_dump()


@router.get("/{lead_id}")
@router.get("/{lead_id}/")
def get_lead_detail(lead_id: int, db: Session = Depends(get_db)):
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


@router.patch("/{lead_id}/pipeline-status", response_model=PipelineStatusUpdateResponse)
@router.patch("/{lead_id}/pipeline-status/", response_model=PipelineStatusUpdateResponse)
async def update_student_pipeline_status(
    lead_id: int,
    payload: PipelineStatusUpdateRequest,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead profile not found.")

    use_structured_transition = payload.transition_type is not None
    result = update_student_status(
        db,
        student_id=lead_id,
        status_id=payload.status_definition_id,
        changed_by_type="admin",
        changed_by_user_id=current_user.id,
        comments=payload.comments,
        skip_if_unchanged=True,
        allow_override=not use_structured_transition,
        transition_type=payload.transition_type,
        acting_user=current_user,
        commit=True,
    )
    if result.get("blocked"):
        status_code = 403 if "Unauthorized Attempt" in str(result.get("reason", "")) else 400
        raise HTTPException(status_code=status_code, detail=result.get("reason", "Status update blocked."))
    return {
        "student_id": lead_id,
        "status_definition_id": result["status_id"],
        "stage_name": result.get("stage_name"),
        "history_id": result.get("history_id"),
        "changed": result.get("changed", True),
    }


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