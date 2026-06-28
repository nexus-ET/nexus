"""Tests for AI provider model registry."""

from app.services.ai_providers import normalize_model_ref, parse_model_ref


def test_parse_model_ref_with_provider():
    assert parse_model_ref("groq:llama-3.3-70b-versatile") == (
        "groq",
        "llama-3.3-70b-versatile",
    )
    assert parse_model_ref("ollama:llama3.1") == ("ollama", "llama3.1")


def test_parse_model_ref_legacy_openai():
    assert parse_model_ref("gpt-4o-mini") == ("openai", "gpt-4o-mini")


def test_normalize_model_ref():
    assert normalize_model_ref("gpt-4o-mini") == "openai:gpt-4o-mini"
    assert normalize_model_ref("llama3.1") == "openai:llama3.1"
    assert normalize_model_ref("ollama:llama3.1") == "ollama:llama3.1"
