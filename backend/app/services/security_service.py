from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException

T = TypeVar("T")

LLM_TIMEOUT_SECONDS = 10

ADVERSARIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*/?\s*(system|assistant|user|instruction|prompt)\s*>", re.I),
    re.compile(r"\[\[?\s*(system|inst|hidden)\s*\]?\]", re.I),
    re.compile(r"(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.I),
    re.compile(r"<\s*script\b", re.I),
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?!\w)"
)


def input_sanitizer(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    for pattern in ADVERSARIAL_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned[:5000]


def output_filter(value: str | None) -> str:
    if not value:
        return ""
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted


async def call_with_llm_circuit_breaker(
    operation: Callable[[], Awaitable[T]],
    *,
    timeout_seconds: float = LLM_TIMEOUT_SECONDS,
) -> T:
    try:
        return await asyncio.wait_for(operation(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"LLM request timed out after {int(timeout_seconds)} seconds.",
        ) from exc


def llm_circuit_breaker(
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        return await call_with_llm_circuit_breaker(lambda: func(*args, **kwargs))

    return wrapper
