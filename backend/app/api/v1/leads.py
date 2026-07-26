from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy import cast, String, or_
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.lead import Lead
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Import Twilio clients and validation modules
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

logger = logging.getLogger(__name__)
router = APIRouter()

def clean_phone_number(raw_phone: str) -> str:
    """ Strips formatting noise to standardize the string for Twilio lookup matrices """
    if not raw_phone:
        return ""
    # Strip spaces, dashes, parentheses, and trailing anomalies
    cleaned = str(raw_phone).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return cleaned

def dispatch_live_whatsapp_message(to_phone: str, message_body: str):
    """ Sends an actual outbound WhatsApp message using Twilio's API environment values. """
    base_dir = Path(__file__).resolve().parents[3]
    env_path = base_dir / ".env"
    load_dotenv(dotenv_path=env_path)

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    sender_number = (
        os.getenv("TWILIO_WHATSAPP_NUMBER") or 
        os.getenv("TWILIO_PHONE_NUMBER") or 
        os.getenv("WHATSAPP_NUMBER") or 
        os.getenv("TWILIO_FROM_NUMBER")
    )

    try:
        if not account_sid or not auth_token or not sender_number:
            logger.warning("Twilio outbound skipped: missing account SID, auth token, or sender number")
            return False
            
        client = Client(account_sid, auth_token)
        
        clean_target = clean_phone_number(to_phone)
        clean_sender = clean_phone_number(sender_number)

        formatted_to = clean_target if clean_target.startswith("whatsapp:") else f"whatsapp:{clean_target}"
        formatted_from = clean_sender if clean_sender.startswith("whatsapp:") else f"whatsapp:{clean_sender}"

        message = client.messages.create(
            from_=formatted_from,
            body=message_body,
            to=formatted_to
        )
        logger.info("Twilio WhatsApp outbound sent sid=%s", message.sid)
        return True
    except Exception as twilio_err:
        logger.exception("Twilio WhatsApp outbound failed: %s", twilio_err)
        return False

class LeadCreate(BaseModel):
    full_name: str
    email: EmailStr
    institution: str
    program_interest: str
    status: Optional[str] = "PROCESSING"
    score: Optional[int] = 0
    agent_execution_state: Optional[str] = "THINKING"
    summary: Optional[str] = None
    next_action: Optional[str] = None


def build_universal_lead_payload(lead: Lead):
    full_name_val = getattr(lead, 'full_name', 'Unknown Lead')
    email_val = getattr(lead, 'email', 'unspecified@nexus.lake')
    phone_val = getattr(lead, 'phone_number', 'Not Provided')
    channel_val = str(getattr(lead, 'channel', 'WHATSAPP'))
    
    current_stage = str(getattr(lead, 'stage', 'AI_ACTIVE'))
    summary_text = getattr(lead, 'academic_summary', None) or "Initializing tracking details..."
    is_human_locked_val = getattr(lead, 'is_human_locked', False)
    
    is_escalated = ("HANDOFF" in current_stage.upper()) or ("HUMAN" in current_stage.upper()) or (is_human_locked_val == True)
    
    raw_country = getattr(lead, 'preferred_country', None)
    destination_value = raw_country if raw_country else ("Human Advisor Intake" if is_escalated else "AI Autonomous Routing")

    return {
        "id": getattr(lead, 'id', None),
        "name": full_name_val,
        "full_name": full_name_val,
        "student_lead": full_name_val,
        "student_name": full_name_val,
        "lead_name": full_name_val,
        "email": email_val,
        "phone_number": phone_val,
        "phone": phone_val,
        "channel": channel_val,
        "stage": current_stage,
        "status": current_stage,
        "ai_status": current_stage,  
        "agent_execution_state": "ESCALATED" if is_escalated else "COMPLETED",
        "engagement_score": int(getattr(lead, 'ml_conversion_score', 85) or 85),
        "score": int(getattr(lead, 'ml_conversion_score', 85) or 85),
        "last_interaction_summary": summary_text,
        "academic_summary": summary_text,
        "ai_next_action": "Awaiting Human Intervention Override" if is_escalated else "Monitoring channel queues.",
        "next_action": "Awaiting Human Intervention Override" if is_escalated else "Monitoring channel queues.",
        "destination": destination_value,
        "destination_name": destination_value,
        "assigned_destination": destination_value,
        "target_destination": destination_value,
        "destination_country": destination_value,
        "preferred_country": raw_country or "Undetermined",
        "country": raw_country or "Undetermined",
        "target_location": destination_value,
        "location": destination_value,
        "institution": getattr(lead, 'institution', "Nexus Academy"),
        "program": getattr(lead, 'program_interest', "General Curriculum"),
        "program_interest": getattr(lead, 'program_interest', "General Curriculum"),
        "is_human_locked": is_human_locked_val or is_escalated,
        "assigned_agent": "Unassigned Support Team" if is_escalated else "Nexus Core AI Admin",
        "created_at": lead.created_at.isoformat() if getattr(lead, 'created_at', None) else None,
        "updated_at": lead.updated_at.isoformat() if getattr(lead, 'updated_at', None) else None
    }


@router.post("/active", status_code=status.HTTP_201_CREATED)
@router.post("/active/", status_code=status.HTTP_201_CREATED)
async def create_simulated_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    try:
        new_lead = Lead(
            full_name=payload.full_name,
            email=payload.email,
            academic_summary=(
                f"Institution: {payload.institution}\n"
                f"Program Interest: {payload.program_interest}\n"
                f"Current Status: {payload.status}\n"
                f"Agent State: {payload.agent_execution_state}\n"
                f"Summary: {payload.summary}\n"
                f"Next Action Sequence: {payload.next_action}"
            ),
            ml_conversion_score=float(payload.score)
        )
        if hasattr(new_lead, 'stage'): new_lead.stage = "AI_ACTIVE"
        if hasattr(new_lead, 'channel'): new_lead.channel = "EMAIL"
            
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        return {"status": "success", "lead_id": new_lead.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/whatsapp-reply")
@router.post("/webhook/whatsapp-reply/")
async def handle_inbound_whatsapp_reply(request: Request, db: Session = Depends(get_db)):
    try:
        form_data = await request.form()
        incoming_msg_raw = form_data.get("Body", "").strip()
        sender_phone_raw = form_data.get("From", "")
        
        sender_phone_clean = sender_phone_raw.replace("whatsapp:", "").strip()
        sender_phone_clean = clean_phone_number(sender_phone_clean)
        
        logger.info("Twilio inbound WhatsApp from %s", sender_phone_clean)
        
        if not incoming_msg_raw:
            return Response(content="No body parsed", media_type="text/plain")

        lead = db.query(Lead).filter(
            or_(
                Lead.phone_number == sender_phone_clean,
                Lead.phone_number == f"+{sender_phone_clean}",
                Lead.phone_number.contains(sender_phone_clean[-8:])
            )
        ).first()
        
        if not lead:
            logger.info("No lead for %s; creating organic WhatsApp prospect", sender_phone_clean)
            safe_email_slug = sender_phone_clean.replace("+", "")
            lead = Lead(
                full_name=f"Organic WA Prospect ({sender_phone_clean[-4:]})",
                email=f"prospect_{safe_email_slug}@whatsapp.nexus",
                phone_number=sender_phone_clean,
                ml_conversion_score=80.0
            )
            if hasattr(lead, 'stage'): lead.stage = "HANDOFF"
            if hasattr(lead, 'channel'): lead.channel = "WHATSAPP"
            if hasattr(lead, 'is_human_locked'): lead.is_human_locked = True
            db.add(lead)
            db.commit()
            db.refresh(lead)

        if not lead.academic_summary:
            lead.academic_summary = ""
            
        lead.academic_summary += f"\nCandidate: {incoming_msg_raw}"

        student_intent = incoming_msg_raw.lower()
        
        # 🚨 SYSTEM ESCALATION DETECTOR
        if any(word in student_intent for word in ["person", "human", "advisor", "agent", "talk to", "escalate"]):
            if hasattr(lead, 'stage'): lead.stage = "HANDOFF"
            if hasattr(lead, 'is_human_locked'): lead.is_human_locked = True
                
            ai_agent_response = (
                f"Understood completely, {lead.full_name}. 🤝 I am pausing my automation cycle and "
                f"flagging your record for our human intake queue. An admissions advisor will connect "
                f"with you on this WhatsApp thread shortly!"
            )
            lead.academic_summary += f"\n[Escalation Event] Workflow control routed to human queue."
            
        elif any(word in student_intent for word in ["yes", "yeah", "confirm", "sure", "want"]):
            ai_agent_response = (
                f"Awesome, glad to hear that, {lead.full_name}! 🚀 Let's get your documentation moving. "
                f"Are you currently holding an official high school or university transcript?"
            )
            lead.academic_summary += f"\n[AI Core Auto-Prompt Summary] Prompted for transcripts."
        elif any(word in student_intent for word in ["no", "not yet", "later"]):
            ai_agent_response = (
                f"No worries at all! We can easily look at future enrollment windows. "
                f"What timing are you thinking about?"
            )
            lead.academic_summary += f"\n[AI Core Auto-Prompt Summary] Prompted for future window."
        else:
            ai_agent_response = f"Got it! Thank you for that update. I've logged that directly in our tracking matrix."

        db.commit()

        # 🛠️ Outbound push bypasses fallback XML delays
        dispatch_live_whatsapp_message(to_phone=sender_phone_clean, message_body=ai_agent_response)

        twiml_response = MessagingResponse()
        twiml_response.message(ai_agent_response)
        logger.info("Twilio inbound reply dispatched for lead_id=%s", getattr(lead, "id", None))
        return Response(content=str(twiml_response), media_type="application/xml")
    except Exception as err:
        db.rollback() 
        logger.exception("Twilio inbound WhatsApp webhook failed: %s", err)
        return Response(content=f"Internal Server Error: {str(err)}", status_code=500)


@router.post("/webhook/social-ingress")
@router.post("/webhook/social-ingress/")
async def handle_external_social_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Malformed JSON payload received by ingress engine.")

        full_name = data.get("full_name") or data.get("name") or "Anonymous Prospect"
        email = data.get("email") or "unspecified@nexus-lake.com"
        phone = data.get("phone") or data.get("phone_number")
        interest = data.get("program_interest") or "General Inquiry"
        institution = data.get("institution") or "Global Web Portal Entry"
        
        if not phone:
            raise HTTPException(status_code=400, detail="Missing critical 'phone' parameter validation rule.")
            
        clean_phone = clean_phone_number(phone)

        if "Manual Advisor Intervention" in institution:
            advisor_message_body = data.get("message") or data.get("body") or data.get("text") or data.get("name")
            logger.info("Manual advisor Twilio outbound to %s", clean_phone)
            
            lead = db.query(Lead).filter(or_(Lead.phone_number == clean_phone, Lead.email == email)).first()
            if lead:
                if not lead.academic_summary: 
                    lead.academic_summary = ""
                lead.academic_summary += f"\nAdvisor: {advisor_message_body}"
                db.commit()
            
            dispatch_live_whatsapp_message(to_phone=clean_phone, message_body=advisor_message_body)
            return {"status": "success", "message": "Advisor text delivered smoothly."}

        existing_lead = db.query(Lead).filter(or_(Lead.phone_number == clean_phone, Lead.email == email)).first()

        if existing_lead:
            logger.info("Social ingress recycled existing lead for %s", clean_phone)
            if hasattr(existing_lead, 'stage'): existing_lead.stage = "HANDOFF"
            if hasattr(existing_lead, 'is_human_locked'): existing_lead.is_human_locked = True
            
            if not existing_lead.academic_summary: existing_lead.academic_summary = ""
            existing_lead.academic_summary += f"\n[Intake Event] Direct intake re-triggered at {institution} for program: {interest}."
            db.commit()
            db.refresh(existing_lead)
            
            ai_introductory_greeting = (
                f"Hello {existing_lead.full_name}! 👋 This is the Admissions Office at Nexus.\n\n"
                f"We noticed your new inquiry regarding our *{interest}* track. Let's look over your dashboard layout right now!"
            )
            dispatch_live_whatsapp_message(to_phone=clean_phone, message_body=ai_introductory_greeting)
            return {"status": "success", "lead_id": existing_lead.id, "action": "recycled"}

        new_lead = Lead(
            full_name=full_name, 
            email=email, 
            phone_number=clean_phone,
            academic_summary=f"Inquiry received regarding: {interest} at {institution}.",
            ml_conversion_score=92.0
        )
        if hasattr(new_lead, 'stage'): new_lead.stage = "HANDOFF"
        if hasattr(new_lead, 'channel'): new_lead.channel = "WHATSAPP"
        if hasattr(new_lead, 'is_human_locked'): new_lead.is_human_locked = True
        
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        
        ai_introductory_greeting = (
            f"Hello {full_name}! 👋 This is the Admissions Office Admin Assistant at Nexus.\n\n"
            f"Thank you for reaching out to us regarding your interest in the *{interest}* program! "
            f"Are you looking to start classes during the upcoming academic semester?"
        )
        dispatch_live_whatsapp_message(to_phone=clean_phone, message_body=ai_introductory_greeting)
        
        return {"status": "success", "lead_id": new_lead.id, "action": "created"}

    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        db.rollback()
        logger.exception("Social ingress webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database operational crash: {str(e)}")


@router.get("/active")
@router.get("/active/")
@router.get("/active-stream")
@router.get("/active-stream/")
async def get_active_leads_queue(db: Session = Depends(get_db)):
    try:
        leads_list = db.query(Lead).filter(
            cast(Lead.stage, String).ilike("%AI_ACTIVE%") & 
            cast(Lead.stage, String).not_ilike("%HANDOFF%")
        ).all()
        return [build_universal_lead_payload(lead) for lead in leads_list]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline")
@router.get("/pipeline/")
async def get_pipeline_summary(limit: int = 5, db: Session = Depends(get_db)):
    try:
        leads_list = db.query(Lead).order_by(Lead.created_at.desc()).limit(limit).all()
        total_count = db.query(Lead).count()
        return {
            "leads": [build_universal_lead_payload(lead) for lead in leads_list], 
            "metrics": {
                "total_leads": total_count, 
                "active_channels": {
                    "EMAIL": db.query(Lead).filter(cast(Lead.channel, String).ilike("%EMAIL%")).count(), 
                    "WHATSAPP": db.query(Lead).filter(cast(Lead.channel, String).ilike("%WHATSAPP%")).count(), 
                    "SOCIAL": 0
                }, 
                "conversion_rate_estimate": 24.5
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/handoffs")
@router.get("/handoff")
@router.get("/handoffs/")
@router.get("/handoff/")
@router.get("/queue")
@router.get("/queue/")
async def get_handoff_queue(db: Session = Depends(get_db)):
    try:
        handoff_list = db.query(Lead).filter(
            or_(
                cast(Lead.stage, String).ilike("%HANDOFF%"),
                cast(Lead.stage, String).ilike("%HUMAN%"),
                Lead.is_human_locked == True
            )
        ).all()
        return [build_universal_lead_payload(lead) for lead in handoff_list]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
@router.get("/all/")
@router.get("")
@router.get("/")
async def get_all_prospects_ledger(stage: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        query = db.query(Lead).order_by(Lead.created_at.desc())
        if stage: 
            query = query.filter(cast(Lead.stage, String).ilike(f"%{stage}%"))
        return [build_universal_lead_payload(lead) for lead in query.all()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive")
@router.get("/archive/")
async def get_archived_leads_ledger(archive_status: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        archived_list = db.query(Lead).filter(
            cast(Lead.stage, String).in_(["ARCHIVED", "ARCHIVE", "COMPLETED"])
        ).all()
        return [build_universal_lead_payload(lead) for lead in archived_list]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{lead_id}/override")
@router.post("/{lead_id}/override/")
@router.put("/{lead_id}/override")
@router.put("/{lead_id}/override/")
@router.post("/{lead_id}/takeover")
@router.put("/{lead_id}/takeover")
@router.post("/takeover/{lead_id}")
@router.put("/takeover/{lead_id}")
async def universal_human_takeover_override(lead_id: int, db: Session = Depends(get_db)):
    try:
        logger.info("Human takeover override for lead_id=%s", lead_id)
        
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead ID {lead_id} absent from database records.")

        if hasattr(lead, 'is_human_locked'):
            lead.is_human_locked = True
        if hasattr(lead, 'stage'):
            lead.stage = "HANDOFF"
            
        if not lead.academic_summary:
            lead.academic_summary = ""
        lead.academic_summary += f"\n[Takeover Override] Manual advisor intersection accepted via Dashboard. AI core suspended."

        db.commit()
        db.refresh(lead)

        if getattr(lead, "phone_number", None):
            clean_target_phone = clean_phone_number(lead.phone_number)
            takeover_notification = (
                f"Hello {getattr(lead, 'full_name', 'there')}! 👋 A human admissions advisor has just joined "
                f"this conversation thread and taken over from our automated assistant. Ask away!"
            )
            dispatch_live_whatsapp_message(to_phone=clean_target_phone, message_body=takeover_notification)

        logger.info("Human takeover confirmed for lead_id=%s", lead_id)
        return {
            "status": "success",
            "message": "AI agent paused cleanly. Live chat channels assigned to manual agent desktop workspace view.",
            "lead": build_universal_lead_payload(lead)
        }
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        db.rollback()
        logger.exception("Takeover endpoint failed for lead_id=%s: %s", lead_id, e)
        raise HTTPException(status_code=500, detail=str(e))