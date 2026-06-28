from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent_config import AgentConfig

# Seed values used only when creating the first agent_configs row (not per-message fallbacks).
DEFAULT_SYSTEM_PROMPT = (
    "You are Edutrust Admissions AI, the WhatsApp assistant for Edutrust — an education consultancy "
    "that guides students to study at foreign universities. Edutrust is NOT a university itself. "
    "Answer clearly about programs abroad, entry requirements, documents, and visas. "
    "Escalate to a human advisor when the student requests a person or when manual review is required."
)
DEFAULT_AI_MODEL = "ollama:llama3.1"
DEFAULT_ESCALATION_THRESHOLD = 70
DEFAULT_KEYWORDS_TRIGGER = "human,advisor,agent,talk to,person"


@dataclass
class RuntimeAgentConfig:
    id: int
    system_prompt: str
    ai_model: str
    escalation_threshold: int
    keywords_trigger: str
    is_active: bool
    updated_at: Optional[datetime] = None


def _to_runtime(config: AgentConfig) -> RuntimeAgentConfig:
    return RuntimeAgentConfig(
        id=config.id,
        system_prompt=config.system_prompt,
        ai_model=config.ai_model,
        escalation_threshold=config.escalation_threshold,
        keywords_trigger=config.keywords_trigger,
        is_active=config.is_active,
        updated_at=config.updated_at,
    )


def get_or_create_agent_config(db: Session) -> AgentConfig:
    config = db.query(AgentConfig).order_by(AgentConfig.id.asc()).first()
    if config:
        return config

    config = AgentConfig(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        ai_model=DEFAULT_AI_MODEL,
        escalation_threshold=DEFAULT_ESCALATION_THRESHOLD,
        keywords_trigger=DEFAULT_KEYWORDS_TRIGGER,
        is_active=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_runtime_agent_config(db: Session) -> RuntimeAgentConfig:
    """Load the latest Agent Console configuration from the database (no process cache)."""
    config = get_or_create_agent_config(db)
    return _to_runtime(config)


def update_agent_config(db: Session, payload: dict) -> AgentConfig:
    config = get_or_create_agent_config(db)
    for field, value in payload.items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config


def parse_trigger_keywords(keywords_trigger: str) -> list[str]:
    return [word.strip().lower() for word in keywords_trigger.split(",") if word.strip()]


def should_escalate_before_llm(message: str, config: RuntimeAgentConfig) -> bool:
    """Pre-LLM intercept: inactive agent or keyword triggers only."""
    if not config.is_active:
        return True

    normalized = (message or "").lower()
    keywords = parse_trigger_keywords(config.keywords_trigger)
    return any(keyword in normalized for keyword in keywords)


def confidence_percent(ai_confidence: float | None) -> float:
    if ai_confidence is None:
        return 0.0
    return max(0.0, min(100.0, float(ai_confidence) * 100.0))


def should_escalate_on_ai_confidence(
    ai_confidence: float | None,
    config: RuntimeAgentConfig,
) -> bool:
    """
    Post-LLM check: escalate when model confidence is below escalation_threshold (0–100).

    escalation_threshold is an AI reliability floor, not a lead conversion score.
    """
    if not config.is_active:
        return True
    if ai_confidence is None:
        return True
    return confidence_percent(ai_confidence) < float(config.escalation_threshold)


def should_escalate_message(
    message: str,
    config: RuntimeAgentConfig,
    ai_confidence: float | None = None,
) -> bool:
    """Combined helper for callers that need pre- and post-LLM escalation in one call."""
    if should_escalate_before_llm(message, config):
        return True
    return should_escalate_on_ai_confidence(ai_confidence, config)
