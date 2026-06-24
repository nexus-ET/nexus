from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.lead import Lead, LeadStage
from app.models.message import Message
from app.models.message_history import MessageHistory
from app.services.admissions_ai_replies import generate_contextual_admissions_reply
from app.services.agent_runtime import get_or_create_agent_config, get_runtime_agent_config, should_escalate_message
from app.services.security_service import call_with_llm_circuit_breaker, input_sanitizer, output_filter
from app.services.phone_utils import clean_phone_number
from app.services.messaging import send_message

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20


def _ensure_env_loaded() -> None:
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir] + list(current_dir.parents):
        target_env = parent / ".env"
        if target_env.exists():
            load_dotenv(dotenv_path=target_env)
            return
    load_dotenv()


async def process_message(sender_phone: str, message_text: str, wa_id: str, lead_id: int) -> None:
    db = SessionLocal()
    try:
        await _process_message_with_session(
            db=db,
            sender_phone=sender_phone,
            message_text=message_text,
            wa_id=wa_id,
            lead_id=lead_id,
        )
    except Exception:
        logger.exception(
            "WhatsApp AI background task failed for lead_id=%s phone=%s",
            lead_id,
            sender_phone,
        )
        db.rollback()
    finally:
        db.close()


async def _process_message_with_session(
    *,
    db: Session,
    sender_phone: str,
    message_text: str,
    wa_id: str,
    lead_id: int,
) -> None:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        logger.error("Lead %s not found during WhatsApp AI processing.", lead_id)
        return

    runtime_config = get_runtime_agent_config(db)
    if not runtime_config.is_active:
        get_or_create_agent_config(db)
        runtime_config = get_runtime_agent_config(db)

    history_rows = (
        db.query(MessageHistory)
        .filter(MessageHistory.lead_id == lead_id)
        .order_by(MessageHistory.created_at.asc())
        .limit(RECENT_HISTORY_LIMIT)
        .all()
    )

    sanitized_message = input_sanitizer(message_text)
    llm_messages = _build_llm_messages(runtime_config.system_prompt, history_rows, sanitized_message)
    ai_response = await _call_llm(runtime_config.ai_model, llm_messages)
    ai_response = output_filter(ai_response)

    if should_escalate_message(sanitized_message, runtime_config, lead.ml_conversion_score or 0.0):
        lead.stage = LeadStage.HANDOFF
        lead.is_human_locked = True
        ai_response = (
            f"Thanks for reaching out, {lead.full_name.split()[0] if lead.full_name else 'there'}. "
            "I'm connecting you with a human advisor now."
        )

    db.add(
        MessageHistory(
            lead_id=lead_id,
            wa_id=wa_id,
            sender_phone=clean_phone_number(sender_phone),
            role="ai",
            message_text=ai_response,
        )
    )
    db.add(
        Message(
            lead_id=lead_id,
            sender="advisor",
            text=ai_response,
            is_read=True,
        )
    )
    db.commit()

    delivered = await send_message(
        to_number=clean_phone_number(sender_phone),
        body=ai_response,
    )
    if not delivered:
        logger.error(
            "Failed to deliver WhatsApp Cloud API response for lead_id=%s phone=%s",
            lead_id,
            sender_phone,
        )


def _build_llm_messages(
    system_prompt: str,
    history_rows: list[MessageHistory],
    latest_user_message: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    for row in history_rows:
        role = "assistant" if row.role == "ai" else "user"
        messages.append({"role": role, "content": input_sanitizer(row.message_text)})

    if not history_rows or history_rows[-1].message_text != latest_user_message:
        messages.append({"role": "user", "content": input_sanitizer(latest_user_message)})

    return messages


async def _call_llm(
    model: str,
    messages: list[dict[str, str]],
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
) -> str:
    return await call_with_llm_circuit_breaker(
        lambda: _invoke_llm(model, messages, student_name=student_name, has_prior_ai_turns=has_prior_ai_turns)
    )


async def _invoke_llm(
    model: str,
    messages: list[dict[str, str]],
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
) -> str:
    _ensure_env_loaded()
    api_key = os.getenv("OPENAI_API_KEY")
    latest_user = next(
        (message["content"] for message in reversed(messages) if message["role"] == "user"),
        "",
    )

    if not api_key:
        logger.warning("OPENAI_API_KEY is not configured; using contextual admissions replies.")
        return generate_contextual_admissions_reply(
            latest_user,
            student_name=student_name,
            has_prior_ai_turns=has_prior_ai_turns,
        )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        def _invoke() -> str:
            response = client.chat.completions.create(
                model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=messages,
                max_tokens=500,
                temperature=0.6,
            )
            content = response.choices[0].message.content or ""
            cleaned = content.strip()
            if cleaned:
                return cleaned
            return generate_contextual_admissions_reply(
                latest_user,
                student_name=student_name,
                has_prior_ai_turns=has_prior_ai_turns,
            )

        return await asyncio.to_thread(_invoke)
    except Exception:
        logger.exception("LLM call failed for WhatsApp message processing.")
        return generate_contextual_admissions_reply(
            latest_user,
            student_name=student_name,
            has_prior_ai_turns=has_prior_ai_turns,
        )


def _fallback_reply(messages: list[dict[str, str]], student_name: str = "there") -> str:
    latest_user = next(
        (message["content"] for message in reversed(messages) if message["role"] == "user"),
        "",
    )
    has_assistant = any(message["role"] == "assistant" for message in messages)
    return generate_contextual_admissions_reply(
        latest_user,
        student_name=student_name,
        has_prior_ai_turns=has_assistant,
    )


async def send_whatsapp_cloud_message(to_phone: str, message_body: str) -> bool:
    """Backward-compatible wrapper; routes through messaging.send_message."""
    return await send_message(to_number=to_phone, body=message_body)
