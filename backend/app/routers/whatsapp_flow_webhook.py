from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.whatsapp_flow_booking import handle_flow_data_exchange
from app.services.whatsapp_flow_crypto import (
    decrypt_flow_request,
    encrypt_flow_response,
    get_flow_public_key_pem,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/whatsapp-flow")
@router.get("/whatsapp-flow/")
async def whatsapp_flow_health():
    return {
        "status": "ok",
        "public_key_configured": bool(get_flow_public_key_pem()),
        "note": "Upload the public key to Meta WhatsApp Flow settings for encrypted data exchange.",
    }


@router.get("/whatsapp-flow/public-key")
@router.get("/whatsapp-flow/public-key/")
async def whatsapp_flow_public_key():
    return PlainTextResponse(content=get_flow_public_key_pem(), media_type="text/plain")


@router.post("/whatsapp-flow")
@router.post("/whatsapp-flow/")
async def whatsapp_flow_data_exchange(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        logger.exception("Invalid WhatsApp Flow webhook body")
        return Response(status_code=400, content="Invalid JSON")

    if not body.get("encrypted_aes_key"):
        logger.warning("WhatsApp Flow webhook received unencrypted payload: %s", list(body.keys()))
        action = body.get("action") or "INIT"
        response = handle_flow_data_exchange(
            db,
            {
                "action": action,
                "data": body.get("data") or {},
                "screen": body.get("screen") or "BOOKING",
                "flow_token": body.get("flow_token") or "",
                "payload": body.get("payload") or {},
            },
        )
        return response

    try:
        decrypted, aes_key, iv = decrypt_flow_request(body)
        logger.info("WhatsApp Flow data exchange action=%s", decrypted.get("action"))
        response = handle_flow_data_exchange(db, decrypted)
        encrypted = encrypt_flow_response(response, aes_key, iv)
        return Response(content=encrypted, media_type="text/plain")
    except Exception:
        logger.exception("WhatsApp Flow decrypt/handle failed")
        return Response(status_code=421, content="Decryption failed")


@router.get("/whatsapp-flow/definition")
@router.get("/whatsapp-flow/definition/")
async def whatsapp_flow_definition():
    from app.services.whatsapp_flow_booking import get_flow_json_template

    return get_flow_json_template()
