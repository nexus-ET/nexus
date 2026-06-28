from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiModelOption:
    value: str
    label: str
    provider: str
    model_id: str
    description: str = ""


AI_MODEL_OPTIONS: list[AiModelOption] = [
    AiModelOption(
        "ollama:llama3.1",
        "Ollama — Llama 3.1 (local)",
        "ollama",
        "llama3.1",
        "Local inference via Ollama. No cloud API key required.",
    ),
    AiModelOption(
        "ollama:llama3.2",
        "Ollama — Llama 3.2 (local)",
        "ollama",
        "llama3.2",
        "Newer local Llama variant when pulled in Ollama.",
    ),
    AiModelOption(
        "openai:gpt-4o-mini",
        "OpenAI — GPT-4o Mini",
        "openai",
        "gpt-4o-mini",
        "Fast and cost-effective general admissions Q&A.",
    ),
    AiModelOption(
        "openai:gpt-4o",
        "OpenAI — GPT-4o",
        "openai",
        "gpt-4o",
        "Higher-quality reasoning for complex student cases.",
    ),
    AiModelOption(
        "groq:llama-3.3-70b-versatile",
        "Groq — Llama 3.3 70B",
        "groq",
        "llama-3.3-70b-versatile",
        "Low-latency Groq cloud inference.",
    ),
    AiModelOption(
        "groq:llama-3.1-8b-instant",
        "Groq — Llama 3.1 8B Instant",
        "groq",
        "llama-3.1-8b-instant",
        "Fastest Groq option for lightweight intake replies.",
    ),
]

_VALID_VALUES = {option.value for option in AI_MODEL_OPTIONS}


def list_ai_model_options() -> list[dict[str, str]]:
    return [
        {
            "value": option.value,
            "label": option.label,
            "provider": option.provider,
            "model_id": option.model_id,
            "description": option.description,
        }
        for option in AI_MODEL_OPTIONS
    ]


def parse_model_ref(ai_model: str) -> tuple[str, str]:
    cleaned = (ai_model or "").strip()
    if ":" in cleaned:
        provider, model_id = cleaned.split(":", 1)
        return provider.lower().strip(), model_id.strip()
    return "openai", cleaned or "gpt-4o-mini"


def normalize_model_ref(ai_model: str) -> str:
    provider, model_id = parse_model_ref(ai_model)
    return f"{provider}:{model_id}"


def is_supported_model_ref(ai_model: str) -> bool:
    normalized = normalize_model_ref(ai_model)
    return normalized in _VALID_VALUES
