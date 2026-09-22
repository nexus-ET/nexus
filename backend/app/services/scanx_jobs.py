"""RQ job: parse / extract / embed a ScanX document and update status."""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.constants.scanx import (
    DOCX_MIME_TYPE,
    STATUS_ACTION_REQUIRED,
    STATUS_PARSING,
    STATUS_RED_FLAG,
)
from sqlalchemy.exc import DBAPIError, OperationalError

from app.db.database import (
    SessionLocal,
    dispose_db_pool,
    ensure_db_connection,
    is_db_pool_pressure_error,
    open_scanx_session,
    recover_ssh_tunnel,
    safe_close_session,
    should_dispose_pool_for_error,
)
from app.models.scanx import ScanxDocument, ScanxDocumentChunk
from app.models.lead import Lead  # noqa: F401 — ScanxDocument.lead_id FK metadata
from app.services.exception_log_service import record_exception_event_isolated
from app.services.scanx_embeddings import (
    chunk_text,
    embed_chunks_best_effort,
    normalize_extracted_display,
    normalize_native_document_text,
    normalize_utf8_text,
)
from app.services.scanx_progress import (
    STEP_STATUS_COMPLETE,
    STEP_STATUS_FAILED,
    STEP_STATUS_IN_PROGRESS,
    STEP_STATUS_SKIPPED,
    apply_progress_to_metrics,
    compute_progress_percent,
    initial_progress_steps,
    set_step,
)
from app.services.scanx_cancel import (
    ScanxJobCancelled,
    bind_job,
    is_cancel_requested,
    raise_if_cancelled,
    request_cancel,
    unbind_job,
)
from app.services.scanx_academic_parse import (
    attach_marks_schema,
    format_subject_item,
    looks_like_marksheet,
    marks_row_to_subject,
    merge_subjects,
    quality_subjects,
    resolve_subjects_from_text,
)
from app.services.scanx_ocr import extract_text_from_image, ocr_budget_seconds
from app.services.scanx_ocr_blocks import blocks_to_json, summarize_blocks
from app.services.scanx_categorize import categorize_document_fields
from app.services.scanx_document_classify import classify_scanx_document
from app.services.scanx_image_enhance import (
    dpi_metrics_without_enhance,
    encode_preview_jpeg,
    enhance_image_batch,
)
from app.services.scanx_storage import (
    collect_enhanced_preview_keys,
    collect_scanx_original_archive_keys,
    delete_scanx_objects,
    fetch_scanx_bytes,
    schedule_archive_scanx_keys,
)
from app.services.scanx_validation import (
    extract_docx_embedded_images,
    extract_docx_text,
    extract_pdf_embedded_images,
    extract_pdf_text,
    inspect_docx,
    looks_like_docx,
    looks_like_pdf,
    max_pages,
    pdf_embedded_images_usable_for_ocr,
    pdf_has_scan_app_stamp,
    pdf_page_count,
    pick_largest_content_image,
    is_scan_watermark_banner,
    render_pdf_pages_as_png,
    select_images_for_ocr,
)

logger = logging.getLogger(__name__)


def _emit_status(doc: ScanxDocument) -> None:
    """Best-effort WebSocket notify (sync context)."""
    try:
        import asyncio

        from app.services.scanx_progress import progress_fields_from_metrics
        from app.services.websocket_service import broadcast_nexus_event

        # Snapshot eagerly — detached/expired instances must not lazy-refresh.
        try:
            metrics_raw = doc.metrics_json
            metrics = metrics_raw if isinstance(metrics_raw, dict) else {}
            payload = {
                "doc_id": int(doc.id),
                "doc_uuid": str(doc.doc_uuid),
                "lead_id": doc.lead_id,
                "status": doc.status,
                "original_filename": doc.original_filename,
                "error_code": doc.error_code,
            }
        except Exception:
            logger.debug("ScanX WS emit skipped (detached doc)", exc_info=True)
            return
        progress = progress_fields_from_metrics(metrics)
        payload.update(
            {
                "progress_percent": progress.get("progress_percent"),
                "current_step_id": progress.get("current_step_id"),
                "current_step_label": progress.get("current_step_label"),
                "progress_steps": progress.get("progress_steps"),
            }
        )

        async def _run() -> None:
            await broadcast_nexus_event("scanx.document.status", payload)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_run())
        else:
            loop.create_task(_run())
    except Exception:
        logger.debug("ScanX WS emit skipped", exc_info=True)


def _is_pdf(doc: ScanxDocument) -> bool:
    ctype = (doc.content_type or "").lower()
    name = (doc.original_filename or "").lower()
    return ctype.startswith("application/pdf") or name.endswith(".pdf")


def _is_docx(doc: ScanxDocument) -> bool:
    ctype = (doc.content_type or "").lower()
    name = (doc.original_filename or "").lower()
    return ctype == DOCX_MIME_TYPE or name.endswith(".docx")


def _is_image(doc: ScanxDocument) -> bool:
    ctype = (doc.content_type or "").lower()
    name = (doc.original_filename or "").lower()
    if ctype.startswith("image/"):
        return True
    return name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff"))


def _source_pages_meta(doc: ScanxDocument) -> list[dict[str, Any]]:
    """Ordered source page entries from column or metrics fallback."""
    pages = doc.source_pages if isinstance(doc.source_pages, list) else None
    if not pages:
        metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
        raw = metrics.get("source_pages") if isinstance(metrics, dict) else None
        pages = raw if isinstance(raw, list) else None
    out: list[dict[str, Any]] = []
    for entry in pages or []:
        if isinstance(entry, dict) and entry.get("r2_key"):
            out.append(entry)
    out.sort(key=lambda e: int(e.get("page_index") or 0))
    return out


def _load_source_page_images(
    doc: ScanxDocument,
    *,
    fallback_content: bytes | None = None,
) -> list[bytes]:
    """Fetch ordered page image bytes for a multi-image document group."""
    pages = _source_pages_meta(doc)
    images: list[bytes] = []
    for entry in pages:
        key = str(entry.get("r2_key") or "").strip()
        if not key:
            continue
        try:
            blob, _ctype = fetch_scanx_bytes(key)
        except Exception:
            logger.exception(
                "ScanX failed to load source page key=%s doc_id=%s",
                key,
                getattr(doc, "id", None),
            )
            continue
        if blob:
            images.append(blob)
    if not images and fallback_content:
        images = [fallback_content]
    elif not images and doc.r2_key:
        try:
            blob, _ = fetch_scanx_bytes(doc.r2_key)
            if blob:
                images = [blob]
        except Exception:
            pass
    return images


def _ensure_steps(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    steps = metrics.get("progress_steps")
    if isinstance(steps, list) and steps:
        # Reconcile older uploads missing classify/enhance with current STEP_DEFS.
        from app.services.scanx_progress import STEP_DEFS, STEP_STATUS_LABELS, STEP_STATUS_PENDING

        by_id = {str(s.get("id")): s for s in steps if isinstance(s, dict)}
        if all(d["id"] in by_id for d in STEP_DEFS):
            return list(steps)
        merged: list[dict[str, Any]] = []
        for defn in STEP_DEFS:
            sid = defn["id"]
            if sid in by_id:
                row = dict(by_id[sid])
                row["weight"] = defn["weight"]
                row["label"] = row.get("label") or defn["label"]
                merged.append(row)
            else:
                merged.append(
                    {
                        "id": sid,
                        "label": defn["label"],
                        "weight": defn["weight"],
                        "status": STEP_STATUS_PENDING,
                        "status_label": STEP_STATUS_LABELS[STEP_STATUS_PENDING],
                        "note": None,
                        "started_at": None,
                        "finished_at": None,
                    }
                )
        return merged
    return initial_progress_steps(waiting_for_worker=False, validate_done=True)


def _is_db_connectivity_error(exc: BaseException) -> bool:
    if is_db_pool_pressure_error(exc):
        return True
    name = type(exc).__name__
    msg = str(exc).lower()
    if isinstance(exc, (OperationalError, DBAPIError, TimeoutError)):
        return True
    return any(
        token in name.lower() or token in msg
        for token in (
            "connectiontimeout",
            "connection timeout",
            "operationalerror",
            "server closed",
            "connection refused",
            "ssl connection",
            "queuepool",
            "pendingrollback",
            "invalid transaction",
            "detachedinstance",
            "tunnel connect gate busy",
            "scanx db slot timeout",
            "adminshutdown",
            "administrator command",
            "terminating connection",
            "the connection is closed",
            "connection is lost",
        )
    )


def _heal_job_session_after_progress_blip(db: Any) -> None:
    """Clear a poisoned job session without disposing the shared pool.

    Prefer invalidate so the next checkout replaces the AdminShutdown'd socket
    instead of reusing a dead connection on the caller's Session.
    """
    try:
        db.rollback()
    except Exception:
        pass
    try:
        db.invalidate()
    except Exception:
        try:
            db.expire_all()
        except Exception:
            pass


# Columns that must survive AdminShutdown retries (metrics-only side writes used
# to drop in-memory passport extracted_fields_json after session heal).
_SCANX_RETRY_COLUMNS = (
    "extracted_fields_json",
    "extracted_text",
    "document_type_id",
    "subfolder",
    "page_count",
    "status",
    "error_code",
    "error_message",
)


def _snapshot_scanx_row_state(doc: Any) -> dict[str, Any]:
    """Capture pending column values without triggering a DB refresh."""
    raw = getattr(doc, "__dict__", {}) or {}
    out: dict[str, Any] = {}
    for key in _SCANX_RETRY_COLUMNS:
        if key in raw:
            out[key] = raw[key]
    return out


def _apply_scanx_row_state(target: Any, state: dict[str, Any]) -> None:
    for key, value in state.items():
        try:
            setattr(target, key, value)
        except Exception:
            pass


def document_looks_like_passport(
    *,
    document_type_id: str | None,
    original_filename: str | None,
    extracted_text: str | None,
) -> bool:
    """True when type, filename, or OCR clearly indicate a passport."""
    type_id = str(document_type_id or "").strip().upper()
    if type_id == "PASSPORT":
        return True
    fname = str(original_filename or "").upper()
    if "PASSPORT" in fname or "PASSEPORT" in fname:
        return True
    text = extracted_text or ""
    if re.search(r"\bP<[A-Z<]{3}", text):
        return True
    if re.search(r"REPUBLIC\s+OF\s+INDIA", text, re.I) and re.search(
        r"(?:passport\s*no|type\s*/?\s*country|given\s*name|surname|\bmrz\b)",
        text,
        re.I,
    ):
        return True
    return False


def _persist_progress(
    db: Any,
    doc: ScanxDocument,
    metrics: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    emit: bool = True,
) -> dict[str, Any]:
    """Best-effort metrics/progress commit — never fail the document alone.

    AdminShutdown / tunnel flaps on the UPDATE must not mark the file failed.
    Retries use a fresh ScanX session after the first attempt; we never call
    ``dispose_db_pool`` here (that used to abort in-flight work via pool wipe).

    Side-session retries also re-write extracted_fields_json and related columns
    so a metrics flap after passport OCR cannot leave Personal Info empty.
    """
    doc_id = int(getattr(doc, "id", 0) or 0)
    raise_if_cancelled(doc_id)
    metrics = apply_progress_to_metrics(metrics, steps)
    doc.metrics_json = metrics
    row_state = _snapshot_scanx_row_state(doc)
    last_exc: BaseException | None = None
    for attempt in range(4):
        if attempt:
            time.sleep(min(0.35 * attempt, 1.5))
            _apply_scanx_row_state(doc, row_state)
            doc.metrics_json = metrics
        try:
            raise_if_cancelled(doc_id)
            if attempt == 0:
                target = doc
                db.commit()
                db.refresh(target)
                try:
                    doc.metrics_json = target.metrics_json
                except Exception:
                    pass
                if emit:
                    _emit_status(target)
                return metrics

            # Retries: write via a short-lived session so a dead job connection
            # (AdminShutdown / closed socket) cannot block OCR continuation.
            if not doc_id:
                raise last_exc or RuntimeError("ScanX progress retry without doc_id")
            side: Any = None
            try:
                side = open_scanx_session(timeout=8.0)
                rebound = (
                    side.query(ScanxDocument)
                    .filter(ScanxDocument.id == doc_id)
                    .first()
                )
                if rebound is None:
                    request_cancel(doc_id)
                    raise ScanxJobCancelled()
                rebound.metrics_json = metrics
                _apply_scanx_row_state(rebound, row_state)
                side.commit()
                try:
                    doc.metrics_json = rebound.metrics_json
                except Exception:
                    pass
                _apply_scanx_row_state(doc, row_state)
                if emit:
                    _emit_status(rebound)
                _heal_job_session_after_progress_blip(db)
                _apply_scanx_row_state(doc, row_state)
                doc.metrics_json = metrics
                return metrics
            finally:
                if side is not None:
                    safe_close_session(side)
        except ScanxJobCancelled:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "ScanX progress commit failed doc_id=%s attempt=%s: %s",
                doc_id or getattr(doc, "id", None),
                attempt + 1,
                exc,
            )
            _heal_job_session_after_progress_blip(db)
            _apply_scanx_row_state(doc, row_state)
            doc.metrics_json = metrics
            if _is_db_connectivity_error(exc):
                # Do not dispose the shared pool from metrics/progress writes —
                # dispose aborts other checked-out ScanX / API connections.
                continue
            raise
    logger.warning(
        "ScanX progress persist exhausted retries doc_id=%s; "
        "continuing with in-memory metrics (%s)",
        doc_id or getattr(doc, "id", None),
        last_exc,
    )
    _apply_scanx_row_state(doc, row_state)
    doc.metrics_json = metrics
    return metrics


def commit_scanx_document_with_retry(
    db: Any,
    doc: ScanxDocument,
    *,
    attempts: int = 4,
    emit: bool = False,
    heal_caller: bool = True,
) -> bool:
    """Commit document row with retry on AdminShutdown / closed connection.

    Returns True when a commit succeeded. On soft failure keeps in-memory state
    on ``doc`` so Review can still backfill from extracted text.

    Set ``heal_caller=False`` for FastAPI request sessions so a side-session
    retry does not invalidate the caller's connection mid-response.
    """
    doc_id = int(getattr(doc, "id", 0) or 0)
    metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
    row_state = _snapshot_scanx_row_state(doc)
    last_exc: BaseException | None = None
    for attempt in range(max(1, attempts)):
        if attempt:
            time.sleep(min(0.35 * attempt, 1.5))
            _apply_scanx_row_state(doc, row_state)
            if isinstance(metrics, dict):
                doc.metrics_json = metrics
        try:
            if attempt == 0:
                db.commit()
                try:
                    db.refresh(doc)
                except Exception:
                    pass
                if emit:
                    _emit_status(doc)
                return True
            if not doc_id:
                raise last_exc or RuntimeError("ScanX commit retry without doc_id")
            side: Any = None
            try:
                side = open_scanx_session(timeout=8.0)
                rebound = (
                    side.query(ScanxDocument)
                    .filter(ScanxDocument.id == doc_id)
                    .first()
                )
                if rebound is None:
                    return False
                if isinstance(metrics, dict):
                    rebound.metrics_json = metrics
                _apply_scanx_row_state(rebound, row_state)
                side.commit()
                _apply_scanx_row_state(doc, row_state)
                if isinstance(metrics, dict):
                    doc.metrics_json = metrics
                if emit:
                    _emit_status(rebound)
                if heal_caller:
                    _heal_job_session_after_progress_blip(db)
                    _apply_scanx_row_state(doc, row_state)
                else:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                return True
            finally:
                if side is not None:
                    safe_close_session(side)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "ScanX document commit failed doc_id=%s attempt=%s: %s",
                doc_id or getattr(doc, "id", None),
                attempt + 1,
                exc,
            )
            if heal_caller:
                _heal_job_session_after_progress_blip(db)
            else:
                try:
                    db.rollback()
                except Exception:
                    pass
            _apply_scanx_row_state(doc, row_state)
            if isinstance(metrics, dict):
                doc.metrics_json = metrics
            if _is_db_connectivity_error(exc):
                continue
            raise
    logger.warning(
        "ScanX document commit exhausted retries doc_id=%s (%s)",
        doc_id or getattr(doc, "id", None),
        last_exc,
    )
    _apply_scanx_row_state(doc, row_state)
    if isinstance(metrics, dict):
        doc.metrics_json = metrics
    return False


def _release_job_db(db: Any) -> None:
    """Commit + close the job session before long CPU/IO so pool slots stay free.

    ScanX OCR / OpenCV enhance / R2 fetch / Ollama LLM+embed can run for tens of
    seconds to minutes. Holding a pooled connection across that work starves
    lightweight API routes (e.g. notifications/inbox → QueuePool TimeoutError).
    """
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    safe_close_session(db)


def _reopen_job_db(document_id: int) -> tuple[Any, ScanxDocument | None]:
    """Open a fresh session after long work; recover the pool if the tunnel flapped.

    Long OCR/IO can idle the SSH tunnel; the first checkout after that often hits
    ConnectionTimeout unless we dispose and retry.

    Slot / connect-gate TimeoutError is retried here (including when raised
    from open_scanx_session itself) so enhance/classify resume waits in line
    instead of failing the document.
    """
    last_exc: BaseException | None = None
    for attempt in range(6):
        if attempt:
            # Pool wait / ScanX slot / connect-gate busy: sleep only. Do not
            # dispose the shared API pool (that 503s /me during OCR resume).
            if last_exc and is_db_pool_pressure_error(last_exc):
                time.sleep(min(1.5 * attempt, 5.0))
            elif last_exc and should_dispose_pool_for_error(last_exc):
                recover_ssh_tunnel(reason=f"scanx resume {type(last_exc).__name__}")
            else:
                time.sleep(min(1.5 * attempt, 5.0))
        db: Any = None
        try:
            db = open_scanx_session()
            ensure_db_connection(db)
            doc = (
                db.query(ScanxDocument)
                .filter(ScanxDocument.id == int(document_id))
                .first()
            )
            if doc is None:
                request_cancel(int(document_id))
                safe_close_session(db)
                raise ScanxJobCancelled()
            raw_metrics = getattr(doc, "metrics_json", None)
            metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
            if metrics.get("cancel_requested"):
                request_cancel(int(document_id))
                safe_close_session(db)
                raise ScanxJobCancelled()
            raise_if_cancelled(int(document_id))
            return db, doc
        except ScanxJobCancelled:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "ScanX resume after long work failed doc_id=%s attempt=%s: %s",
                document_id,
                attempt + 1,
                exc,
            )
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
                if should_dispose_pool_for_error(exc):
                    dispose_db_pool(
                        reason=f"scanx resume after long work: {type(exc).__name__}"
                    )
                safe_close_session(db)
            time.sleep(min(2.0 * (attempt + 1), 8.0))
    if last_exc:
        raise last_exc
    return open_scanx_session(), None


# Back-compat aliases (OCR was the first long-work pause site).
_pause_db_during_ocr = _release_job_db
_resume_doc_after_ocr = _reopen_job_db


def _resolve_subjects_releasing_db(
    db: Any,
    document_id: int,
    text: str,
    *,
    use_llm: bool = True,
    prior_subjects: list[dict[str, str]] | None = None,
    doc: ScanxDocument | None = None,
    metrics: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> tuple[Any, ScanxDocument | None, list[dict[str, str]]]:
    """Run subject resolution (may call Ollama) without pinning a pool connection."""
    if doc is not None and metrics is not None and steps is not None:
        # Flush in-memory progress before closing so we don't commit a stale row.
        _persist_progress(db, doc, metrics, steps, emit=False)
    _release_job_db(db)
    try:
        subjects = resolve_subjects_from_text(
            text,
            use_llm=use_llm,
            prior_subjects=prior_subjects,
        )
    except Exception:
        db, doc = _reopen_job_db(document_id)
        raise
    db, doc = _reopen_job_db(document_id)
    return db, doc, subjects


def _call_extract_text_from_image(
    content: bytes,
    *,
    timeout_seconds: float | None = None,
    on_progress: Any = None,
    prefer_engine: str | None = None,
):
    """Call OCR with prefer_engine; tolerate stale workers missing that kwarg."""
    kwargs: dict[str, Any] = {
        "timeout_seconds": timeout_seconds,
        "on_progress": on_progress,
    }
    if prefer_engine:
        kwargs["prefer_engine"] = prefer_engine
    try:
        return extract_text_from_image(content, **kwargs)
    except TypeError as exc:
        if prefer_engine and "prefer_engine" in str(exc):
            logger.warning(
                "ScanX OCR missing prefer_engine support — retrying without it"
            )
            kwargs.pop("prefer_engine", None)
            return extract_text_from_image(content, **kwargs)
        raise


def _discard_enhanced_preview_artifacts(metrics: dict[str, Any]) -> dict[str, Any]:
    """Drop local enhanced/deskewed preview files; never keep them as rescan source.

    OCR still uses in-memory enhanced frames. Counsellor viewer shows original
    source pages. Any leftover ``__enhanced_preview*`` keys from older jobs are
    deleted from local disk (and R2 if present) then cleared from metrics.
    """
    leftover = collect_enhanced_preview_keys(metrics)
    if leftover:
        try:
            delete_scanx_objects(leftover)
        except Exception:
            logger.debug(
                "ScanX enhanced preview cleanup failed keys=%s",
                len(leftover),
                exc_info=True,
            )
    for field in (
        "enhanced_preview_key",
        "enhanced_preview_bytes",
        "enhanced_preview_keys",
        "enhanced_preview_pages",
        "enhanced_preview_page_count",
        "enhanced_preview_local_only",
        "enhanced_preview_error",
        "enhanced_preview_repaired",
    ):
        metrics.pop(field, None)
    return metrics


def _schedule_post_ocr_r2_archive(doc: ScanxDocument, metrics: dict[str, Any]) -> None:
    """After extract is in the DB, archive only the original upload(s) to R2.

    Review Scan must not wait on Cloudflare. Enhanced / deskewed / preview
    artifacts are never uploaded. Local originals remain until cancel/delete.
    """
    _discard_enhanced_preview_artifacts(metrics)
    keys = collect_scanx_original_archive_keys(doc)
    if not keys:
        return
    ctypes: dict[str, str] = {}
    names: dict[str, str] = {}
    if doc.r2_key:
        ctypes[str(doc.r2_key)] = str(doc.content_type or "application/octet-stream")
        names[str(doc.r2_key)] = str(doc.original_filename or "document")
    pages = doc.source_pages if isinstance(doc.source_pages, list) else None
    if not pages and isinstance(metrics, dict):
        raw = metrics.get("source_pages")
        pages = raw if isinstance(raw, list) else None
    for entry in pages or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("r2_key") or "").strip()
        if not key:
            continue
        ctypes[key] = str(entry.get("content_type") or "application/octet-stream")
        names[key] = str(entry.get("original_filename") or Path(key).name)
    metrics["r2_archive_pending"] = True
    metrics["r2_archive_scheduled"] = True
    metrics["r2_archive_originals_only"] = True
    schedule_archive_scanx_keys(keys, content_types=ctypes, filenames=names)
    logger.info(
        "ScanX scheduled deferred R2 archive (originals only) doc_id=%s keys=%s",
        getattr(doc, "id", None),
        len(keys),
    )


def rebuild_enhanced_preview_from_original(
    doc: ScanxDocument,
    metrics: dict[str, Any] | None = None,
    *,
    prefer_page: int = 0,
) -> bytes | None:
    """Regenerate an enhanced JPEG in memory from the original upload.

    Loads original source frames (group pages or primary ``r2_key``), re-runs
    enhance, and returns the preferred page JPEG. Does not write enhanced
    artifacts to disk or Cloudflare — rescan always uses the original.
    """
    from app.services.scanx_image_enhance import enhance_image_bytes

    if not doc.r2_key and not _source_pages_meta(doc):
        return None
    try:
        source_pages = _source_pages_meta(doc)
        if len(source_pages) > 1:
            frames = _load_source_page_images(doc)
            original = frames[0] if frames else b""
        else:
            original, _ctype = fetch_scanx_bytes(doc.r2_key)
            frames = []
    except Exception:
        logger.warning(
            "ScanX rebuild enhanced preview: fetch original failed doc_id=%s",
            getattr(doc, "id", None),
            exc_info=True,
        )
        return None

    if not frames:
        frames = []
        if looks_like_pdf(original):
            frames = render_pdf_pages_as_png(original, scale=2.0)
            if not frames:
                embedded = extract_pdf_embedded_images(original)
                pick = pick_largest_content_image(embedded)
                if pick:
                    frames = [pick]
        else:
            frames = [original] if original else []

    if not frames:
        return None

    m = dict(metrics or {})
    preferred = max(0, int(prefer_page or 0))
    preferred_preview: bytes | None = None
    first_preview: bytes | None = None

    for idx, page in enumerate(frames):
        result = None
        try:
            result = enhance_image_bytes(page)
            enhanced = result.png_bytes if result.applied else page
        except Exception:
            enhanced = page

        if is_scan_watermark_banner(enhanced):
            continue

        preview_dpi = (
            m.get("dpi_metadata")
            or m.get("dpi_after")
            or (getattr(result, "dpi_after", None) if result is not None else None)
            or 300
        )
        try:
            preview = encode_preview_jpeg(enhanced, dpi=float(preview_dpi or 300))
        except Exception:
            logger.warning(
                "ScanX rebuild enhanced preview encode failed doc_id=%s page=%s",
                getattr(doc, "id", None),
                idx,
                exc_info=True,
            )
            continue

        if first_preview is None:
            first_preview = preview
        if idx == preferred:
            preferred_preview = preview

    if metrics is not None:
        _discard_enhanced_preview_artifacts(metrics)

    if preferred_preview is not None:
        return preferred_preview
    return first_preview


def _ocr_image_batch(
    images: list[bytes],
    on_progress: Any,
    *,
    budget_seconds: float | None = None,
    prefer_engine: str | None = None,
    page_indices: list[int] | None = None,
) -> dict[str, Any]:
    """OCR many images under one shared wall-clock budget (not per-image)."""
    budget = float(budget_seconds) if budget_seconds is not None else ocr_budget_seconds()
    t0 = time.perf_counter()
    parts: list[str] = []
    all_blocks: list[Any] = []
    all_marks: list[dict[str, str]] = []
    all_table_regions: list[dict[str, Any]] = []
    ocr_ms_total = 0
    last_ocr_note = "ocr_empty"
    last_engine = "rapid"
    last_fallback_reason: str | None = None
    last_primary_engine: str | None = None
    timed_out = False
    sequential_offset = 0

    for img_i, img_bytes in enumerate(images):
        raise_if_cancelled()
        remaining = budget - (time.perf_counter() - t0)
        if remaining <= 0.5:
            timed_out = True
            last_ocr_note = "ocr_timeout"
            break
        ocr = _call_extract_text_from_image(
            img_bytes,
            timeout_seconds=remaining,
            on_progress=on_progress,
            prefer_engine=prefer_engine,
        )
        ocr_ms_total += ocr.elapsed_ms
        last_ocr_note = ocr.note
        last_engine = ocr.engine
        last_fallback_reason = ocr.fallback_reason
        last_primary_engine = ocr.primary_engine
        if ocr.text:
            parts.append(ocr.text)
        if page_indices is not None and img_i < len(page_indices):
            base_page = int(page_indices[img_i])
        else:
            base_page = sequential_offset
        for blk in getattr(ocr, "blocks", None) or []:
            # Remap page index across multi-image batches (PDF pages).
            try:
                local = int(getattr(blk, "page_index", 0) or 0)
                blk.page_index = base_page + local
            except Exception:
                pass
            all_blocks.append(blk)
        for row in getattr(ocr, "marks", None) or []:
            if isinstance(row, dict):
                all_marks.append(row)
        for region in getattr(ocr, "table_regions", None) or []:
            if isinstance(region, dict):
                all_table_regions.append(region)
        sequential_offset += max(1, int(getattr(ocr, "page_count", 1) or 1))
        if ocr.note == "ocr_timeout":
            timed_out = True
            # Budget already consumed; do not start another image.
            break

    if timed_out and not parts:
        last_ocr_note = "ocr_timeout"

    return {
        "parts": parts,
        "blocks": all_blocks,
        "marks": all_marks,
        "table_regions": all_table_regions,
        "ocr_ms_total": ocr_ms_total,
        "last_ocr_note": last_ocr_note,
        "last_engine": last_engine,
        "last_fallback_reason": last_fallback_reason,
        "last_primary_engine": last_primary_engine,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


def _apply_ocr_block_metrics(metrics: dict[str, Any], blocks: list[Any] | None) -> None:
    """Persist OCR spatial blocks + low-confidence summary onto metrics_json."""
    block_list = list(blocks or [])
    metrics["ocr_blocks"] = blocks_to_json(block_list)
    metrics.update(summarize_blocks(block_list))


def _apply_ocr_batch_metrics(metrics: dict[str, Any], batch: dict[str, Any]) -> None:
    metrics["ocr_engine"] = batch["last_engine"]
    metrics["ocr_engine_used"] = batch["last_engine"]
    metrics["ocr_ms"] = batch["ocr_ms_total"]
    metrics["ocr_note"] = batch["last_ocr_note"]
    if batch["last_primary_engine"]:
        metrics["ocr_engine_primary"] = batch["last_primary_engine"]
    if batch["last_fallback_reason"]:
        metrics["ocr_fallback_reason"] = batch["last_fallback_reason"]
    else:
        metrics.pop("ocr_fallback_reason", None)
    _apply_ocr_block_metrics(metrics, batch.get("blocks"))
    marks = batch.get("marks") or []
    if marks:
        metrics["marks"] = marks
        metrics["marks_count"] = len(marks)
    regions = batch.get("table_regions") or []
    if regions:
        metrics["table_regions"] = regions
        metrics["table_region_count"] = len(regions)


def _prepare_images_for_ocr(
    images: list[bytes],
    *,
    doc_kind: str,
    skip_enhance: bool,
    db: Any,
    doc: ScanxDocument,
    metrics: dict[str, Any],
    steps: list[dict[str, Any]],
) -> tuple[list[bytes], dict[str, Any], list[dict[str, Any]], str | None, Any, ScanxDocument | None]:
    """Enhance scanned frames before OCR; skip OpenCV for born-digital.

    Returns (images, metrics, steps, prefer_engine, db, doc).
    OpenCV enhance + in-memory OCR frames run with the job session closed.
    Enhanced scans prefer RapidOCR (Paddle remains fallback via prefer_engine).
    Always records dpi_before (and dpi_after when enhance runs).
    Enhanced/deskewed previews are never persisted — only originals go to R2.
    """
    if doc_kind != "scanned" or skip_enhance or not images:
        steps = set_step(
            steps,
            "enhance",
            STEP_STATUS_SKIPPED,
            note=(
                "Born-digital — skipped OpenCV enhance"
                if doc_kind == "born_digital"
                else (
                    "Clean digital image — skipped enhance"
                    if skip_enhance
                    else "No images to enhance"
                )
            ),
        )
        metrics["enhance_applied"] = False
        if skip_enhance and doc_kind == "scanned":
            metrics["enhance_skip_reason"] = metrics.get("enhance_skip_reason") or "already_clean"
        # Still estimate input DPI when frames exist (dpi_after stays null).
        if images:
            metrics.update(dpi_metrics_without_enhance(images))
        else:
            metrics.setdefault("dpi_before", None)
            metrics.setdefault("dpi_after", None)
            metrics.setdefault("dpi_in", None)
            metrics.setdefault("dpi_out", None)
        metrics = _persist_progress(db, doc, metrics, steps)
        # Scanned but skipped enhance still uses Rapid as primary for scan path.
        prefer = "rapid" if doc_kind == "scanned" else None
        return images, metrics, steps, prefer, db, doc

    steps = set_step(
        steps,
        "enhance",
        STEP_STATUS_IN_PROGRESS,
        note=f"Enhancing {len(images)} image(s)…",
    )
    metrics = _persist_progress(db, doc, metrics, steps)
    doc_id = int(doc.id)
    _release_job_db(db)
    enhanced, enhance_metrics = enhance_image_batch(images)
    metrics.update(enhance_metrics)
    dpi_b = enhance_metrics.get("dpi_before")
    dpi_a = enhance_metrics.get("dpi_after")
    dpi_note = ""
    if dpi_b is not None and dpi_a is not None:
        dpi_note = f" · DPI {dpi_b}→{dpi_a}"
    elif dpi_b is not None:
        dpi_note = f" · DPI in {dpi_b}"
    note = (
        f"Enhanced {enhance_metrics.get('enhance_pages', 0)}/{len(images)} "
        f"({enhance_metrics.get('enhance_ms_total', 0)} ms){dpi_note}"
    )
    steps = set_step(steps, "enhance", STEP_STATUS_COMPLETE, note=note)
    # Keep enhanced frames in memory for OCR only — do not persist preview JPEGs.
    metrics = _discard_enhanced_preview_artifacts(metrics)
    db, doc = _reopen_job_db(doc_id)
    if not doc:
        prefer = "rapid" if enhance_metrics.get("enhance_applied") else "rapid"
        return enhanced, metrics, steps, prefer, db, None
    metrics = _persist_progress(db, doc, metrics, steps)
    prefer = "rapid" if enhance_metrics.get("enhance_applied") else "rapid"
    return enhanced, metrics, steps, prefer, db, doc


def _ocr_progress_updater(
    doc_id: int,
    metrics: dict[str, Any],
    steps: list[dict[str, Any]],
):
    """Persist extract-step notes during long OCR init so UI leaves 16%.

    Uses a fresh DB session per callback — OCR runs on a worker thread and must
    not share the job's Session (SQLAlchemy is not thread-safe; shared use hung
    the tunnel pool). Soft-ramps percent within the extract band (35%→49%) so
    the bar is not frozen for the full OCR budget.
    """
    state: dict[str, Any] = {
        "metrics": metrics,
        "steps": steps,
        "last": "",
        "tick": 0,
        "last_persist_at": 0.0,
    }
    lock = threading.Lock()
    # Cap heartbeat DB checkouts so OCR progress cannot starve notifications/inbox.
    _min_persist_interval_sec = 8.0

    def _on_progress(message: str) -> None:
        from app.models.scanx import ScanxDocument as ScanxDoc

        if is_cancel_requested(doc_id):
            raise ScanxJobCancelled()
        note = (message or "").strip()
        if not note:
            return
        now = time.monotonic()
        with lock:
            if note == state["last"]:
                if is_cancel_requested(doc_id):
                    raise ScanxJobCancelled()
                return
            last_persist = float(state.get("last_persist_at") or 0.0)
            if last_persist and (now - last_persist) < _min_persist_interval_sec:
                # Keep latest note in memory; skip pool checkout this tick.
                state["last"] = note
                return
            state["last"] = note
            state["last_persist_at"] = now
            state["tick"] = int(state["tick"] or 0) + 1
            new_steps = set_step(
                list(state["steps"]),
                "extract",
                STEP_STATUS_IN_PROGRESS,
                note=note,
            )
            new_metrics = apply_progress_to_metrics(dict(state["metrics"]), new_steps)
            # Soft ramp inside extract-in-progress (half-weight ≈ 35%) up toward
            # extract-complete (50%) so counsellors see movement during OCR.
            base = compute_progress_percent(new_steps)
            soft = min(49, base + min(14, int(state["tick"])))
            new_metrics["progress_percent"] = soft
            state["steps"] = new_steps
            state["metrics"] = new_metrics

        session = open_scanx_session(timeout=0.15, optional=True)
        if session is None:
            return
        try:
            row = session.query(ScanxDoc).filter(ScanxDoc.id == int(doc_id)).first()
            if not row:
                request_cancel(doc_id)
                raise ScanxJobCancelled()
            merged = dict(row.metrics_json or {})
            if merged.get("cancel_requested"):
                request_cancel(doc_id)
                raise ScanxJobCancelled()
            # Merge onto latest metrics so we don't clobber concurrent job writes.
            merged = dict(row.metrics_json or {})
            merged.update(
                {
                    "progress_steps": new_steps,
                    "progress_percent": new_metrics.get("progress_percent"),
                    "current_step_id": new_metrics.get("current_step_id"),
                    "current_step_label": new_metrics.get("current_step_label"),
                    "progress_updated_at": new_metrics.get("progress_updated_at"),
                }
            )
            row.metrics_json = merged
            session.commit()
            _emit_status(row)
        except ScanxJobCancelled:
            raise
        except Exception as exc:
            logger.warning(
                "ScanX OCR progress persist failed doc_id=%s: %s",
                doc_id,
                exc,
            )
            try:
                session.rollback()
            except Exception:
                pass
            # Do not dispose the shared pool from OCR heartbeats — a brief tunnel
            # blip used to wipe every connection and 500 Action Required list polls.
            try:
                session.invalidate()
            except Exception:
                pass
        finally:
            safe_close_session(session)

    return state, _on_progress


def _fail_step_and_doc(
    db: Any,
    doc: ScanxDocument,
    metrics: dict[str, Any],
    steps: list[dict[str, Any]],
    step_id: str,
    *,
    error_code: str,
    note: str | None = None,
) -> None:
    steps = set_step(steps, step_id, STEP_STATUS_FAILED, note=note)
    metrics = apply_progress_to_metrics(metrics, steps)
    doc.status = STATUS_RED_FLAG
    doc.error_code = error_code
    doc.metrics_json = metrics
    db.commit()
    _emit_status(doc)


def _finalize_status(
    doc: ScanxDocument,
    *,
    embed_source: str,
    page_count: int | None,
    metrics: dict[str, Any],
    extract_note: str | None = None,
) -> None:
    """Leave Parsing: text present → Action Required; empty → clear M14/M15 (never Verified)."""
    if embed_source:
        doc.status = STATUS_ACTION_REQUIRED
        doc.error_code = None
        metrics.pop("empty_extract", None)
        doc.metrics_json = metrics
        return

    note = (extract_note or "").strip()
    ocr_empty = note in {
        "ocr_empty",
        "ocr_timeout",
        "ocr_failed",
        "ocr_unavailable",
        "docx_ocr_empty",
        "docx_ocr_timeout",
        "docx_ocr_failed",
        "docx_ocr_unavailable",
        "pdf_ocr_empty",
        "pdf_ocr_timeout",
        "pdf_ocr_failed",
        "pdf_ocr_unavailable",
    }
    if _is_image(doc) or ocr_empty:
        doc.status = STATUS_ACTION_REQUIRED
        doc.error_code = "M15"
        metrics["empty_extract"] = True
        doc.metrics_json = metrics
    else:
        # Valid PDF/DOCX/unknown with no text → Action Required (never false M7).
        doc.status = STATUS_ACTION_REQUIRED
        doc.error_code = "M14"
        metrics["empty_extract"] = True
        doc.metrics_json = metrics


def process_scanx_document(document_id: int) -> dict[str, Any]:
    """Worker entrypoint: Parsing → Action Required | Verified | Red Flags.

    Extract text first and leave Parsing promptly; embeddings run with a short
    budget afterward (or are skipped if Ollama is slow/down). Progress steps
    are committed along the way so the UI can poll live %.
    """
    t0 = time.perf_counter()
    bind_job(int(document_id))
    db = None
    try:
        db = open_scanx_session()
        raise_if_cancelled(int(document_id))
        doc = db.query(ScanxDocument).filter(ScanxDocument.id == int(document_id)).first()
        if not doc:
            return {"ok": False, "error": "not_found"}
        metrics_early = dict(doc.metrics_json or {}) if isinstance(doc.metrics_json, dict) else {}
        if metrics_early.get("cancel_requested"):
            raise ScanxJobCancelled()

        doc.status = STATUS_PARSING
        doc.error_code = None
        metrics = dict(doc.metrics_json or {})
        metrics["worker"] = "scanx_process_v4"
        steps = _ensure_steps(metrics)
        steps = set_step(
            steps,
            "queued",
            STEP_STATUS_COMPLETE,
            note="Worker started",
            label="Queued / Started",
        )
        steps = set_step(
            steps,
            "validate_store",
            STEP_STATUS_IN_PROGRESS,
            note="Fetching stored file…",
        )
        metrics = _persist_progress(db, doc, metrics, steps)
        prior_text = normalize_extracted_display(doc.extracted_text)

        if not doc.r2_key:
            _fail_step_and_doc(
                db,
                doc,
                metrics,
                steps,
                "validate_store",
                error_code="M10",
                note="Missing storage key",
            )
            return {"ok": False, "error": "missing_r2_key"}

        t_fetch = time.perf_counter()
        r2_key = doc.r2_key
        doc_id = int(document_id)
        # R2/local fetch can hang on network — do not pin a pool slot.
        _release_job_db(db)
        try:
            content, fetched_ctype = fetch_scanx_bytes(r2_key)
        except Exception as exc:
            logger.exception("ScanX fetch failed doc_id=%s", document_id)
            record_exception_event_isolated(
                severity="error",
                source="scanx",
                message=f"ScanX fetch failed for document {document_id}",
                category="scanx_fetch",
                exception_type=type(exc).__name__,
                related_resource="scanx_document",
                related_id=str(document_id),
                details=[str(exc)[:500]],
            )
            db, doc = _reopen_job_db(doc_id)
            if not doc:
                return {"ok": False, "error": "not_found_after_fetch"}
            _fail_step_and_doc(
                db,
                doc,
                metrics,
                steps,
                "validate_store",
                error_code="M10",
                note=str(exc)[:200],
            )
            return {"ok": False, "error": "fetch_failed"}
        fetch_ms = int((time.perf_counter() - t_fetch) * 1000)
        db, doc = _reopen_job_db(doc_id)
        if not doc:
            return {"ok": False, "error": "not_found_after_fetch"}

        if fetched_ctype and fetched_ctype != "application/octet-stream" and not doc.content_type:
            doc.content_type = fetched_ctype

        steps = set_step(
            steps,
            "validate_store",
            STEP_STATUS_COMPLETE,
            note=f"Fetched ({fetch_ms} ms)",
        )
        steps = set_step(
            steps,
            "classify",
            STEP_STATUS_IN_PROGRESS,
            note="Classifying…",
        )
        metrics["fetch_ms"] = fetch_ms
        metrics = _persist_progress(db, doc, metrics, steps)

        # Born-digital vs scanned — CPU work; release pool slot.
        ctype_for_class = doc.content_type
        fname_for_class = doc.original_filename
        _release_job_db(db)
        classification = classify_scanx_document(
            content,
            content_type=ctype_for_class,
            filename=fname_for_class,
        )
        db, doc = _reopen_job_db(doc_id)
        if not doc:
            return {"ok": False, "error": "not_found_after_classify"}
        metrics.update(classification.to_metrics())
        doc_kind = classification.doc_kind
        skip_enhance = bool(classification.skip_enhance)
        steps = set_step(
            steps,
            "classify",
            STEP_STATUS_COMPLETE,
            note=f"{doc_kind} ({classification.reason})",
        )
        # Mark enhance skipped early for born-digital / clean rasters so starting
        # extract cannot auto-complete a pending enhance step as "done".
        if doc_kind == "born_digital" or skip_enhance:
            steps = set_step(
                steps,
                "enhance",
                STEP_STATUS_SKIPPED,
                note=(
                    "Born-digital — skipped OpenCV enhance"
                    if doc_kind == "born_digital"
                    else "Clean digital image — skipped enhance"
                ),
            )
            metrics["enhance_applied"] = False
            metrics.setdefault("dpi_after", None)
            metrics.setdefault("dpi_out", None)
            if skip_enhance and doc_kind == "scanned":
                metrics["enhance_skip_reason"] = (
                    metrics.get("enhance_skip_reason") or "already_clean"
                )
        metrics = _persist_progress(db, doc, metrics, steps)

        extracted: str | None = None
        page_count = doc.page_count
        extract_note: str | None = None
        prefetched_subjects: list[dict[str, str]] = []
        prefer_ocr_engine: str | None = None

        t_extract = time.perf_counter()
        if _is_pdf(doc) or looks_like_pdf(content):
            if looks_like_pdf(content) and not (doc.content_type or "").lower().startswith(
                "application/pdf"
            ):
                doc.content_type = "application/pdf"
            # Native probe first (no extract-step bump yet — scanned path must
            # finish/skip enhance before extract IN_PROGRESS or set_step would
            # auto-complete a pending enhance as "done").
            try:
                page_count, extracted, prefetched_subjects = extract_pdf_text(content)
            except Exception as exc:
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note="Extracting text…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
                detail = getattr(exc, "detail", None)
                code = "M7"
                if isinstance(detail, dict) and detail.get("error_code"):
                    code = str(detail["error_code"])
                _fail_step_and_doc(
                    db,
                    doc,
                    metrics,
                    steps,
                    "extract",
                    error_code=code,
                    note=str(exc)[:200],
                )
                return {"ok": False, "error": code}
            extract_note = "pdf_native" if (extracted or "").strip() else "pdf_text_empty"
            if prefetched_subjects:
                metrics["pdf_subjects"] = len(prefetched_subjects)

            sparse_native = len((extracted or "").strip()) < 40
            need_ocr = doc_kind == "scanned" or (
                not (extracted or "").strip()
                or (sparse_native and not prefetched_subjects)
            )
            if need_ocr and doc_kind == "born_digital" and (extracted or "").strip() and not sparse_native:
                need_ocr = False
            if need_ocr:
                doc_id = int(doc.id)
                # Snapshot before release — commit+close detaches doc; reading
                # expired attrs afterward raises DetachedInstanceError (M16).
                fname_u = (doc.original_filename or "").upper()
                likely_passport = "PASSPORT" in fname_u or "PASSEPORT" in fname_u
                _release_job_db(db)
                embedded = extract_pdf_embedded_images(content)
                ocr_images = embedded
                ocr_source = "embedded"
                # CamScanner embeds a tiny stamp XObject; when present (or when the
                # largest blob is still stamp-sized), rasterize full pages so
                # Enhanced DPI is the page — never the "Scanned with CamScanner" strip.
                has_scan_stamp = pdf_has_scan_app_stamp(content)
                pdf_pages = pdf_page_count(content)
                # Multi-page scans (passport page 1 + page 2) must rasterize every
                # page — embedded XObjects are often only the largest leaf and
                # omit page 2 from the Enhanced viewer.
                multi_page_scan = pdf_pages >= 2 and doc_kind == "scanned"
                force_render = has_scan_stamp or multi_page_scan or (
                    not pdf_embedded_images_usable_for_ocr(ocr_images)
                )
                # Passports need sharper rasterization so the bottom MRZ is not cut off.
                render_scale = 3.0 if (has_scan_stamp or likely_passport) else 2.0
                if force_render or likely_passport:
                    rendered = render_pdf_pages_as_png(content, scale=render_scale)
                    if rendered:
                        ocr_images = rendered
                        ocr_source = "rendered"
                        pdf_rendered_pages = len(rendered)
                        metrics["pdf_render_scale"] = render_scale
                        metrics["pdf_page_count"] = pdf_pages or len(rendered)
                        metrics["pdf_ocr_fallback"] = (
                            "render_after_camscanner_stamp"
                            if has_scan_stamp
                            else (
                                "render_passport_high_dpi"
                                if likely_passport
                                else (
                                    "render_multipage_scan"
                                    if multi_page_scan
                                    else "render_after_tiny_or_missing_embedded"
                                )
                            )
                        )
                    elif not ocr_images:
                        ocr_images = []
                        ocr_source = "embedded"
                        pdf_rendered_pages = 0
                    else:
                        pdf_rendered_pages = 0
                        metrics["pdf_ocr_fallback"] = "embedded_below_page_threshold"
                else:
                    pdf_rendered_pages = 0
                db, doc = _reopen_job_db(doc_id)
                if not doc:
                    return {"ok": False, "error": "not_found_after_pdf_prep"}
                metrics["pdf_embedded_images"] = len(embedded)
                if pdf_rendered_pages:
                    metrics["pdf_rendered_pages"] = pdf_rendered_pages
                if ocr_images:
                    images, ocr_page_indices = select_images_for_ocr(
                        ocr_images,
                        likely_passport=likely_passport,
                    )
                    metrics["ocr_page_indices"] = list(ocr_page_indices)
                    metrics["ocr_page_count_selected"] = len(images)
                    metrics["ocr_page_count_available"] = len(ocr_images)
                    already_skipped = any(
                        s.get("id") == "enhance"
                        and s.get("status") == STEP_STATUS_SKIPPED
                        for s in steps
                    )
                    if already_skipped:
                        prefer_ocr_engine = "rapid" if doc_kind == "scanned" else None
                        if metrics.get("dpi_before") is None and metrics.get("dpi_in") is None:
                            metrics.update(dpi_metrics_without_enhance(images))
                    else:
                        images, metrics, steps, prefer_ocr_engine, db, doc = (
                            _prepare_images_for_ocr(
                                images,
                                doc_kind=doc_kind,
                                skip_enhance=skip_enhance,
                                db=db,
                                doc=doc,
                                metrics=metrics,
                                steps=steps,
                            )
                        )
                        if not doc:
                            return {"ok": False, "error": "not_found_after_enhance"}
                    steps = set_step(
                        steps,
                        "extract",
                        STEP_STATUS_IN_PROGRESS,
                        note=f"OCR on {len(images)} PDF {ocr_source} image(s)…",
                    )
                    metrics = _persist_progress(db, doc, metrics, steps)
                    doc_id = int(doc.id)
                    _pause_db_during_ocr(db)
                    ocr_state, on_ocr_progress = _ocr_progress_updater(
                        doc_id, metrics, steps
                    )
                    batch = _ocr_image_batch(
                        images,
                        on_ocr_progress,
                        prefer_engine=prefer_ocr_engine,
                        page_indices=list(ocr_page_indices),
                        budget_seconds=(
                            max(ocr_budget_seconds(), 420.0)
                            if likely_passport and len(images) >= 4
                            else None
                        ),
                    )
                    db, doc = _resume_doc_after_ocr(doc_id)
                    if not doc:
                        return {"ok": False, "error": "not_found_after_ocr"}
                    metrics = dict(ocr_state["metrics"])
                    steps = list(ocr_state["steps"])
                    ocr_parts = list(batch["parts"] or [])
                    _apply_ocr_batch_metrics(metrics, batch)
                    page_count = page_count or len(images)
                    # Passport / MRZ recovery: primary OCR often truncates TD3 line 2.
                    # Re-OCR a bottom band of page 1 at higher clarity and merge lines.
                    joined_probe = "\n".join(ocr_parts)
                    probe_u = joined_probe.upper().replace(" ", "")
                    needs_mrz_repair = bool(
                        likely_passport
                        or has_scan_stamp
                        or "P<" in probe_u
                        or "PASSPORT" in joined_probe.upper()
                    )
                    if needs_mrz_repair and images:
                        try:
                            from app.services.scanx_passport import (
                                crop_bottom_band_png,
                                extract_mrz_lines,
                                parse_td3_mrz,
                            )

                            mrz_now = parse_td3_mrz(extract_mrz_lines(joined_probe))
                            mrz_text = str(mrz_now.get("mrz_string") or "")
                            incomplete = bool(mrz_now.get("_mrz_incomplete")) or (
                                "\n" not in mrz_text
                            )
                            # Always re-OCR the MRZ band for passports when line 2
                            # is missing — primary OCR often drops the second TD3 line.
                            if incomplete or likely_passport:
                                band = crop_bottom_band_png(
                                    images[0],
                                    fraction=0.42 if likely_passport else 0.34,
                                )
                                if band:
                                    doc_id = int(doc.id)
                                    _pause_db_during_ocr(db)
                                    strip = _call_extract_text_from_image(
                                        band,
                                        timeout_seconds=min(
                                            45.0, ocr_budget_seconds() * 0.25
                                        ),
                                        prefer_engine=prefer_ocr_engine or "rapid",
                                    )
                                    db, doc = _resume_doc_after_ocr(doc_id)
                                    if not doc:
                                        return {
                                            "ok": False,
                                            "error": "not_found_after_mrz_strip",
                                        }
                                    strip_text = (strip.text or "").strip()
                                    if strip_text:
                                        ocr_parts.append(strip_text)
                                        metrics["passport_mrz_strip_ocr"] = True
                                        metrics["passport_mrz_strip_chars"] = len(
                                            strip_text
                                        )
                                        # Prefer a complete two-line MRZ from the
                                        # band when the page OCR only had line 1.
                                        strip_mrz = parse_td3_mrz(
                                            extract_mrz_lines(
                                                f"{joined_probe}\n{strip_text}"
                                            )
                                        )
                                        if strip_mrz.get("mrz_string") and "\n" in str(
                                            strip_mrz.get("mrz_string") or ""
                                        ):
                                            metrics["passport_mrz_string"] = strip_mrz[
                                                "mrz_string"
                                            ]
                        except Exception:
                            logger.debug(
                                "Passport MRZ strip OCR skipped doc_id=%s",
                                document_id,
                                exc_info=True,
                            )
                    if ocr_parts:
                        ocr_text = "\n\n".join(ocr_parts)
                        if not (extracted or "").strip():
                            extracted = ocr_text
                        else:
                            extracted = f"{extracted}\n\n{ocr_text}"
                        extract_note = "pdf_ocr_ok"
                        db, doc, ocr_subjects = _resolve_subjects_releasing_db(
                            db,
                            doc_id,
                            ocr_text,
                            use_llm=True,
                            doc=doc,
                            metrics=metrics,
                            steps=steps,
                        )
                        if not doc:
                            return {"ok": False, "error": "not_found_after_subjects"}
                        prefetched_subjects = merge_subjects(
                            prefetched_subjects, ocr_subjects
                        )
                    elif not (extracted or "").strip():
                        extract_note = f"pdf_{batch['last_ocr_note']}"
                else:
                    steps = set_step(
                        steps,
                        "enhance",
                        STEP_STATUS_SKIPPED,
                        note="No PDF images to enhance",
                    )
                    metrics["enhance_applied"] = False
                    steps = set_step(
                        steps,
                        "extract",
                        STEP_STATUS_IN_PROGRESS,
                        note="No images for OCR…",
                    )
                    metrics = _persist_progress(db, doc, metrics, steps)
            else:
                if not any(
                    s.get("id") == "enhance"
                    and s.get("status")
                    in {STEP_STATUS_SKIPPED, STEP_STATUS_COMPLETE, STEP_STATUS_FAILED}
                    for s in steps
                ):
                    steps = set_step(
                        steps,
                        "enhance",
                        STEP_STATUS_SKIPPED,
                        note="Born-digital PDF — native text used",
                    )
                    metrics["enhance_applied"] = False
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note="Using native PDF text…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
        elif _is_docx(doc) or looks_like_docx(content):
            if looks_like_docx(content) and not (doc.content_type or "").lower().startswith(
                "application/vnd.openxmlformats"
            ):
                doc.content_type = DOCX_MIME_TYPE
            try:
                _pages, extracted = inspect_docx(content)
                page_count = _pages if _pages is not None else page_count
                _joined, prefetched_subjects = extract_docx_text(content)
                if _joined and not (extracted or "").strip():
                    extracted = _joined
            except Exception as exc:
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note="Extracting text…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
                detail = getattr(exc, "detail", None)
                code = "M7"
                if isinstance(detail, dict) and detail.get("error_code"):
                    code = str(detail["error_code"])
                _fail_step_and_doc(
                    db,
                    doc,
                    metrics,
                    steps,
                    "extract",
                    error_code=code,
                    note=str(exc)[:200],
                )
                return {"ok": False, "error": code}
            extract_note = "docx_native" if (extracted or "").strip() else "docx_no_page_cap"
            if prefetched_subjects:
                metrics["docx_subjects"] = len(prefetched_subjects)

            # Image-only / sparse Word (scanned page pasted into .docx): enhance + OCR.
            # Mirror PDF: sparse native text without subjects must still OCR embedded images
            # so trailing subjects (e.g. Mathematics) are not lost when captions exist.
            sparse_native = len((extracted or "").strip()) < 40
            thin_subjects = len(quality_subjects(prefetched_subjects)) < 4
            need_docx_ocr = doc_kind == "scanned" or (
                not (extracted or "").strip()
                or (sparse_native and not prefetched_subjects)
                or (thin_subjects and looks_like_marksheet(extracted or ""))
            )
            # Born-digital with usable native body: skip RapidOCR/OpenCV — native
            # python-docx (paragraphs + tables) is authoritative. OCR only when
            # scanned / empty / truly sparse.
            if (
                need_docx_ocr
                and doc_kind == "born_digital"
                and (extracted or "").strip()
                and not sparse_native
            ):
                need_docx_ocr = False
            if need_docx_ocr:
                doc_id = int(doc.id)
                _release_job_db(db)
                embedded = extract_docx_embedded_images(content)
                db, doc = _reopen_job_db(doc_id)
                if not doc:
                    return {"ok": False, "error": "not_found_after_docx_prep"}
                metrics["docx_embedded_images"] = len(embedded)
                if embedded:
                    # Largest media first (extract_docx_embedded_images ranks by area).
                    # Cap to max_pages — usually 1 certificate page, not logo+page collage.
                    images = embedded[: max(1, max_pages())]
                    already_skipped = any(
                        s.get("id") == "enhance"
                        and s.get("status") == STEP_STATUS_SKIPPED
                        for s in steps
                    )
                    if already_skipped:
                        prefer_ocr_engine = "rapid"
                        if metrics.get("dpi_before") is None and metrics.get("dpi_in") is None:
                            metrics.update(dpi_metrics_without_enhance(images))
                    else:
                        images, metrics, steps, prefer_ocr_engine, db, doc = (
                            _prepare_images_for_ocr(
                                images,
                                doc_kind="scanned",
                                skip_enhance=skip_enhance,
                                db=db,
                                doc=doc,
                                metrics=metrics,
                                steps=steps,
                            )
                        )
                        if not doc:
                            return {"ok": False, "error": "not_found_after_enhance"}
                    steps = set_step(
                        steps,
                        "extract",
                        STEP_STATUS_IN_PROGRESS,
                        note=f"OCR on {len(images)} embedded image(s)…",
                    )
                    metrics = _persist_progress(db, doc, metrics, steps)
                    doc_id = int(doc.id)
                    _pause_db_during_ocr(db)
                    ocr_state, on_ocr_progress = _ocr_progress_updater(
                        doc_id, metrics, steps
                    )
                    batch = _ocr_image_batch(
                        images,
                        on_ocr_progress,
                        prefer_engine=prefer_ocr_engine,
                    )
                    db, doc = _resume_doc_after_ocr(doc_id)
                    if not doc:
                        return {"ok": False, "error": "not_found_after_ocr"}
                    metrics = dict(ocr_state["metrics"])
                    steps = list(ocr_state["steps"])
                    ocr_parts = batch["parts"]
                    _apply_ocr_batch_metrics(metrics, batch)
                    page_count = page_count or len(images)
                    if ocr_parts:
                        ocr_joined = "\n\n".join(ocr_parts)
                        native = (extracted or "").strip()
                        # Never wipe born-digital native text (tables/subjects)
                        # with embedded-image OCR — merge so Mathematics etc. survive.
                        if native and len(native) >= 40:
                            extracted = f"{native}\n\n{ocr_joined}"
                            extract_note = "docx_native+ocr"
                        else:
                            extracted = ocr_joined
                            extract_note = "docx_ocr_ok"
                        db, doc, docx_subjects = _resolve_subjects_releasing_db(
                            db,
                            doc_id,
                            extracted,
                            use_llm=True,
                            doc=doc,
                            metrics=metrics,
                            steps=steps,
                        )
                        if not doc:
                            return {"ok": False, "error": "not_found_after_subjects"}
                        prefetched_subjects = merge_subjects(
                            prefetched_subjects,
                            docx_subjects,
                        )
                    else:
                        extract_note = f"docx_{batch['last_ocr_note']}"
                else:
                    steps = set_step(
                        steps,
                        "enhance",
                        STEP_STATUS_SKIPPED,
                        note="No embedded images to enhance",
                    )
                    metrics["enhance_applied"] = False
                    steps = set_step(
                        steps,
                        "extract",
                        STEP_STATUS_IN_PROGRESS,
                        note="No embedded images for OCR…",
                    )
                    metrics = _persist_progress(db, doc, metrics, steps)
            else:
                if not any(
                    s.get("id") == "enhance"
                    and s.get("status")
                    in {STEP_STATUS_SKIPPED, STEP_STATUS_COMPLETE, STEP_STATUS_FAILED}
                    for s in steps
                ):
                    steps = set_step(
                        steps,
                        "enhance",
                        STEP_STATUS_SKIPPED,
                        note="Born-digital DOCX — native text used",
                    )
                    metrics["enhance_applied"] = False
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note="Using native DOCX text…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
        elif _is_image(doc) or len(_source_pages_meta(doc)) > 1:
            source_pages = _source_pages_meta(doc)
            multi_image = len(source_pages) > 1
            page_count = page_count or (len(source_pages) if source_pages else 1)
            # Enhance before extract so the enhance step is not auto-completed.
            already_skipped = any(
                s.get("id") == "enhance" and s.get("status") == STEP_STATUS_SKIPPED
                for s in steps
            )
            if multi_image:
                raw_images = _load_source_page_images(doc, fallback_content=content)
                if not raw_images:
                    raw_images = [content] if content else []
                metrics["multi_image_group"] = True
                metrics["source_page_count"] = len(raw_images)
                if already_skipped:
                    images = raw_images
                    prefer_ocr_engine = "rapid"
                    if metrics.get("dpi_before") is None and metrics.get("dpi_in") is None:
                        metrics.update(dpi_metrics_without_enhance(images))
                        metrics = _persist_progress(db, doc, metrics, steps)
                else:
                    images, metrics, steps, prefer_ocr_engine, db, doc = (
                        _prepare_images_for_ocr(
                            raw_images,
                            doc_kind=doc_kind,
                            skip_enhance=skip_enhance,
                            db=db,
                            doc=doc,
                            metrics=metrics,
                            steps=steps,
                        )
                    )
                    if not doc:
                        return {"ok": False, "error": "not_found_after_enhance"}
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note=f"OCR on {len(images)} grouped image page(s)…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
                doc_id = int(doc.id)
                _pause_db_during_ocr(db)
                ocr_state, on_ocr_progress = _ocr_progress_updater(
                    doc_id, metrics, steps
                )
                batch = _ocr_image_batch(
                    images,
                    on_ocr_progress,
                    prefer_engine=prefer_ocr_engine,
                )
                db, doc = _resume_doc_after_ocr(doc_id)
                if not doc:
                    return {"ok": False, "error": "not_found_after_ocr"}
                metrics = dict(ocr_state["metrics"])
                steps = list(ocr_state["steps"])
                ocr_parts = list(batch["parts"] or [])
                _apply_ocr_batch_metrics(metrics, batch)
                page_count = max(page_count or 0, len(images))
                joined_probe = "\n".join(ocr_parts)
                probe_u = joined_probe.upper().replace(" ", "")
                likely_passport = bool(
                    "P<" in probe_u
                    or "PASSPORT" in joined_probe.upper()
                    or "REPUBLIC" in joined_probe.upper()
                )
                if likely_passport and images:
                    try:
                        from app.services.scanx_passport import (
                            crop_bottom_band_png,
                            extract_mrz_lines,
                            parse_td3_mrz,
                        )

                        mrz_now = parse_td3_mrz(extract_mrz_lines(joined_probe))
                        mrz_text = str(mrz_now.get("mrz_string") or "")
                        incomplete = bool(mrz_now.get("_mrz_incomplete")) or (
                            "\n" not in mrz_text
                        )
                        if incomplete or likely_passport:
                            band = crop_bottom_band_png(
                                images[0],
                                fraction=0.42,
                            )
                            if band:
                                doc_id = int(doc.id)
                                _pause_db_during_ocr(db)
                                strip = _call_extract_text_from_image(
                                    band,
                                    timeout_seconds=min(
                                        45.0, ocr_budget_seconds() * 0.25
                                    ),
                                    prefer_engine=prefer_ocr_engine or "rapid",
                                )
                                db, doc = _resume_doc_after_ocr(doc_id)
                                if not doc:
                                    return {
                                        "ok": False,
                                        "error": "not_found_after_mrz_ocr",
                                    }
                                if strip.text:
                                    ocr_parts.append(strip.text)
                                    metrics["passport_mrz_band_ocr"] = True
                                    if strip.text:
                                        metrics["passport_mrz_string"] = "\n".join(
                                            extract_mrz_lines(
                                                "\n".join(ocr_parts)
                                            )[:2]
                                        )
                    except Exception:
                        logger.debug(
                            "ScanX multi-image MRZ band OCR skipped",
                            exc_info=True,
                        )
                extracted = "\n\n".join(p for p in ocr_parts if p)
                extract_note = batch.get("last_ocr_note") or "ocr_multi_image"
                metrics["ocr_engine"] = batch.get("last_engine") or metrics.get(
                    "ocr_engine"
                )
                metrics["ocr_engine_used"] = metrics.get("ocr_engine")
                metrics["ocr_ms"] = batch.get("ocr_ms_total")
                metrics["ocr_note"] = extract_note
                if batch.get("last_primary_engine"):
                    metrics["ocr_engine_primary"] = batch["last_primary_engine"]
                if batch.get("last_fallback_reason"):
                    metrics["ocr_fallback_reason"] = batch["last_fallback_reason"]
                _apply_ocr_block_metrics(metrics, batch.get("blocks"))
                if extracted:
                    db, doc, prefetched_subjects = _resolve_subjects_releasing_db(
                        db,
                        int(doc.id),
                        extracted,
                        use_llm=True,
                        doc=doc,
                        metrics=metrics,
                        steps=steps,
                    )
                    if not doc:
                        return {"ok": False, "error": "not_found_after_subjects"}
            else:
                if already_skipped:
                    images = [content]
                    prefer_ocr_engine = "rapid"
                    # Early skip (e.g. clean digital) still needs dpi_before on metrics.
                    if metrics.get("dpi_before") is None and metrics.get("dpi_in") is None:
                        metrics.update(dpi_metrics_without_enhance(images))
                        metrics = _persist_progress(db, doc, metrics, steps)
                else:
                    images, metrics, steps, prefer_ocr_engine, db, doc = (
                        _prepare_images_for_ocr(
                            [content],
                            doc_kind=doc_kind,
                            skip_enhance=skip_enhance,
                            db=db,
                            doc=doc,
                            metrics=metrics,
                            steps=steps,
                        )
                    )
                    if not doc:
                        return {"ok": False, "error": "not_found_after_enhance"}
                content_for_ocr = images[0] if images else content
                steps = set_step(
                    steps,
                    "extract",
                    STEP_STATUS_IN_PROGRESS,
                    note="Running OCR…",
                )
                metrics = _persist_progress(db, doc, metrics, steps)
                doc_id = int(doc.id)
                _pause_db_during_ocr(db)
                ocr_state, on_ocr_progress = _ocr_progress_updater(doc_id, metrics, steps)
                ocr = _call_extract_text_from_image(
                    content_for_ocr,
                    timeout_seconds=ocr_budget_seconds(),
                    on_progress=on_ocr_progress,
                    prefer_engine=prefer_ocr_engine,
                )
                db, doc = _resume_doc_after_ocr(doc_id)
                if not doc:
                    return {"ok": False, "error": "not_found_after_ocr"}
                metrics = dict(ocr_state["metrics"])
                steps = list(ocr_state["steps"])
                extracted = ocr.text
                page_count = ocr.page_count or page_count or 1
                extract_note = ocr.note
                metrics["ocr_engine"] = ocr.engine
                metrics["ocr_engine_used"] = ocr.engine
                metrics["ocr_ms"] = ocr.elapsed_ms
                metrics["ocr_note"] = ocr.note
                if ocr.primary_engine:
                    metrics["ocr_engine_primary"] = ocr.primary_engine
                if ocr.fallback_reason:
                    metrics["ocr_fallback_reason"] = ocr.fallback_reason
                else:
                    metrics.pop("ocr_fallback_reason", None)
                _apply_ocr_block_metrics(metrics, getattr(ocr, "blocks", None))
                ocr_marks = list(getattr(ocr, "marks", None) or [])
                if ocr_marks:
                    metrics["marks"] = ocr_marks
                    metrics["marks_count"] = len(ocr_marks)
                ocr_regions = list(getattr(ocr, "table_regions", None) or [])
                if ocr_regions:
                    metrics["table_regions"] = ocr_regions
                    metrics["table_region_count"] = len(ocr_regions)
                if extracted:
                    db, doc, prefetched_subjects = _resolve_subjects_releasing_db(
                        db,
                        doc_id,
                        extracted,
                        use_llm=True,
                        doc=doc,
                        metrics=metrics,
                        steps=steps,
                    )
                    if not doc:
                        return {"ok": False, "error": "not_found_after_subjects"}
        else:
            extract_note = "unsupported_extract"
            steps = set_step(
                steps,
                "enhance",
                STEP_STATUS_SKIPPED,
                note="Unsupported type",
            )
            metrics["enhance_applied"] = False
            steps = set_step(
                steps,
                "extract",
                STEP_STATUS_IN_PROGRESS,
                note="Unsupported extract",
            )
        extract_ms = int((time.perf_counter() - t_extract) * 1000)

        # Born-digital native PDF/DOCX: preserve Title Case subjects — do not run
        # RapidOCR noise filters that historically wiped "Tamil"/"English"/etc.
        _native_notes = {"docx_native", "pdf_native"}
        if (extract_note or "") in _native_notes:
            text = normalize_native_document_text(extracted) or prior_text
        else:
            text = normalize_extracted_display(extracted) or prior_text
        embed_source = normalize_utf8_text(text)
        doc.extracted_text = text or None
        doc.page_count = page_count
        metrics["page_count"] = page_count
        metrics["extracted_chars"] = len(embed_source)
        metrics["extract_ms"] = extract_ms
        if extract_note:
            metrics["extract_note"] = extract_note

        # Auto-classify document type from OCR/native text (RegEx / heuristics).
        try:
            from app.constants.scanx import DOCUMENT_TYPE_TO_SUBFOLDER
            from app.services.scanx_type_classify import classify_document_type

            prior_type = str(doc.document_type_id or "").strip().upper()
            type_hit = classify_document_type(
                text,
                filename=doc.original_filename,
                prior_type_id=prior_type
                if prior_type not in {"", "UNKNOWN", "AUTO"}
                else None,
            )
            metrics.update(type_hit.to_metrics())
            new_type = type_hit.document_type_id
            if new_type and new_type != prior_type:
                doc.document_type_id = new_type
                sub = DOCUMENT_TYPE_TO_SUBFOLDER.get(new_type)
                if sub:
                    doc.subfolder = sub
            elif prior_type in {"", "AUTO"} and new_type:
                doc.document_type_id = new_type
                sub = DOCUMENT_TYPE_TO_SUBFOLDER.get(new_type)
                if sub:
                    doc.subfolder = sub
            if new_type == "UNKNOWN":
                metrics["requires_manual_review"] = True
                metrics["counsellor_note"] = (
                    str(metrics.get("counsellor_note") or "").strip()
                    + " Document type could not be auto-detected — please confirm."
                ).strip()
        except Exception:
            logger.debug(
                "ScanX type classify skipped doc_id=%s", document_id, exc_info=True
            )
            metrics["auto_document_type_error"] = "classify_failed"

        # Categorize extracted text (best-effort; never blocks parse).
        # Passport extract must NOT depend on categorize succeeding — otherwise
        # Personal Info / Document Details panels stay empty on Review Scan.
        type_id_u = str(doc.document_type_id or "").strip().upper()
        is_passport = document_looks_like_passport(
            document_type_id=doc.document_type_id,
            original_filename=doc.original_filename,
            extracted_text=text,
        )
        if is_passport and type_id_u != "PASSPORT":
            from app.constants.scanx import DOCUMENT_TYPE_TO_SUBFOLDER

            doc.document_type_id = "PASSPORT"
            type_id_u = "PASSPORT"
            sub = DOCUMENT_TYPE_TO_SUBFOLDER.get("PASSPORT")
            if sub:
                doc.subfolder = sub
        categorized: dict[str, Any] | None = None
        try:
            categorized = categorize_document_fields(
                text=text,
                original_filename=doc.original_filename,
                document_type_id=doc.document_type_id,
                page_count=page_count,
                content_type=doc.content_type,
                byte_size=doc.byte_size,
                use_llm_fields=not is_passport,
            )
        except Exception:
            logger.debug(
                "ScanX categorize skipped doc_id=%s", document_id, exc_info=True
            )
            metrics["categories_error"] = "categorize_failed"
            categorized = None

        if is_passport:
            try:
                from app.services.scanx_passport import (
                    attach_passport_to_fields,
                    extract_passport_fields,
                )
                from app.services.scanx_extracted_store import (
                    persist_extracted_from_scanx,
                )

                ocr_blocks_json = metrics.get("ocr_blocks")
                passport = extract_passport_fields(
                    text or "",
                    ocr_blocks=ocr_blocks_json
                    if isinstance(ocr_blocks_json, list)
                    else None,
                    ocr_mean_confidence=(
                        float(metrics["ocr_mean_confidence"])
                        if isinstance(metrics.get("ocr_mean_confidence"), (int, float))
                        else None
                    ),
                )
                preferred_mrz = metrics.get("passport_mrz_string")
                if (
                    isinstance(preferred_mrz, str)
                    and "\n" in preferred_mrz
                    and (
                        not passport.get("mrz_string")
                        or "\n" not in str(passport.get("mrz_string") or "")
                    )
                ):
                    passport["mrz_string"] = preferred_mrz
                    passport.pop("_mrz_incomplete", None)
                base = (
                    categorized
                    if isinstance(categorized, dict)
                    else {"version": 1}
                )
                categorized = attach_passport_to_fields(base, passport)
                doc.extracted_fields_json = categorized
                metrics["categories_count"] = len(
                    categorized.get("categories") or []
                )
                metrics["passport_extracted"] = True
                metrics["passport_low_confidence"] = bool(
                    passport.get("is_low_confidence")
                )
                metrics.pop("passport_extract_error", None)
                doc.metrics_json = metrics
                # Persist passport fields immediately with retry — do not wait for
                # a later metrics-only progress write that can drop this column.
                commit_scanx_document_with_retry(db, doc, emit=False)
                try:
                    persist_extracted_from_scanx(
                        scanx_doc=doc,
                        field_group="passport",
                        structured_data=passport,
                        is_low_confidence=bool(passport.get("is_low_confidence")),
                    )
                except Exception:
                    logger.debug(
                        "ScanX passport persist skipped doc_id=%s",
                        document_id,
                        exc_info=True,
                    )
            except Exception as exc:
                logger.warning(
                    "ScanX passport extract failed doc_id=%s: %s",
                    document_id,
                    exc,
                    exc_info=True,
                )
                metrics["passport_extract_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )[:240]
                if isinstance(categorized, dict):
                    doc.extracted_fields_json = categorized
                    metrics["categories_count"] = len(
                        categorized.get("categories") or []
                    )
                elif doc.extracted_fields_json is None:
                    metrics.pop("categories_count", None)
                doc.metrics_json = metrics
                commit_scanx_document_with_retry(db, doc, emit=False)
        elif categorized is not None:
            try:
                # Merge table-extract subjects (PDF/DOCX) + LLM assist into categorizer.
                doc_id = int(doc.id)
                db, doc, live = _resolve_subjects_releasing_db(
                    db,
                    doc_id,
                    text,
                    use_llm=True,
                    prior_subjects=prefetched_subjects,
                    doc=doc,
                    metrics=metrics,
                    steps=steps,
                )
                if not doc:
                    return {"ok": False, "error": "not_found_after_subjects"}
                # Prefer OCR-structured marks from metrics when present.
                ocr_marks_subjects: list[dict[str, str]] = []
                raw_marks = metrics.get("marks") if isinstance(metrics, dict) else None
                if isinstance(raw_marks, list) and raw_marks:
                    ocr_marks_subjects = [
                        marks_row_to_subject(m)
                        for m in raw_marks
                        if isinstance(m, dict)
                    ]
                # live already merges prior_subjects — do not pass prefetched again.
                merged = merge_subjects(
                    quality_subjects(list(categorized.get("subjects") or [])),
                    ocr_marks_subjects,
                    live,
                )
                if merged:
                    categorized = attach_marks_schema(dict(categorized), merged)
                    # Ensure Academic category lists Subject rows for the UI.
                    cats = list(categorized.get("categories") or [])
                    academic = next(
                        (c for c in cats if c.get("id") == "academic"), None
                    )
                    subject_items = [format_subject_item(s) for s in merged]
                    if academic is None:
                        cats.append(
                            {
                                "id": "academic",
                                "label": "Academic / credentials",
                                "items": subject_items,
                            }
                        )
                        categorized["categories"] = cats
                    else:
                        existing = [
                            i
                            for i in (academic.get("items") or [])
                            if (i.get("label") or "") != "Subject"
                        ]
                        academic["items"] = existing + subject_items
                        categorized["categories"] = cats
                    metrics["marks"] = categorized.get("marks") or []
                    metrics["marks_count"] = len(metrics["marks"])
                    metrics["subjects_count"] = len(merged)
                doc.extracted_fields_json = categorized
                metrics["categories_count"] = len(
                    categorized.get("categories") or []
                )
                if categorized.get("subjects") and "subjects_count" not in metrics:
                    metrics["subjects_count"] = len(categorized["subjects"])
                # Persist marks_table group when structured marks exist.
                marks_payload = categorized.get("marks")
                if isinstance(marks_payload, list) and marks_payload:
                    from app.services.scanx_extracted_store import (
                        persist_extracted_from_scanx,
                    )

                    persist_extracted_from_scanx(
                        scanx_doc=doc,
                        field_group="marks_table",
                        structured_data={"marks": marks_payload},
                    )
            except Exception:
                logger.debug(
                    "ScanX categorize/subjects skipped doc_id=%s",
                    document_id,
                    exc_info=True,
                )
                metrics["categories_error"] = "categorize_failed"
        else:
            doc.extracted_fields_json = None
            metrics.pop("categories_count", None)
            if "categories_error" not in metrics:
                metrics["categories_error"] = "categorize_empty"

        extract_complete_note = f"{len(embed_source)} chars ({extract_ms} ms)"
        if extract_note == "ocr_ok":
            extract_complete_note = (
                f"OCR ok — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note == "docx_ocr_ok":
            extract_complete_note = (
                f"DOCX embedded OCR ok — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note == "docx_native+ocr":
            extract_complete_note = (
                f"DOCX native+OCR merge — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note == "pdf_ocr_ok":
            extract_complete_note = (
                f"PDF image OCR ok — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note == "pdf_native":
            extract_complete_note = (
                f"PDF text ok — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note in {"ocr_empty", "docx_ocr_empty", "pdf_ocr_empty"}:
            extract_complete_note = "OCR found no readable text — manual review"
        elif extract_note in {"ocr_timeout", "docx_ocr_timeout", "pdf_ocr_timeout"}:
            extract_complete_note = "OCR timed out — manual review"
        elif extract_note in {"ocr_failed", "docx_ocr_failed", "pdf_ocr_failed"}:
            extract_complete_note = "OCR failed — manual review"
        elif extract_note in {
            "ocr_unavailable",
            "docx_ocr_unavailable",
            "pdf_ocr_unavailable",
        }:
            extract_complete_note = (
                "OCR engine missing — install paddleocr+paddlepaddle or rapidocr"
            )
        elif extract_note == "docx_native":
            extract_complete_note = (
                f"DOCX text ok — {len(embed_source)} chars ({extract_ms} ms)"
            )
        elif extract_note in {"pdf_text_empty", "docx_no_page_cap"}:
            extract_complete_note = "No native text — manual review"
        # Surface OCR outcome on the review panel (extract step still marks complete).
        if not (embed_source or "").strip() and extract_note:
            metrics["counsellor_note"] = extract_complete_note
            if metrics.get("ocr_fallback_reason"):
                metrics["counsellor_note"] = (
                    f"{extract_complete_note} ({metrics['ocr_fallback_reason']})"
                )
        elif embed_source:
            metrics.pop("counsellor_note", None)
        steps = set_step(
            steps,
            "extract",
            STEP_STATUS_COMPLETE,
            note=extract_complete_note,
        )
        steps = set_step(
            steps,
            "chunk",
            STEP_STATUS_IN_PROGRESS,
            note="Chunking text…",
        )
        metrics = _persist_progress(db, doc, metrics, steps)

        # Replace prior chunks on re-process — persist text chunks first (no embed wait).
        db.query(ScanxDocumentChunk).filter(
            ScanxDocumentChunk.document_id == doc.id
        ).delete()

        chunks = chunk_text(embed_source) if embed_source else []
        chunk_rows: list[ScanxDocumentChunk] = []
        for idx, chunk in enumerate(chunks):
            row = ScanxDocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                chunk_text=chunk,
                embedding=None,
                embedding_dimensions=None,
                embedding_model=None,
                source_text_hash=None,
            )
            db.add(row)
            chunk_rows.append(row)

        metrics["chunk_count"] = len(chunks)
        metrics["embedded_count"] = 0
        steps = set_step(
            steps,
            "chunk",
            STEP_STATUS_COMPLETE,
            note=f"{len(chunks)} chunk(s)",
        )

        # Advance past extract+chunk into finalize/embed so % never stalls on embeds.
        steps = set_step(
            steps,
            "finalize",
            STEP_STATUS_IN_PROGRESS,
            note="Saving extracted text…",
        )
        metrics = apply_progress_to_metrics(metrics, steps)
        doc.metrics_json = metrics

        # Leave Parsing as soon as text is saved — embeddings are secondary.
        _finalize_status(
            doc,
            embed_source=embed_source,
            page_count=page_count,
            metrics=metrics,
            extract_note=extract_note,
        )
        steps = set_step(
            steps,
            "finalize",
            STEP_STATUS_COMPLETE,
            note=f"Status → {doc.status}",
        )
        if chunks:
            steps = set_step(
                steps,
                "embed",
                STEP_STATUS_IN_PROGRESS,
                note="Embedding chunks (optional, timed)…",
            )
        else:
            steps = set_step(
                steps,
                "embed",
                STEP_STATUS_SKIPPED,
                note="No text chunks to embed",
            )
        metrics = apply_progress_to_metrics(metrics, steps)
        doc.metrics_json = metrics
        commit_scanx_document_with_retry(db, doc, emit=True)
        # Cloudflare archival must not gate Review Scan — fire after extract is saved.
        try:
            _schedule_post_ocr_r2_archive(doc, metrics)
        except Exception:
            logger.warning(
                "ScanX deferred R2 archive schedule failed doc_id=%s",
                document_id,
                exc_info=True,
            )
        leave_parsing_ms = int((time.perf_counter() - t0) * 1000)
        metrics["leave_parsing_ms"] = leave_parsing_ms
        logger.info(
            "ScanX left Parsing doc_id=%s status=%s extract_ms=%s leave_parsing_ms=%s "
            "chars=%s chunks=%s progress=%s",
            document_id,
            doc.status,
            extract_ms,
            leave_parsing_ms,
            len(embed_source),
            len(chunks),
            metrics.get("progress_percent"),
        )

        # Best-effort embeddings with short budget (does not re-enter Parsing).
        embed_stats: dict[str, Any] = {
            "chunk_count": len(chunks),
            "embedded_count": 0,
            "embeddings_note": None if not chunks else "embeddings_skipped_empty",
        }
        if chunks:
            t_embed = time.perf_counter()
            doc_id = int(doc.id)
            # Ollama embed HTTP must not pin a pool connection for the budget window.
            _release_job_db(db)
            embedded, embed_stats = embed_chunks_best_effort(chunks)
            db, doc = _reopen_job_db(doc_id)
            if not doc:
                return {"ok": False, "error": "not_found_after_embed"}
            # Refresh chunk ORM rows after reopen
            chunk_rows = (
                db.query(ScanxDocumentChunk)
                .filter(ScanxDocumentChunk.document_id == doc.id)
                .order_by(ScanxDocumentChunk.chunk_index.asc())
                .all()
            )
            by_idx = {r["chunk_index"]: r for r in embedded}
            for orm_row in chunk_rows:
                data = by_idx.get(orm_row.chunk_index)
                if not data:
                    continue
                orm_row.embedding = data.get("embedding")
                orm_row.embedding_dimensions = data.get("embedding_dimensions")
                orm_row.embedding_model = data.get("embedding_model")
                orm_row.source_text_hash = data.get("source_text_hash")
            embed_ms = int((time.perf_counter() - t_embed) * 1000)
            embed_stats["embed_wall_ms"] = embed_ms

            note = embed_stats.get("embeddings_note") or "embeddings_done"
            if note == "embeddings_ok":
                steps = set_step(
                    steps,
                    "embed",
                    STEP_STATUS_COMPLETE,
                    note=f"{embed_stats.get('embedded_count', 0)} embedded ({embed_ms} ms)",
                )
            elif note == "embeddings_pending":
                steps = set_step(
                    steps,
                    "embed",
                    STEP_STATUS_COMPLETE,
                    note=(
                        f"Partial/timed out — {embed_stats.get('embedded_count', 0)}/"
                        f"{len(chunks)} embedded; text ready for review"
                    ),
                )
            elif note == "embeddings_failed":
                steps = set_step(
                    steps,
                    "embed",
                    STEP_STATUS_FAILED,
                    note=(
                        embed_stats.get("embed_error")
                        or "Embeddings failed — extracted text is ready"
                    ),
                )
            else:
                steps = set_step(
                    steps,
                    "embed",
                    STEP_STATUS_SKIPPED,
                    note=str(note),
                )

        metrics.update(
            {
                "chunk_count": embed_stats.get("chunk_count", len(chunks)),
                "embedded_count": embed_stats.get("embedded_count", 0),
                "embeddings_note": embed_stats.get("embeddings_note"),
                "embed_elapsed_ms": embed_stats.get("embed_elapsed_ms"),
                "embed_failed": embed_stats.get("embed_failed"),
                "embed_skipped_budget": embed_stats.get("embed_skipped_budget"),
                "embed_error": embed_stats.get("embed_error"),
                "embed_wall_ms": embed_stats.get("embed_wall_ms"),
                "total_ms": int((time.perf_counter() - t0) * 1000),
            }
        )
        if embed_stats.get("embeddings_note") in {"embeddings_failed", "embeddings_pending"}:
            metrics["counsellor_note"] = (
                "Embeddings pending/failed — extracted text is ready for review."
            )
        metrics = apply_progress_to_metrics(metrics, steps)
        # Ensure bar reaches 100 once pipeline finished (failed embed still counts).
        if doc.status != STATUS_PARSING:
            metrics["progress_percent"] = 100
            metrics["current_step_label"] = None
        doc.metrics_json = metrics
        commit_scanx_document_with_retry(db, doc, emit=True)

        return {
            "ok": True,
            "document_id": doc.id,
            "status": doc.status,
            "chunks": len(chunks),
            "embedded": embed_stats.get("embedded_count", 0),
            "extracted_chars": len(embed_source),
            "leave_parsing_ms": leave_parsing_ms,
            "total_ms": metrics.get("total_ms"),
            "embeddings_note": embed_stats.get("embeddings_note"),
            "progress_percent": metrics.get("progress_percent"),
        }
    except ScanxJobCancelled:
        logger.info("ScanX job cancelled doc_id=%s", document_id)
        return {"ok": False, "cancelled": True}
    except Exception as exc:
        logger.exception("ScanX worker crashed doc_id=%s", document_id)
        record_exception_event_isolated(
            severity="critical",
            source="scanx",
            message=f"ScanX worker crash for document {document_id}",
            category="scanx_worker",
            exception_type=type(exc).__name__,
            related_resource="scanx_document",
            related_id=str(document_id),
            details=[str(exc)[:500]],
        )
        try:
            safe_close_session(db)
        except Exception:
            pass
        if should_dispose_pool_for_error(exc):
            dispose_db_pool(reason=f"scanx worker crash: {type(exc).__name__}")
        # Fresh session — job session is often poisoned after ConnectionTimeout.
        fail_db = SessionLocal()
        try:
            try:
                ensure_db_connection(fail_db)
            except Exception as reconnect_exc:
                if should_dispose_pool_for_error(reconnect_exc):
                    dispose_db_pool(reason="scanx fail-path reconnect")
                safe_close_session(fail_db)
                fail_db = SessionLocal()
            doc = (
                fail_db.query(ScanxDocument)
                .filter(ScanxDocument.id == int(document_id))
                .first()
            )
            if doc:
                metrics = dict(doc.metrics_json or {})
                steps = _ensure_steps(metrics)
                active = metrics.get("current_step_id") or "extract"
                err_note = f"{type(exc).__name__}: {exc}"[:200]
                steps = set_step(
                    steps,
                    str(active),
                    STEP_STATUS_FAILED,
                    note=err_note,
                )
                metrics = apply_progress_to_metrics(metrics, steps)
                metrics["pipeline_error"] = err_note
                # File was already fetched / classified / enhanced → not "damaged".
                file_accepted = bool(
                    metrics.get("fetch_ms") is not None
                    or metrics.get("doc_kind")
                    or metrics.get("enhance_applied")
                    or metrics.get("dpi_before") is not None
                    or metrics.get("classify_ms") is not None
                )
                if file_accepted:
                    doc.status = STATUS_ACTION_REQUIRED
                    doc.error_code = "M16"
                    metrics["counsellor_note"] = (
                        f"Processing error after enhance/classify — {err_note}. "
                        "Use Re-process."
                    )
                else:
                    doc.status = STATUS_RED_FLAG
                    doc.error_code = "M7"
                doc.metrics_json = metrics
                fail_db.commit()
                _emit_status(doc)
        except Exception:
            logger.exception(
                "ScanX fail-path could not mark red_flag doc_id=%s", document_id
            )
        finally:
            safe_close_session(fail_db)
        return {
            "ok": False,
            "error": type(exc).__name__,
            "detail": str(exc)[:300],
        }
    finally:
        unbind_job()
        try:
            safe_close_session(db)
        except Exception:
            pass
