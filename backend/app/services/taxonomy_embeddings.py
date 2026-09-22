"""Embed education taxonomy names + descriptions into dedicated tables.

Create/update CRUD calls ``schedule_*_embedding`` after a successful commit.
Failures are logged and never raised to the caller so taxonomy saves stay available
when the embedding API is down; re-run ``scripts/_backfill_taxonomy_embeddings.py``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from html import unescape
from typing import Literal

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.education_super_major import EducationSuperMajor
from app.models.education_taxonomy_embedding import (
    EducationMajorEmbedding,
    EducationSubMajorEmbedding,
    EducationSuperMajorEmbedding,
)

logger = logging.getLogger(__name__)

EntityKind = Literal["super_major", "major", "sub_major"]

_HTML_TAG_RE = re.compile(r"<[^>]*>")


class EmbeddingUnavailableError(RuntimeError):
    """Raised when no embedding provider can produce a vector."""


def plain_text(value: str | None) -> str:
    """Strip TipTap/HTML markup down to counselor-facing plain text."""
    if not value:
        return ""
    text = unescape(_HTML_TAG_RE.sub(" ", value))
    return " ".join(text.split()).strip()


def build_taxonomy_source_text(*, name: str, description: str | None) -> str:
    name_clean = (name or "").strip()
    desc_clean = plain_text(description)
    if desc_clean:
        return f"Name: {name_clean}\nDescription: {desc_clean}"
    return f"Name: {name_clean}"


def source_text_hash(source_text: str, *, model: str) -> str:
    payload = f"{model}\n{source_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolved_provider() -> str:
    provider = (settings.EMBEDDING_PROVIDER or "openai").strip().lower()
    if provider == "openai" and not (settings.OPENAI_API_KEY or "").strip():
        # Prefer Ollama when OpenAI is selected but unconfigured.
        return "ollama"
    return provider


def _model_and_expected_dim() -> tuple[str, int]:
    provider = _resolved_provider()
    if provider == "ollama":
        return (
            settings.OLLAMA_EMBEDDING_MODEL,
            int(settings.OLLAMA_EMBEDDING_DIMENSIONS),
        )
    return (
        settings.OPENAI_EMBEDDING_MODEL,
        int(settings.OPENAI_EMBEDDING_DIMENSIONS),
    )


def embed_taxonomy_text(name: str, description: str | None = None) -> tuple[list[float], str, str]:
    """Convert name + description → embedding vector.

    Returns ``(vector, model_name, source_text_hash)``.
    """
    source = build_taxonomy_source_text(name=name, description=description)
    if not source.strip() or source.strip() == "Name:":
        raise EmbeddingUnavailableError("Cannot embed empty taxonomy text.")

    model, expected_dim = _model_and_expected_dim()
    provider = _resolved_provider()
    if provider == "ollama":
        vector = _embed_ollama(source, model=model)
    else:
        vector = _embed_openai(source, model=model, dimensions=expected_dim)

    if not vector:
        raise EmbeddingUnavailableError("Embedding provider returned an empty vector.")
    if expected_dim and len(vector) != expected_dim:
        logger.warning(
            "Embedding dimension mismatch for model=%s expected=%s got=%s",
            model,
            expected_dim,
            len(vector),
        )
    return vector, model, source_text_hash(source, model=model)


def _embed_openai(text: str, *, model: str, dimensions: int) -> list[float]:
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise EmbeddingUnavailableError(
            "OPENAI_API_KEY is not configured for taxonomy embeddings."
        )
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    kwargs: dict = {"model": model, "input": text}
    # text-embedding-3-* supports dimensions; older models ignore/reject it.
    if model.startswith("text-embedding-3") and dimensions > 0:
        kwargs["dimensions"] = dimensions
    response = client.embeddings.create(**kwargs)
    return list(response.data[0].embedding)


def _embed_ollama(
    text: str, *, model: str, timeout_seconds: float | None = None
) -> list[float]:
    """Call Ollama native embed API (not the OpenAI-compat /v1 path)."""
    base = (settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434/v1").rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    url = f"{base}/api/embed"
    timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else (settings.OLLAMA_TIMEOUT_SECONDS or 120)
    )
    try:
        response = httpx.post(
            url,
            json={"model": model, "input": text},
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — surface as unavailable for callers
        raise EmbeddingUnavailableError(
            f"Ollama embed failed ({model}): {exc}"
        ) from exc

    payload = response.json()
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        if isinstance(first, list) and first:
            return [float(x) for x in first]
    # Legacy single-vector shape
    single = payload.get("embedding")
    if isinstance(single, list) and single:
        return [float(x) for x in single]
    raise EmbeddingUnavailableError(
        f"Ollama returned no embeddings for model={model!r}. "
        "Pull an embedding model (e.g. `ollama pull nomic-embed-text`)."
    )


def upsert_super_major_embedding(db: Session, record: EducationSuperMajor) -> bool:
    vector, model, text_hash = embed_taxonomy_text(record.name, record.description)
    return _upsert_row(
        db,
        model_cls=EducationSuperMajorEmbedding,
        fk_attr="super_major_id",
        entity_id=record.id,
        vector=vector,
        model=model,
        text_hash=text_hash,
    )


def upsert_major_embedding(db: Session, record: EducationMajor) -> bool:
    vector, model, text_hash = embed_taxonomy_text(
        record.label, record.major_description
    )
    return _upsert_row(
        db,
        model_cls=EducationMajorEmbedding,
        fk_attr="major_id",
        entity_id=record.id,
        vector=vector,
        model=model,
        text_hash=text_hash,
    )


def upsert_sub_major_embedding(db: Session, record: EducationSubMajor) -> bool:
    vector, model, text_hash = embed_taxonomy_text(
        record.name, record.sub_major_description
    )
    return _upsert_row(
        db,
        model_cls=EducationSubMajorEmbedding,
        fk_attr="sub_major_id",
        entity_id=record.id,
        vector=vector,
        model=model,
        text_hash=text_hash,
    )


def _upsert_row(
    db: Session,
    *,
    model_cls: type,
    fk_attr: str,
    entity_id: int,
    vector: list[float],
    model: str,
    text_hash: str,
) -> bool:
    """Insert or update embedding. Returns False when hash unchanged (skipped)."""
    existing = (
        db.query(model_cls)
        .filter(getattr(model_cls, fk_attr) == entity_id)
        .first()
    )
    if (
        existing
        and existing.source_text_hash == text_hash
        and existing.embedding_model == model
        and existing.embedding_dimensions == len(vector)
    ):
        return False

    if existing:
        existing.embedding = vector
        existing.embedding_dimensions = len(vector)
        existing.embedding_model = model
        existing.source_text_hash = text_hash
    else:
        row = model_cls(
            **{
                fk_attr: entity_id,
                "embedding": vector,
                "embedding_dimensions": len(vector),
                "embedding_model": model,
                "source_text_hash": text_hash,
            }
        )
        db.add(row)
    db.commit()
    return True


def _with_fresh_session(fn, entity_id: int) -> None:
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        fn(db, entity_id)
    finally:
        db.close()


def _embed_super_major_by_id(db: Session, super_major_id: int) -> None:
    record = (
        db.query(EducationSuperMajor)
        .filter(EducationSuperMajor.id == super_major_id)
        .first()
    )
    if not record:
        return
    upsert_super_major_embedding(db, record)


def _embed_major_by_id(db: Session, major_id: int) -> None:
    record = db.query(EducationMajor).filter(EducationMajor.id == major_id).first()
    if not record:
        return
    upsert_major_embedding(db, record)


def _embed_sub_major_by_id(db: Session, sub_major_id: int) -> None:
    record = (
        db.query(EducationSubMajor)
        .filter(EducationSubMajor.id == sub_major_id)
        .first()
    )
    if not record:
        return
    upsert_sub_major_embedding(db, record)


def schedule_super_major_embedding(super_major_id: int) -> None:
    """Best-effort embed after create/update. Never raises to CRUD callers."""
    if not settings.TAXONOMY_EMBEDDINGS_ENABLED:
        return
    try:
        _with_fresh_session(_embed_super_major_by_id, super_major_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Taxonomy embedding failed for super-major id=%s", super_major_id
        )


def schedule_major_embedding(major_id: int) -> None:
    if not settings.TAXONOMY_EMBEDDINGS_ENABLED:
        return
    try:
        _with_fresh_session(_embed_major_by_id, major_id)
    except Exception:  # noqa: BLE001
        logger.exception("Taxonomy embedding failed for major id=%s", major_id)


def schedule_sub_major_embedding(sub_major_id: int) -> None:
    if not settings.TAXONOMY_EMBEDDINGS_ENABLED:
        return
    try:
        _with_fresh_session(_embed_sub_major_by_id, sub_major_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Taxonomy embedding failed for sub-major id=%s", sub_major_id
        )
