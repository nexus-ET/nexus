"""Tests for Agent Console runtime escalation logic."""

from app.services.agent_runtime import (
    RuntimeAgentConfig,
    confidence_percent,
    should_escalate_before_llm,
    should_escalate_message,
    should_escalate_on_ai_confidence,
)


def _config(**overrides) -> RuntimeAgentConfig:
    defaults = {
        "id": 1,
        "system_prompt": "Test prompt",
        "ai_model": "gpt-4o-mini",
        "escalation_threshold": 70,
        "keywords_trigger": "human,advisor",
        "is_active": True,
        "updated_at": None,
    }
    defaults.update(overrides)
    return RuntimeAgentConfig(**defaults)


def test_confidence_percent_clamps():
    assert confidence_percent(0.85) == 85.0
    assert confidence_percent(1.5) == 100.0
    assert confidence_percent(-0.2) == 0.0
    assert confidence_percent(None) == 0.0


def test_should_escalate_before_llm_keyword_match():
    config = _config()
    assert should_escalate_before_llm("I need a human please", config) is True
    assert should_escalate_before_llm("hello there", config) is False


def test_should_escalate_before_llm_inactive_agent():
    config = _config(is_active=False)
    assert should_escalate_before_llm("hello", config) is True


def test_should_escalate_on_ai_confidence_below_threshold():
    config = _config(escalation_threshold=70)
    assert should_escalate_on_ai_confidence(0.69, config) is True
    assert should_escalate_on_ai_confidence(0.70, config) is False
    assert should_escalate_on_ai_confidence(0.85, config) is False


def test_should_escalate_on_ai_confidence_none_escalates():
    config = _config(escalation_threshold=70)
    assert should_escalate_on_ai_confidence(None, config) is True


def test_should_escalate_message_combined():
    config = _config(escalation_threshold=70)
    assert should_escalate_message("talk to advisor", config, ai_confidence=0.95) is True
    assert should_escalate_message("question about visa", config, ai_confidence=0.50) is True
    assert should_escalate_message("question about visa", config, ai_confidence=0.90) is False
