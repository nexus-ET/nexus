"""Cooperative ScanX job cancel — abort in-flight work and hard-delete artifacts.

Exact byte/page resume is not supported (no OCR checkpoints). Cancel therefore
stops the worker as soon as it next checks the flag and removes the document
row, extracted fields, chunks, group pages, and stored files.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from dataclasses import dataclass
from typing import Any

from app.constants.scanx import STATUS_PARSING, STATUS_UPLOADING

logger = logging.getLogger(__name__)

_CANCELABLE_STATUSES = frozenset({STATUS_UPLOADING, STATUS_PARSING})

_lock = threading.Lock()
_events: dict[int, threading.Event] = {}
_current = threading.local()
_current_doc: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "scanx_job_document_id",
    default=None,
)


class ScanxJobCancelled(Exception):
    """Cooperative abort — not a pipeline failure."""


@dataclass(frozen=True)
class ScanxCancelResult:
    ok: bool = True
    document_id: int = 0
    cancelled: bool = True
    already_gone: bool = False
    storage_removed: bool = False


def bind_job(document_id: int) -> None:
    """Remember the active document on this thread and copied executor contexts.

    Preserves any queue/slot wait_ms already recorded on this thread (e.g. parse
    slot wait in ``_start_thread`` before ``process_scanx_document`` runs).
    """
    doc_id = int(document_id)
    prior_wait = getattr(_current, "wait_ms", 0) or 0
    _current.document_id = doc_id
    try:
        _current.wait_ms = max(0, int(prior_wait))
    except (TypeError, ValueError):
        _current.wait_ms = 0
    _current_doc.set(doc_id)


def unbind_job() -> None:
    _current.document_id = None
    _current.wait_ms = 0
    _current_doc.set(None)


def add_job_wait_ms(ms: int) -> None:
    """Accumulate queue / slot wait so leave_parsing_ms can exclude it."""
    try:
        delta = max(0, int(ms))
    except (TypeError, ValueError):
        return
    if delta <= 0:
        return
    cur = getattr(_current, "wait_ms", 0) or 0
    try:
        _current.wait_ms = int(cur) + delta
    except (TypeError, ValueError):
        _current.wait_ms = delta


def take_job_wait_ms() -> int:
    """Return and clear accumulated wait milliseconds for this job thread."""
    raw = getattr(_current, "wait_ms", 0) or 0
    _current.wait_ms = 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def current_job_document_id() -> int | None:
    ctx = _current_doc.get()
    if ctx:
        try:
            return int(ctx)
        except (TypeError, ValueError):
            pass
    raw = getattr(_current, "document_id", None)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def request_cancel(document_id: int) -> None:
    doc_id = int(document_id)
    with _lock:
        event = _events.setdefault(doc_id, threading.Event())
        event.set()


def clear_cancel(document_id: int) -> None:
    with _lock:
        _events.pop(int(document_id), None)


def is_cancel_requested(document_id: int | None = None) -> bool:
    doc_id = int(document_id) if document_id is not None else current_job_document_id()
    if not doc_id:
        return False
    with _lock:
        event = _events.get(int(doc_id))
        return bool(event and event.is_set())


def raise_if_cancelled(document_id: int | None = None) -> None:
    if is_cancel_requested(document_id):
        raise ScanxJobCancelled()


def cancel_scanx_document(db: Any, document_id: int) -> ScanxCancelResult:
    """Abort a running job (if any) and hard-delete the document + stored files.

    Missing ids are success (idempotent). Rows that already left Uploading/Parsing
    are left in place unless a prior cancel flag is still set (retry cleanup).
    """
    from app.models.scanx import ScanxDocument
    from app.services.scanx_queue import cancel_scanx_rq_job
    from app.services.scanx_storage import (
        collect_scanx_document_storage_keys,
        delete_scanx_objects,
    )

    try:
        doc_id = int(document_id)
    except (TypeError, ValueError):
        return ScanxCancelResult(ok=True, document_id=0, cancelled=True, already_gone=True)
    if doc_id < 1:
        return ScanxCancelResult(ok=True, document_id=doc_id, cancelled=True, already_gone=True)

    doc = db.query(ScanxDocument).filter(ScanxDocument.id == doc_id).first()
    if not doc:
        clear_cancel(doc_id)
        return ScanxCancelResult(
            ok=True,
            document_id=doc_id,
            cancelled=True,
            already_gone=True,
        )

    metrics = dict(doc.metrics_json or {}) if isinstance(doc.metrics_json, dict) else {}
    in_progress = str(doc.status or "") in _CANCELABLE_STATUSES
    already_flagged = bool(metrics.get("cancel_requested"))
    if not in_progress and not already_flagged:
        return ScanxCancelResult(
            ok=True,
            document_id=doc_id,
            cancelled=False,
            already_gone=False,
        )

    rows = [doc]
    group_id = getattr(doc, "document_group_id", None)
    if group_id is not None:
        siblings = (
            db.query(ScanxDocument)
            .filter(ScanxDocument.document_group_id == group_id)
            .all()
        )
        if siblings:
            rows = list(siblings)

    storage_keys: list[str] = []
    job_ids: list[str] = []
    row_ids: list[int] = []
    for row in rows:
        rid = int(row.id)
        row_ids.append(rid)
        request_cancel(rid)
        storage_keys.extend(collect_scanx_document_storage_keys(row))
        row_metrics = dict(row.metrics_json or {}) if isinstance(row.metrics_json, dict) else {}
        row_metrics["cancel_requested"] = True
        row.metrics_json = row_metrics
        raw_job = row_metrics.get("job_id")
        if raw_job:
            job_ids.append(str(raw_job))
    db.commit()

    for raw_job in job_ids:
        if raw_job.startswith("thread-") or raw_job.startswith("pending-"):
            continue
        cancel_scanx_rq_job(raw_job)

    storage_removed = delete_scanx_objects(storage_keys) if storage_keys else 0

    # Re-load so this session does not delete stale instances after the flag commit.
    fresh = (
        db.query(ScanxDocument)
        .filter(ScanxDocument.id.in_(row_ids))
        .all()
        if row_ids
        else []
    )
    for row in fresh:
        db.delete(row)
    if fresh:
        db.commit()

    for rid in row_ids:
        clear_cancel(rid)

    logger.info(
        "ScanX cancelled document_id=%s rows=%s storage_removed=%s keys=%s",
        doc_id,
        [int(r.id) for r in fresh],
        storage_removed,
        len(storage_keys),
    )
    return ScanxCancelResult(
        ok=True,
        document_id=doc_id,
        cancelled=True,
        already_gone=False,
        storage_removed=storage_removed > 0 or not storage_keys,
    )
