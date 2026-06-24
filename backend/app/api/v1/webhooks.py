from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.lead import Lead, LeadChannel

router = APIRouter()

# Meta requires a verification handshake when you first connect their dashboard
@router.get("/meta")
async def verify_meta_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == "YOUR_SECRET_TOKEN":
        return int(params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Verification token mismatch")

# The landing pad for live messages
@router.post("/meta")
async def receive_meta_message(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    
    # Extract data from Meta's nested JSON structure
    try:
        # (This structure changes slightly depending on WhatsApp vs Instagram)
        messaging_event = payload["entry"][0]["messaging"][0]
        sender_id = messaging_event["sender"]["id"]
        message_text = messaging_event["message"]["text"]
        
        # Save straight to your existing Lead model!
        new_lead = Lead(
            full_name=f"Social User {sender_id}",
            channel=LeadChannel.INSTAGRAM,  # Or WHATSAPP based on payload data
            academic_summary=f"Inbound Message: {message_text}"
        )
        db.add(new_lead)
        db.commit()
        return {"status": "event_processed"}
    except Exception as e:
        return {"status": "ignored_or_invalid_format"}