from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent_config import AgentConfig


DEFAULT_SYSTEM_PROMPT = (
    "You are Nexus Admissions AI, a helpful and professional university admissions assistant. "
    "Answer clearly, qualify student intent, and escalate to a human advisor when the student "
    "requests a person or when the situation requires manual review."
)
DEFAULT_AI_MODEL = "gpt-4o-mini"
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


_runtime_cache: RuntimeAgentConfig | None = None


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
    refresh_runtime_config(config)
    return config


def refresh_runtime_config(config: AgentConfig) -> RuntimeAgentConfig:
    global _runtime_cache
    _runtime_cache = _to_runtime(config)
    return _runtime_cache


def get_runtime_agent_config(db: Session | None = None) -> RuntimeAgentConfig:
    global _runtime_cache
    if _runtime_cache is not None:
        return _runtime_cache

    if db is None:
        return RuntimeAgentConfig(
            id=0,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            ai_model=DEFAULT_AI_MODEL,
            escalation_threshold=DEFAULT_ESCALATION_THRESHOLD,
            keywords_trigger=DEFAULT_KEYWORDS_TRIGGER,
            is_active=True,
        )

    config = get_or_create_agent_config(db)
    return refresh_runtime_config(config)


def update_agent_config(db: Session, payload: dict) -> AgentConfig:
    config = get_or_create_agent_config(db)
    for field, value in payload.items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    refresh_runtime_config(config)
    return config


def parse_trigger_keywords(keywords_trigger: str) -> list[str]:
    return [word.strip().lower() for word in keywords_trigger.split(",") if word.strip()]


def should_escalate_message(message: str, config: RuntimeAgentConfig, ml_score: float = 0.0) -> bool:
    if not config.is_active:
        return True

    normalized = (message or "").lower()
    keywords = parse_trigger_keywords(config.keywords_trigger)
    if any(keyword in normalized for keyword in keywords):
        return True

    if ml_score >= config.escalation_threshold:
        return True

    return False
