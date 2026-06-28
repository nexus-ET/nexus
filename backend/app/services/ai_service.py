from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.lead import Lead
from app.config import settings
from app.services.admissions_ai_replies import generate_contextual_admissions_reply
from app.services.agent_runtime import RuntimeAgentConfig, get_runtime_agent_config
from app.services.ai_providers import parse_model_ref
from app.services.organization_context import append_organization_context
from app.services.security_service import (
    LLM_TIMEOUT_SECONDS,
    call_with_llm_circuit_breaker,
    input_sanitizer,
    output_filter,
)
from app.services.phone_utils import clean_phone_number

logger = logging.getLogger(__name__)

RECENT_HISTORY_LIMIT = 20

JSON_RESPONSE_DIRECTIVE = (
    "\n\nRespond with valid JSON only using this schema: "
    '{"reply": "<WhatsApp message to the student>", '
    '"confidence": <number from 0.0 to 1.0 indicating how confident you are in the reply>}'
)


@dataclass(frozen=True)
class LlmResult:
    text: str
    confidence: float


def _ensure_env_loaded() -> None:
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir] + list(current_dir.parents):
        target_env = parent / ".env"
        if target_env.exists():
            load_dotenv(dotenv_path=target_env)
            return
    load_dotenv()


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _parse_llm_json_payload(content: str, *, fallback_text: str, fallback_confidence: float) -> LlmResult:
    cleaned = (content or "").strip()
    if not cleaned:
        return LlmResult(text=fallback_text, confidence=fallback_confidence)

    candidates = [cleaned]
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidates.insert(0, cleaned[brace_start : brace_end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                reply = str(payload.get("reply", "")).strip()
                confidence_raw = payload.get("confidence", fallback_confidence)
                confidence = _clamp_confidence(float(confidence_raw))
                if reply:
                    return LlmResult(text=reply, confidence=confidence)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    if cleaned and not cleaned.startswith("{"):
        return LlmResult(text=cleaned, confidence=max(fallback_confidence, 0.65))

    return LlmResult(text=fallback_text, confidence=fallback_confidence)


HANDOFF_NOTICE_MARKERS = (
    "redirecting it to an Admissions Officer",
    "An Admissions Officer is reviewing",
)


def build_handoff_student_notice(lead: Lead) -> LlmResult:
    first = (lead.full_name or "there").split()[0]
    text = (
        f"Thank you, {first}. Your question needs specialist attention from our admissions team. "
        "I'm redirecting it to an Admissions Officer now — they will get back to you on this WhatsApp thread shortly."
    )
    return LlmResult(text=text, confidence=1.0)


def build_handoff_followup_notice(lead: Lead, incoming_text: str = "") -> LlmResult:
    first = (lead.full_name or "there").split()[0]
    snippet = (incoming_text or "").strip()
    if snippet:
        text = (
            f"Thanks, {first} — I've added \"{snippet[:80]}\" to your file. "
            "An Admissions Officer is reviewing your thread and will reply here shortly."
        )
    else:
        text = (
            f"Thanks, {first}. An Admissions Officer is reviewing your thread "
            "and will reply here on WhatsApp shortly."
        )
    return LlmResult(text=text, confidence=1.0)


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
    from app.services.twilio_ai_conversation import handle_ai_active_inbound

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        logger.error("Lead %s not found during WhatsApp AI processing.", lead_id)
        return

    await handle_ai_active_inbound(
        db,
        lead,
        input_sanitizer(message_text),
        clean_phone_number(sender_phone) or sender_phone,
    )


async def compose_agent_message(
    db: Session,
    runtime_config: RuntimeAgentConfig,
    lead: Lead,
    *,
    task: str,
    incoming_text: str = "",
    conversation_history: list[tuple[str, str]] | None = None,
    extra_context: str = "",
) -> LlmResult:
    """Generate a student-facing message using Agent Console system prompt + structured JSON output."""
    student_name = (lead.full_name or "there").split()[0] if (lead.full_name or "").strip() else "there"
    history = conversation_history or []
    has_prior_ai_turns = any(role == "assistant" for role, _ in history)

    enriched_prompt = append_organization_context(runtime_config.system_prompt.strip())
    enriched_prompt += (
        f"\n\nStudent profile context:\n"
        f"- Name: {lead.full_name or student_name}\n"
        f"- Location: {getattr(lead, 'current_location', None) or 'unknown'}\n"
        f"- Target country: {lead.preferred_country or 'unknown'}\n"
        f"- Test scores: {lead.test_scores or 'unknown'}\n"
    )
    if extra_context.strip():
        enriched_prompt += f"\n{extra_context.strip()}\n"
    enriched_prompt += JSON_RESPONSE_DIRECTIVE

    messages: list[dict[str, str]] = [{"role": "system", "content": enriched_prompt}]
    for role, text in history:
        messages.append({"role": role, "content": input_sanitizer(text)})

    user_parts = [f"Task: {task.strip()}"]
    if incoming_text.strip():
        user_parts.append(f"Student message: {input_sanitizer(incoming_text.strip())}")
    messages.append({"role": "user", "content": "\n".join(user_parts)})

    return await call_agent_llm(
        runtime_config.ai_model,
        messages,
        student_name=student_name,
        has_prior_ai_turns=has_prior_ai_turns,
        latest_user=incoming_text,
    )


async def call_agent_llm(
    model: str,
    messages: list[dict[str, str]],
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
    latest_user: str = "",
) -> LlmResult:
    provider, _ = parse_model_ref(model)
    timeout_seconds = (
        float(settings.OLLAMA_TIMEOUT_SECONDS)
        if provider == "ollama"
        else float(LLM_TIMEOUT_SECONDS)
    )
    try:
        return await call_with_llm_circuit_breaker(
            lambda: _invoke_llm(
                model,
                messages,
                student_name=student_name,
                has_prior_ai_turns=has_prior_ai_turns,
                latest_user=latest_user,
            ),
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        logger.exception("LLM call failed for model=%s.", model)
        return LlmResult(text="", confidence=0.0)


async def _invoke_llm(
    model: str,
    messages: list[dict[str, str]],
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
    latest_user: str = "",
) -> LlmResult:
    _ensure_env_loaded()
    provider, model_id = parse_model_ref(model)
    latest_user = latest_user or next(
        (message["content"] for message in reversed(messages) if message["role"] == "user"),
        "",
    )

    fallback_text = generate_contextual_admissions_reply(
        latest_user,
        student_name=student_name,
        has_prior_ai_turns=has_prior_ai_turns,
    )
    fallback_confidence = 0.55

    if provider == "ollama":
        try:
            return await _invoke_ollama_chat(
                model_id,
                messages,
                fallback_text="",
                fallback_confidence=0.0,
            )
        except Exception:
            logger.exception("LLM call failed for provider=ollama model=%s.", model_id)
            return LlmResult(text="", confidence=0.0)

    if provider == "groq":
        api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    else:
        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")

    if not api_key:
        logger.warning(
            "%s API key is not configured; using contextual admissions replies.",
            provider.title(),
        )
        return LlmResult(text=fallback_text, confidence=fallback_confidence)

    try:
        if provider == "groq":
            return await _invoke_groq_chat(
                api_key,
                model_id,
                messages,
                fallback_text=fallback_text,
                fallback_confidence=fallback_confidence,
            )
        return await _invoke_openai_chat(
            api_key,
            model_id,
            messages,
            fallback_text=fallback_text,
            fallback_confidence=fallback_confidence,
        )
    except Exception:
        logger.exception("LLM call failed for provider=%s model=%s.", provider, model_id)
        return LlmResult(text=fallback_text, confidence=fallback_confidence)


async def _invoke_ollama_chat(
    model_id: str,
    messages: list[dict[str, str]],
    *,
    fallback_text: str,
    fallback_confidence: float,
) -> LlmResult:
    import httpx

    configured_base = settings.OLLAMA_BASE_URL or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    native_base = configured_base.rstrip("/").removesuffix("/v1")
    chat_url = f"{native_base}/api/chat"
    timeout_seconds = float(settings.OLLAMA_TIMEOUT_SECONDS or 120)

    payload = {
        "model": model_id,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.6, "num_predict": 500},
    }

    def _invoke() -> LlmResult:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(chat_url, json=payload)
            response.raise_for_status()
            content = (response.json().get("message") or {}).get("content") or ""
        return _finalize_llm_payload(content, fallback_text, fallback_confidence)

    return await asyncio.to_thread(_invoke)


async def _invoke_openai_chat(
    api_key: str,
    model_id: str,
    messages: list[dict[str, str]],
    *,
    fallback_text: str,
    fallback_confidence: float,
) -> LlmResult:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _invoke() -> LlmResult:
        response = client.chat.completions.create(
            model=model_id or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            max_tokens=500,
            temperature=0.6,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return _finalize_llm_payload(content, fallback_text, fallback_confidence)

    return await asyncio.to_thread(_invoke)


async def _invoke_groq_chat(
    api_key: str,
    model_id: str,
    messages: list[dict[str, str]],
    *,
    fallback_text: str,
    fallback_confidence: float,
) -> LlmResult:
    from groq import Groq

    client = Groq(api_key=api_key)

    def _invoke() -> LlmResult:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=500,
            temperature=0.6,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return _finalize_llm_payload(content, fallback_text, fallback_confidence)

    return await asyncio.to_thread(_invoke)


def _finalize_llm_payload(
    content: str,
    fallback_text: str,
    fallback_confidence: float,
) -> LlmResult:
    parsed = _parse_llm_json_payload(
        content,
        fallback_text=fallback_text,
        fallback_confidence=fallback_confidence,
    )
    filtered = output_filter(parsed.text).strip()
    if filtered:
        return LlmResult(text=filtered, confidence=parsed.confidence)
    return LlmResult(text=fallback_text, confidence=fallback_confidence)


async def _call_llm(
    model: str,
    messages: list[dict[str, str]],
    *,
    student_name: str = "there",
    has_prior_ai_turns: bool = False,
) -> str:
    """Backward-compatible text-only wrapper."""
    latest_user = next(
        (message["content"] for message in reversed(messages) if message["role"] == "user"),
        "",
    )
    result = await call_agent_llm(
        model,
        messages,
        student_name=student_name,
        has_prior_ai_turns=has_prior_ai_turns,
        latest_user=latest_user,
    )
    return result.text


async def compose_handoff_acknowledgement(
    db: Session,
    runtime_config: RuntimeAgentConfig,
    lead: Lead,
    incoming_text: str,
) -> LlmResult:
    del db, runtime_config, incoming_text
    return build_handoff_student_notice(lead)
