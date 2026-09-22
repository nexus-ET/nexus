"""ScanX CRM API — document upload, status, list, review (v1; no mobile)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, defer, load_only

from app.api import deps
from app.config import settings
from app.models.lead import Lead  # noqa: F401 — ensure FK metadata for ScanxDocument commits
from app.constants.scanx import (
    CONCURRENT_UPLOAD_CAP,
    DOCUMENT_TYPE_LABELS,
    DOCUMENT_TYPE_TO_SUBFOLDER,
    MESSAGE_CATALOG,
    SOURCE_CRM,
    STATUS_ACTION_REQUIRED,
    STATUS_LABELS,
    STATUS_PARSING,
    STATUS_UPLOADING,
    format_message,
)
from app.db.database import get_db
from app.models.lead import Lead
from app.models.scanx import ScanxDocument, ScanxDocumentChunk
from app.models.user import User
from app.services.audit_service import log_action
from app.services.scanx_upload_guard import (
    find_inflight_same_filename,
    normalize_scanx_filename,
)
from app.services.scanx_progress import (
    apply_progress_to_metrics,
    initial_progress_steps,
    progress_fields_from_metrics,
)
from app.services.scanx_queue import (
    rescue_stale_parsing_document,
    rescue_stale_waiting_document,
    schedule_process_document,
)
from app.services.scanx_cancel import ScanxCancelResult, cancel_scanx_document
from app.services.scanx_storage import (
    collect_scanx_document_storage_keys,
    delete_scanx_object,
    delete_scanx_objects,
    fetch_scanx_bytes,
    presign_scanx_download,
    resolve_enhanced_preview_key,
    store_scanx_bytes_local,
)
from app.services.scanx_validation import (
    build_r2_key,
    build_source_page_r2_key,
    content_sha256,
    human_file_size,
    max_file_size_bytes,
    max_pages,
    resolve_subfolder,
    scanx_error,
    validate_mime_and_size,
    validate_pages_for_content,
)
from app.services.websocket_service import broadcast_nexus_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanx", tags=["ScanX"])

DOCUMENT_READINESS_ROUTE = "/students/document-readiness"


class ScanxConfigResponse(BaseModel):
    max_file_size_bytes: int
    max_file_size_label: str
    max_pages: int
    r2_key_root: str
    concurrent_upload_cap: int
    document_types: list[dict[str, str]]
    statuses: dict[str, str]
    message_catalog: dict[str, dict[str, str]]
    preupload_rules: list[str]
    # Image OCR: primary + fallback (see SCANX_OCR_ENGINE / SCANX_OCR_FALLBACK)
    ocr_engine: str = "rapid"
    ocr_fallback: str | None = "paddle"


class ScanxProgressStepOut(BaseModel):
    id: str
    label: str
    weight: int = 0
    status: str
    status_label: str | None = None
    note: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ScanxDocumentOut(BaseModel):
    id: int
    doc_uuid: str
    lead_id: int
    uploader_user_id: int | None = None
    source: str
    document_type_id: str
    document_type_label: str | None = None
    subfolder: str
    original_filename: str
    status: str
    status_label: str
    content_sha256: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    page_count: int | None = None
    document_group_id: str | None = None
    source_page_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # Live parse pipeline progress (from metrics_json)
    progress_percent: int | None = None
    progress_steps: list[ScanxProgressStepOut] | None = None
    current_step_id: str | None = None
    current_step_label: str | None = None
    # Ops only — not primary UI label
    r2_key: str | None = None
    upload_id: str | None = None


class ScanxSourcePageOut(BaseModel):
    page_index: int = 0
    original_filename: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    file_url: str | None = None
    viewer_url: str | None = None


class ScanxUploadResponse(BaseModel):
    document: ScanxDocumentOut
    job_id: str | None = None
    enqueue_mode: str | None = None


class ScanxCategoryItemOut(BaseModel):
    label: str
    value: str


class ScanxCategoryOut(BaseModel):
    id: str
    label: str
    items: list[ScanxCategoryItemOut] = Field(default_factory=list)


class ScanxEnhancedPageOut(BaseModel):
    page_index: int = 0
    file_url: str
    viewer_url: str | None = None


class ScanxReviewResponse(BaseModel):
    document: ScanxDocumentOut
    extracted_text: str | None = None
    extracted_fields: dict[str, Any] | None = Field(
        default=None,
        description="Structured OCR/text categories (version + categories[]).",
    )
    subjects: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Subject rows for counsellor Dynamic Table: name/subject, theory?, "
            "practical?/prac?, total/marks, words?, grade? — Theory/Prac are "
            "per-subject columns (also mirrored on extracted_fields.marks)."
        ),
    )
    categories: list[ScanxCategoryOut] = Field(
        default_factory=list,
        description="Normalized category panels for counsellor review UI.",
    )
    chunk_count: int = 0
    embedded_count: int = 0
    viewer_url: str | None = Field(
        default=None, description="Optional short-lived R2 URL when available."
    )
    file_url: str | None = Field(
        default=None,
        description="Auth-backed CRM stream path (always set when file exists).",
    )
    enhanced_viewer_url: str | None = Field(
        default=None,
        description="Optional short-lived R2 URL for OpenCV enhanced preview (page 0).",
    )
    enhanced_file_url: str | None = Field(
        default=None,
        description="Auth-backed stream for enhanced preview JPEG when stored (page 0).",
    )
    enhanced_pages: list[ScanxEnhancedPageOut] = Field(
        default_factory=list,
        description="Per-page OpenCV enhanced preview URLs for multi-page documents.",
    )
    source_pages: list[ScanxSourcePageOut] = Field(
        default_factory=list,
        description="Ordered original page assets for multi-image document groups.",
    )
    metrics: dict[str, Any] | None = None
    review_prompt: str | None = None
    # OCR spatial blocks + confidence flags (also mirrored in metrics).
    ocr_blocks: list[dict[str, Any]] | None = Field(
        default=None,
        description="Spatially ordered OCR text blocks with boxes and confidence.",
    )
    requires_manual_review: bool | None = Field(
        default=None,
        description="True when any OCR block confidence is below 0.80.",
    )
    ocr_low_confidence_count: int | None = None
    ocr_block_count: int | None = None
    ocr_mean_confidence: float | None = None
    ocr_min_confidence: float | None = None
    ocr_low_confidence_block_ids: list[str] | None = None
    ocr_confidence_threshold: float | None = None


class ScanxDeleteResponse(BaseModel):
    ok: bool = True
    document_id: int
    storage_removed: bool = False


class ScanxCancelResponse(BaseModel):
    ok: bool = True
    document_id: int
    cancelled: bool = True
    already_gone: bool = False
    storage_removed: bool = False


class ScanxBulkDeleteRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=200)


class ScanxBulkDeleteResponse(BaseModel):
    deleted: int
    skipped: int = 0
    ids: list[int] = Field(default_factory=list)
    storage_removed: int = 0


class ScanxReprocessResponse(BaseModel):
    document: ScanxDocumentOut
    job_id: str | None = None
    enqueue_mode: str | None = None


def _categories_out(fields: Any) -> list[ScanxCategoryOut]:
    if not isinstance(fields, dict):
        return []
    raw = fields.get("categories")
    if not isinstance(raw, list):
        return []
    out: list[ScanxCategoryOut] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        items_raw = entry.get("items") if isinstance(entry.get("items"), list) else []
        items: list[ScanxCategoryItemOut] = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            items.append(
                ScanxCategoryItemOut(
                    label=str(item.get("label") or "Value").strip() or "Value",
                    value=value,
                )
            )
        out.append(
            ScanxCategoryOut(
                id=str(entry.get("id")),
                label=str(entry.get("label") or entry.get("id")),
                items=items,
            )
        )
    return out


# Columns needed for list / status cards — never pull OCR text or fat JSON blobs.
_SCANX_LIST_LOAD_ONLY = (
    ScanxDocument.id,
    ScanxDocument.doc_uuid,
    ScanxDocument.lead_id,
    ScanxDocument.uploader_user_id,
    ScanxDocument.source,
    ScanxDocument.document_type_id,
    ScanxDocument.subfolder,
    ScanxDocument.original_filename,
    ScanxDocument.status,
    ScanxDocument.content_sha256,
    ScanxDocument.content_type,
    ScanxDocument.byte_size,
    ScanxDocument.page_count,
    ScanxDocument.error_code,
    ScanxDocument.created_at,
    ScanxDocument.updated_at,
    ScanxDocument.r2_key,
    ScanxDocument.upload_id,
)

# Progress keys only — excludes ocr_blocks / marks / table_regions / etc.
_LIST_METRICS_KEYS = (
    "progress_percent",
    "progress_steps",
    "current_step_id",
    "current_step_label",
    "progress_updated_at",
)


def _slim_list_metrics_expr():
    """PostgreSQL: project only progress fields from metrics_json (no OCR blobs)."""
    m = ScanxDocument.metrics_json
    args: list[Any] = []
    for key in _LIST_METRICS_KEYS:
        args.extend([key, m[key]])
    return func.jsonb_build_object(*args)


def _normalize_list_metrics(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {k: raw[k] for k in _LIST_METRICS_KEYS if k in raw}
    return {}


def _background_rescue_parsing_docs(document_ids: list[int]) -> None:
    """Stale-parse rescue must not block GET /documents (Redis/DB can stall)."""
    for document_id in document_ids:
        try:
            if rescue_stale_waiting_document(document_id):
                continue
            rescue_stale_parsing_document(document_id)
        except Exception:
            # Rescue is best-effort; list already returned metadata.
            pass


def _doc_out(
    doc: ScanxDocument,
    *,
    metrics: dict[str, Any] | None = None,
) -> ScanxDocumentOut:
    err_msg = None
    if doc.error_code:
        err_msg = format_message(
            doc.error_code,
            max_size_label=human_file_size(max_file_size_bytes()),
            max_pages=max_pages(),
        )
    if metrics is None:
        metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
    progress = progress_fields_from_metrics(metrics)
    steps_out: list[ScanxProgressStepOut] | None = None
    raw_steps = progress.get("progress_steps")
    if isinstance(raw_steps, list):
        steps_out = []
        for s in raw_steps:
            if not isinstance(s, dict) or not s.get("id"):
                continue
            steps_out.append(
                ScanxProgressStepOut(
                    id=str(s.get("id")),
                    label=str(s.get("label") or s.get("id")),
                    weight=int(s.get("weight") or 0),
                    status=str(s.get("status") or "pending"),
                    status_label=s.get("status_label"),
                    note=s.get("note"),
                    started_at=s.get("started_at"),
                    finished_at=s.get("finished_at"),
                )
            )
    source_pages = doc.source_pages if isinstance(doc.source_pages, list) else None
    source_page_count = len(source_pages) if source_pages else None
    return ScanxDocumentOut(
        id=doc.id,
        doc_uuid=str(doc.doc_uuid),
        lead_id=doc.lead_id,
        uploader_user_id=doc.uploader_user_id,
        source=doc.source,
        document_type_id=doc.document_type_id,
        document_type_label=DOCUMENT_TYPE_LABELS.get(doc.document_type_id),
        subfolder=doc.subfolder,
        original_filename=doc.original_filename,
        status=doc.status,
        status_label=STATUS_LABELS.get(doc.status, doc.status),
        content_sha256=doc.content_sha256,
        content_type=doc.content_type,
        byte_size=doc.byte_size,
        page_count=doc.page_count,
        document_group_id=str(doc.document_group_id) if doc.document_group_id else None,
        source_page_count=source_page_count,
        error_code=doc.error_code,
        error_message=err_msg,
        created_at=doc.created_at.isoformat() if doc.created_at else None,
        updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
        progress_percent=progress.get("progress_percent"),
        progress_steps=steps_out,
        current_step_id=progress.get("current_step_id"),
        current_step_label=progress.get("current_step_label"),
        r2_key=doc.r2_key,
        upload_id=doc.upload_id,
    )


@router.get("/config", response_model=ScanxConfigResponse)
def get_scanx_config():
    """Pure settings read — no DB.

    Auth + page RBAC are enforced solely by NavigationRBACMiddleware
    (``/api/v1/scanx`` → ``/students/document-readiness``). Skipping
    ``get_current_active_user`` here avoids a second user lookup over a slow
    tunnel (middleware already validated the bearer token).
    """
    types = [
        {
            "id": type_id,
            "label": DOCUMENT_TYPE_LABELS.get(type_id, type_id),
            "subfolder": subfolder,
        }
        for type_id, subfolder in DOCUMENT_TYPE_TO_SUBFOLDER.items()
    ]
    size_bytes = max_file_size_bytes()
    size_label = human_file_size(size_bytes)
    pages = max_pages()
    rules = [
        "Supported formats: PDF, DOCX, PNG, JPEG, TIFF.",
        f"Max file size: {size_label}.",
        f"Max page count: {pages} pages for PDF; DOCX limited by file size.",
        "Prefer clear, readable scans; images ideally ≥150 DPI.",
        "Password-protected or encrypted PDFs are not accepted.",
        "File must not be corrupted or unreadable.",
        "Choose the student (lead) before uploading.",
        "Choose document type before upload.",
        f"Up to {CONCURRENT_UPLOAD_CAP} uploads can be in progress at once for your account.",
        "Uploaded files are tagged as from Nexus CRM.",
    ]
    from app.services.scanx_ocr import configured_ocr_engine, configured_ocr_fallback

    return ScanxConfigResponse(
        max_file_size_bytes=size_bytes,
        max_file_size_label=size_label,
        max_pages=pages,
        r2_key_root=(settings.SCANX_R2_KEY_ROOT or "STUDENTS").strip() or "STUDENTS",
        concurrent_upload_cap=CONCURRENT_UPLOAD_CAP,
        document_types=types,
        statuses=dict(STATUS_LABELS),
        message_catalog=dict(MESSAGE_CATALOG),
        preupload_rules=rules,
        ocr_engine=configured_ocr_engine(),
        ocr_fallback=configured_ocr_fallback(),
    )


@router.get("/documents", response_model=list[ScanxDocumentOut])
def list_scanx_documents(
    background_tasks: BackgroundTasks,
    lead_id: int = Query(..., ge=1),
):
    """List document metadata + parse progress only.

    Auth + page RBAC are enforced by NavigationRBACMiddleware
    (``/api/v1/scanx`` → ``/students/document-readiness``). Skipping a second
    ``require_page_access`` / ``get_db`` dependency avoids an extra checkout while
    ScanX OCR heartbeats already contend for the SSH-tunnel pool.

    Up to two short retries on connectivity / pool wait — do not dispose the
    shared pool on QueuePool timeout (that reconnect storm 503s Document Readiness).
    """
    from app.db.database import (
        DB_TEMPORARILY_BUSY_DETAIL,
        SessionLocal,
        db_temporarily_busy_headers,
        dispose_db_pool,
        safe_close_session,
        should_dispose_pool_for_error,
    )
    from app.services.scanx_jobs import _is_db_connectivity_error

    last_exc: BaseException | None = None
    retry_delays = (0.5, 1.5)
    for attempt in range(3):
        db = SessionLocal()
        try:
            dialect = getattr(getattr(db, "bind", None), "dialect", None)
            dialect_name = getattr(dialect, "name", "") or ""

            if dialect_name == "postgresql":
                query = (
                    db.query(ScanxDocument, _slim_list_metrics_expr().label("metrics_slim"))
                    .options(load_only(*_SCANX_LIST_LOAD_ONLY))
                    .filter(ScanxDocument.lead_id == lead_id)
                    .order_by(ScanxDocument.created_at.desc())
                    .limit(200)
                )
                pairs = query.all()
                parsing_ids = [
                    doc.id for doc, _metrics in pairs if doc.status == STATUS_PARSING
                ]
                if parsing_ids:
                    background_tasks.add_task(
                        _background_rescue_parsing_docs, parsing_ids
                    )
                return [
                    _doc_out(doc, metrics=_normalize_list_metrics(metrics_slim))
                    for doc, metrics_slim in pairs
                ]

            rows = (
                db.query(ScanxDocument)
                .options(
                    defer(ScanxDocument.extracted_text),
                    defer(ScanxDocument.extracted_fields_json),
                )
                .filter(ScanxDocument.lead_id == lead_id)
                .order_by(ScanxDocument.created_at.desc())
                .limit(200)
                .all()
            )
            parsing_ids = [row.id for row in rows if row.status == STATUS_PARSING]
            if parsing_ids:
                background_tasks.add_task(_background_rescue_parsing_docs, parsing_ids)
            return [
                _doc_out(row, metrics=_normalize_list_metrics(row.metrics_json))
                for row in rows
            ]
        except Exception as exc:
            last_exc = exc
            try:
                db.rollback()
            except Exception:
                pass
            if not _is_db_connectivity_error(exc) or attempt >= 2:
                break
            logger.warning(
                "ScanX list documents retry lead_id=%s attempt=%s: %s",
                lead_id,
                attempt + 1,
                exc,
            )
            if should_dispose_pool_for_error(exc):
                dispose_db_pool(reason=f"scanx list documents: {type(exc).__name__}")
            time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
        finally:
            safe_close_session(db)

    # Prefer a fast 503 over hanging until the SPA list AbortError.
    if last_exc is not None:
        logger.warning(
            "ScanX list documents failed lead_id=%s: %s",
            lead_id,
            last_exc,
        )
    raise HTTPException(
        status_code=503,
        detail=DB_TEMPORARILY_BUSY_DETAIL,
        headers=db_temporarily_busy_headers(),
    )


@router.post("/documents/bulk-delete", response_model=ScanxBulkDeleteResponse)
@log_action("scanx_bulk_delete_documents", "scanx_document")
def bulk_delete_scanx_documents(
    payload: ScanxBulkDeleteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Hard-delete many documents (DB cascade + async R2/local cleanup)."""
    _ = current_user
    return _hard_delete_scanx_documents(
        db,
        payload.ids,
        background_tasks=background_tasks,
        defer_storage=True,
    )


@router.get("/documents/{document_id}", response_model=ScanxDocumentOut)
def get_scanx_document(
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    doc = db.query(ScanxDocument).filter(ScanxDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_out(doc)


@router.get("/documents/{document_id}/review", response_model=ScanxReviewResponse)
def get_scanx_review(
    document_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    doc = db.query(ScanxDocument).filter(ScanxDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = (
        db.query(ScanxDocumentChunk)
        .filter(ScanxDocumentChunk.document_id == doc.id)
        .all()
    )
    signed = None
    if doc.r2_key:
        try:
            signed = presign_scanx_download(doc.r2_key)
        except Exception:
            signed = None
    file_url = f"/api/v1/scanx/documents/{doc.id}/file" if doc.r2_key else None
    metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else None
    enhanced_key = None
    if isinstance(metrics, dict):
        enhanced_key = resolve_enhanced_preview_key(metrics, page_index=0)
    enhanced_signed = None
    enhanced_file_url = None
    enhanced_pages_out: list[ScanxEnhancedPageOut] = []
    if enhanced_key:
        enhanced_file_url = f"/api/v1/scanx/documents/{doc.id}/enhanced?page=0"
        try:
            enhanced_signed = presign_scanx_download(enhanced_key)
        except Exception:
            enhanced_signed = None
    if isinstance(metrics, dict):
        pages_meta = metrics.get("enhanced_preview_pages")
        if isinstance(pages_meta, list) and pages_meta:
            for entry in pages_meta:
                if not isinstance(entry, dict):
                    continue
                try:
                    pidx = int(entry.get("page_index", 0))
                except (TypeError, ValueError):
                    continue
                page_key = entry.get("key")
                if not isinstance(page_key, str) or not page_key.strip():
                    page_key = resolve_enhanced_preview_key(metrics, page_index=pidx)
                if not page_key:
                    continue
                page_signed = None
                try:
                    page_signed = presign_scanx_download(page_key)
                except Exception:
                    page_signed = None
                enhanced_pages_out.append(
                    ScanxEnhancedPageOut(
                        page_index=pidx,
                        file_url=f"/api/v1/scanx/documents/{doc.id}/enhanced?page={pidx}",
                        viewer_url=page_signed,
                    )
                )
        elif enhanced_file_url:
            enhanced_pages_out.append(
                ScanxEnhancedPageOut(
                    page_index=0,
                    file_url=enhanced_file_url,
                    viewer_url=enhanced_signed,
                )
            )

    source_pages_out: list[ScanxSourcePageOut] = []
    raw_source_pages = doc.source_pages if isinstance(doc.source_pages, list) else None
    if raw_source_pages:
        for entry in raw_source_pages:
            if not isinstance(entry, dict):
                continue
            try:
                pidx = int(entry.get("page_index", 0))
            except (TypeError, ValueError):
                continue
            page_key = entry.get("r2_key")
            if not isinstance(page_key, str) or not page_key.strip():
                if pidx == 0 and doc.r2_key:
                    page_key = doc.r2_key
                else:
                    continue
            page_signed = None
            try:
                page_signed = presign_scanx_download(page_key)
            except Exception:
                page_signed = None
            source_pages_out.append(
                ScanxSourcePageOut(
                    page_index=pidx,
                    original_filename=(
                        str(entry.get("original_filename"))
                        if entry.get("original_filename")
                        else None
                    ),
                    content_type=(
                        str(entry.get("content_type"))
                        if entry.get("content_type")
                        else None
                    ),
                    byte_size=(
                        int(entry["byte_size"])
                        if isinstance(entry.get("byte_size"), int)
                        else None
                    ),
                    file_url=f"/api/v1/scanx/documents/{doc.id}/file?page={pidx}",
                    viewer_url=page_signed,
                )
            )
    prompt = None
    if doc.status == STATUS_ACTION_REQUIRED:
        if doc.error_code in {"M14", "M15", "M16"}:
            prompt = format_message(doc.error_code)
        else:
            prompt = format_message("M12")
    elif doc.error_code:
        prompt = format_message(doc.error_code)
    if metrics and metrics.get("counsellor_note"):
        note = str(metrics["counsellor_note"]).strip()
        if note:
            prompt = f"{prompt} {note}".strip() if prompt else note
    fields = (
        doc.extracted_fields_json
        if isinstance(doc.extracted_fields_json, dict)
        else None
    )
    # Re-parse fields + subjects from extracted_text on review so stacked OCR
    # (DOB / Roll / Group Code, Tamil 169, …) appears without re-OCR.
    # Bump when field or subject parsers improve.
    _FIELDS_BACKFILL_VERSION = 19
    review_subjects: list[dict[str, str]] = []
    text = (doc.extracted_text or "").strip()
    type_id_u = str(doc.document_type_id or "").strip().upper()
    from app.services.scanx_jobs import (
        commit_scanx_document_with_retry,
        document_looks_like_passport,
    )

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
    if text:
        try:
            # Re-run auto type classify when still UNKNOWN / AUTO.
            if type_id_u in {"", "UNKNOWN", "AUTO"}:
                from app.constants.scanx import DOCUMENT_TYPE_TO_SUBFOLDER
                from app.services.scanx_type_classify import classify_document_type

                type_hit = classify_document_type(
                    text,
                    filename=doc.original_filename,
                    prior_type_id=None,
                )
                metrics_for_type = dict(metrics) if isinstance(metrics, dict) else {}
                metrics_for_type.update(type_hit.to_metrics())
                if type_hit.document_type_id:
                    doc.document_type_id = type_hit.document_type_id
                    sub = DOCUMENT_TYPE_TO_SUBFOLDER.get(type_hit.document_type_id)
                    if sub:
                        doc.subfolder = sub
                    type_id_u = type_hit.document_type_id
                    is_passport = document_looks_like_passport(
                        document_type_id=doc.document_type_id,
                        original_filename=doc.original_filename,
                        extracted_text=text,
                    )
                    if is_passport and type_id_u != "PASSPORT":
                        doc.document_type_id = "PASSPORT"
                        type_id_u = "PASSPORT"
                        sub = DOCUMENT_TYPE_TO_SUBFOLDER.get("PASSPORT")
                        if sub:
                            doc.subfolder = sub
                    doc.metrics_json = metrics_for_type
                    metrics = metrics_for_type
                    commit_scanx_document_with_retry(db, doc, emit=False, heal_caller=False)

            from app.services.scanx_academic_parse import (
                attach_marks_schema,
                format_subject_item,
                merge_subjects,
                quality_subjects,
                resolve_subjects_from_text,
                subjects_missing_or_empty,
            )
            from app.services.scanx_categorize import categorize_document_fields

            prior = []
            if isinstance(fields, dict) and isinstance(fields.get("subjects"), list):
                prior = [s for s in fields["subjects"] if isinstance(s, dict)]
            metrics_mut: dict[str, Any] = (
                dict(metrics) if isinstance(metrics, dict) else {}
            )
            already_checked = (
                metrics_mut.get("fields_backfill_version") == _FIELDS_BACKFILL_VERSION
            )

            if is_passport:
                from app.services.scanx_passport import (
                    attach_passport_to_fields,
                    extract_passport_fields,
                )
                from app.services.scanx_extracted_store import (
                    persist_extracted_from_scanx,
                )

                need_fields_refresh = (not already_checked) or not (
                    isinstance(fields, dict) and isinstance(fields.get("passport"), dict)
                )
                if metrics_mut.get("passport_extract_error"):
                    need_fields_refresh = True
                # Re-group into Personal / Document / MRZ / Audit / Other when older
                # payloads still use a flat identity category.
                if (
                    not need_fields_refresh
                    and isinstance(fields, dict)
                    and isinstance(fields.get("passport"), dict)
                ):
                    cats = fields.get("categories") or []
                    has_groups = any(
                        isinstance(c, dict)
                        and c.get("id")
                        in {
                            "personal_info",
                            "document_details",
                            "mrz_data",
                            "audit_ui",
                        }
                        for c in cats
                    )
                    if not has_groups:
                        need_fields_refresh = True
                if need_fields_refresh:
                    # Heuristic categorize only (no LLM) — passport schema drives
                    # Personal Info / Document Details. LLM categorize was timing
                    # out the Review Scan request before panels could populate.
                    live_fields: dict[str, Any] | None = None
                    try:
                        live_fields = categorize_document_fields(
                            text=text,
                            original_filename=doc.original_filename,
                            document_type_id=doc.document_type_id or "PASSPORT",
                            page_count=doc.page_count,
                            content_type=doc.content_type,
                            byte_size=doc.byte_size,
                            use_llm_fields=False,
                        )
                    except Exception:
                        live_fields = None
                    base = live_fields if isinstance(live_fields, dict) else (
                        dict(fields) if isinstance(fields, dict) else {"version": 1}
                    )
                    ocr_blocks_json = (
                        metrics_mut.get("ocr_blocks")
                        if isinstance(metrics_mut.get("ocr_blocks"), list)
                        else None
                    )
                    try:
                        passport = extract_passport_fields(
                            text,
                            ocr_blocks=ocr_blocks_json,
                            ocr_mean_confidence=(
                                float(metrics_mut["ocr_mean_confidence"])
                                if isinstance(
                                    metrics_mut.get("ocr_mean_confidence"), (int, float)
                                )
                                else None
                            ),
                        )
                        fields = attach_passport_to_fields(base, passport)
                        doc.extracted_fields_json = fields
                        metrics_mut["fields_backfill_version"] = _FIELDS_BACKFILL_VERSION
                        metrics_mut["passport_extracted"] = True
                        metrics_mut["passport_low_confidence"] = bool(
                            passport.get("is_low_confidence")
                        )
                        metrics_mut.pop("categories_error", None)
                        metrics_mut.pop("passport_extract_error", None)
                        doc.metrics_json = metrics_mut
                        metrics = metrics_mut
                        commit_scanx_document_with_retry(db, doc, emit=False, heal_caller=False)
                        try:
                            persist_extracted_from_scanx(
                                scanx_doc=doc,
                                field_group="passport",
                                structured_data=passport,
                                is_low_confidence=bool(
                                    passport.get("is_low_confidence")
                                ),
                            )
                        except Exception:
                            pass
                    except Exception as exc:
                        logger.warning(
                            "ScanX review passport backfill failed doc_id=%s: %s",
                            doc.id,
                            exc,
                            exc_info=True,
                        )
                        metrics_mut["passport_extract_error"] = (
                            f"{type(exc).__name__}: {exc}"
                        )[:240]
                        # Do not stamp fields_backfill_version on failure — that
                        # blocked later GETs from retrying when passport was null.
                        doc.metrics_json = metrics_mut
                        metrics = metrics_mut
                        commit_scanx_document_with_retry(db, doc, emit=False, heal_caller=False)
                review_subjects = []
            else:
                # Subjects: re-parse every review; LLM only when quality count is low.
                need_subj_llm = (
                    subjects_missing_or_empty(fields)
                    or len(quality_subjects(prior)) < 2
                )
                live_subjects = resolve_subjects_from_text(
                    text,
                    use_llm=need_subj_llm,
                    prior_subjects=None,
                )
                review_subjects = live_subjects

                # Full field re-categorize when backfill version is stale or fields thin.
                prior_field_count = 0
                if isinstance(fields, dict):
                    prior_field_count = len(fields.get("fields") or [])
                    if prior_field_count == 0:
                        for cat in fields.get("categories") or []:
                            if not isinstance(cat, dict) or cat.get("id") in {
                                "document_summary",
                                "other",
                            }:
                                continue
                            prior_field_count += len(
                                [
                                    i
                                    for i in (cat.get("items") or [])
                                    if isinstance(i, dict)
                                    and (i.get("label") or "") != "Subject"
                                ]
                            )
                need_fields_refresh = (not already_checked) or prior_field_count < 4

                if need_fields_refresh:
                    live_fields = categorize_document_fields(
                        text=text,
                        original_filename=doc.original_filename,
                        document_type_id=doc.document_type_id,
                        page_count=doc.page_count,
                        content_type=doc.content_type,
                        byte_size=doc.byte_size,
                    )
                    if isinstance(live_fields, dict):
                        fields = dict(live_fields)

                if not isinstance(fields, dict):
                    fields = {"version": 1, "categories": []}

                fields = dict(fields)
                if live_subjects:
                    merged = merge_subjects(live_subjects, quality_subjects(prior))
                    # Prefer stored marks rows when they add theory/prac/words.
                    prior_marks = []
                    if isinstance(fields.get("marks"), list):
                        prior_marks = [
                            m for m in fields["marks"] if isinstance(m, dict)
                        ]
                    if isinstance(metrics_mut.get("marks"), list):
                        prior_marks = prior_marks + [
                            m for m in metrics_mut["marks"] if isinstance(m, dict)
                        ]
                    fields = attach_marks_schema(fields, merged)
                    if prior_marks:
                        from app.services.scanx_academic_parse import marks_row_to_subject

                        fields = attach_marks_schema(
                            fields,
                            merge_subjects(
                                merged,
                                [marks_row_to_subject(m) for m in prior_marks],
                            ),
                        )
                    review_subjects = list(fields.get("subjects") or merged)
                    cats = list(fields.get("categories") or [])
                    academic = next(
                        (c for c in cats if c.get("id") == "academic"), None
                    )
                    subject_items = [format_subject_item(s) for s in review_subjects]
                    if academic is None:
                        cats.append(
                            {
                                "id": "academic",
                                "label": "Academic / credentials",
                                "items": subject_items,
                            }
                        )
                        fields["categories"] = cats
                    else:
                        existing = [
                            i
                            for i in (academic.get("items") or [])
                            if (i.get("label") or "") != "Subject"
                        ]
                        academic["items"] = existing + subject_items
                        fields["categories"] = cats
                    metrics_mut["marks"] = fields.get("marks") or []
                    metrics_mut["marks_count"] = len(metrics_mut["marks"])
                elif isinstance(fields, dict):
                    review_subjects = quality_subjects(
                        [
                            s
                            for s in (fields.get("subjects") or [])
                            if isinstance(s, dict)
                        ]
                    )
                    fields = attach_marks_schema(fields, review_subjects)

                should_persist = need_fields_refresh or subjects_missing_or_empty(
                    doc.extracted_fields_json
                    if isinstance(doc.extracted_fields_json, dict)
                    else None
                )
                if should_persist:
                    doc.extracted_fields_json = fields
                    metrics_mut["fields_backfill_version"] = _FIELDS_BACKFILL_VERSION
                    metrics_mut["subjects_backfill_version"] = _FIELDS_BACKFILL_VERSION
                    if live_subjects:
                        metrics_mut["subjects_backfill"] = len(live_subjects)
                    if need_subj_llm:
                        metrics_mut["subjects_llm_assist"] = True
                    flat = fields.get("fields") if isinstance(fields, dict) else None
                    if isinstance(flat, list):
                        metrics_mut["fields_backfill"] = len(flat)
                    doc.metrics_json = metrics_mut
                    metrics = metrics_mut
                    try:
                        db.add(doc)
                        db.commit()
                        db.refresh(doc)
                    except Exception:
                        db.rollback()
                elif not already_checked:
                    metrics_mut["fields_backfill_version"] = _FIELDS_BACKFILL_VERSION
                    doc.metrics_json = metrics_mut
                    metrics = metrics_mut
                    try:
                        db.add(doc)
                        db.commit()
                    except Exception:
                        db.rollback()
        except Exception:
            # Review must still return stored text/fields if backfill fails.
            if isinstance(fields, dict) and isinstance(fields.get("subjects"), list):
                from app.services.scanx_academic_parse import quality_subjects

                review_subjects = quality_subjects(
                    [s for s in fields["subjects"] if isinstance(s, dict)]
                )
    elif isinstance(fields, dict) and isinstance(fields.get("subjects"), list):
        from app.services.scanx_academic_parse import quality_subjects

        review_subjects = quality_subjects(
            [s for s in fields["subjects"] if isinstance(s, dict)]
        )

    ocr_blocks_out: list[dict[str, Any]] | None = None
    requires_manual_review: bool | None = None
    ocr_low_confidence_count: int | None = None
    ocr_block_count: int | None = None
    ocr_mean_confidence: float | None = None
    ocr_min_confidence: float | None = None
    ocr_low_confidence_block_ids: list[str] | None = None
    ocr_confidence_threshold: float | None = None
    if isinstance(metrics, dict):
        raw_blocks = metrics.get("ocr_blocks")
        if isinstance(raw_blocks, list):
            ocr_blocks_out = [b for b in raw_blocks if isinstance(b, dict)]
        if "requires_manual_review" in metrics:
            requires_manual_review = bool(metrics.get("requires_manual_review"))
        if metrics.get("ocr_low_confidence_count") is not None:
            try:
                ocr_low_confidence_count = int(metrics["ocr_low_confidence_count"])
            except (TypeError, ValueError):
                ocr_low_confidence_count = None
        if metrics.get("ocr_block_count") is not None:
            try:
                ocr_block_count = int(metrics["ocr_block_count"])
            except (TypeError, ValueError):
                ocr_block_count = None
        if metrics.get("ocr_mean_confidence") is not None:
            try:
                ocr_mean_confidence = float(metrics["ocr_mean_confidence"])
            except (TypeError, ValueError):
                ocr_mean_confidence = None
        if metrics.get("ocr_min_confidence") is not None:
            try:
                ocr_min_confidence = float(metrics["ocr_min_confidence"])
            except (TypeError, ValueError):
                ocr_min_confidence = None
        ids = metrics.get("ocr_low_confidence_block_ids")
        if isinstance(ids, list):
            ocr_low_confidence_block_ids = [str(x) for x in ids]
        if metrics.get("ocr_confidence_threshold") is not None:
            try:
                ocr_confidence_threshold = float(metrics["ocr_confidence_threshold"])
            except (TypeError, ValueError):
                ocr_confidence_threshold = None

    return ScanxReviewResponse(
        document=_doc_out(doc),
        extracted_text=doc.extracted_text,
        extracted_fields=fields,
        subjects=review_subjects,
        categories=_categories_out(fields),
        chunk_count=len(chunks),
        embedded_count=sum(1 for c in chunks if c.embedding),
        viewer_url=signed,
        file_url=file_url,
        enhanced_viewer_url=enhanced_signed,
        enhanced_file_url=enhanced_file_url,
        enhanced_pages=enhanced_pages_out,
        source_pages=source_pages_out,
        metrics=metrics,
        review_prompt=prompt,
        ocr_blocks=ocr_blocks_out,
        requires_manual_review=requires_manual_review,
        ocr_low_confidence_count=ocr_low_confidence_count,
        ocr_block_count=ocr_block_count,
        ocr_mean_confidence=ocr_mean_confidence,
        ocr_min_confidence=ocr_min_confidence,
        ocr_low_confidence_block_ids=ocr_low_confidence_block_ids,
        ocr_confidence_threshold=ocr_confidence_threshold,
    )


@router.get("/documents/{document_id}/file")
def download_scanx_document_file(
    document_id: int,
    page: int = Query(0, ge=0, description="0-based source page for multi-image groups"),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Stream stored bytes (R2 or local uploads/) with CRM auth — used when View has no presign."""
    doc = db.query(ScanxDocument).filter(ScanxDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    object_key = doc.r2_key
    media = (doc.content_type or "application/octet-stream").split(";")[0].strip()
    safe_name = Path(doc.original_filename or "document").name.replace('"', "")
    pages = doc.source_pages if isinstance(doc.source_pages, list) else None
    if pages and page >= 0:
        match = None
        for entry in pages:
            if not isinstance(entry, dict):
                continue
            try:
                if int(entry.get("page_index", -1)) == int(page):
                    match = entry
                    break
            except (TypeError, ValueError):
                continue
        if match and isinstance(match.get("r2_key"), str) and match["r2_key"].strip():
            object_key = match["r2_key"].strip()
            if match.get("content_type"):
                media = str(match["content_type"]).split(";")[0].strip()
            if match.get("original_filename"):
                safe_name = Path(str(match["original_filename"])).name.replace('"', "")
        elif page > 0:
            raise HTTPException(status_code=404, detail="Document page not found")

    if not object_key:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        content, ctype = fetch_scanx_bytes(object_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Document bytes not found.") from exc

    if not media or media == "application/octet-stream":
        media = (ctype or "application/octet-stream").split(";")[0].strip()
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "private, max-age=0, no-cache",
        },
    )


@router.get("/documents/{document_id}/enhanced")
def download_scanx_enhanced_preview(
    document_id: int,
    page: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """On-demand enhanced JPEG from the original upload (never a stored artifact).

    ``page`` is 0-based. Re-renders from original source frames / PDF pages and
    runs enhance in memory. Enhanced previews are not archived to Cloudflare.
    """
    from app.services.scanx_jobs import rebuild_enhanced_preview_from_original

    doc = db.query(ScanxDocument).filter(ScanxDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    metrics = doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
    page_index = max(0, int(page or 0))

    repaired_metrics = dict(metrics)
    content = rebuild_enhanced_preview_from_original(
        doc,
        repaired_metrics,
        prefer_page=page_index,
    )
    if repaired_metrics != metrics:
        doc.metrics_json = repaired_metrics
        try:
            db.commit()
        except Exception:
            db.rollback()

    if content is None:
        raise HTTPException(status_code=404, detail="Enhanced preview not available")

    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'inline; filename="enhanced_preview_p{page_index}.jpg"',
            "Cache-Control": "private, max-age=0, no-cache",
        },
    )


def _hard_delete_scanx_document(
    db: Session,
    document_id: int,
    *,
    background_tasks: BackgroundTasks | None = None,
    defer_storage: bool = False,
) -> ScanxDeleteResponse:
    """Hard-delete document row (cascades chunks) and remove R2/local object."""
    result = _hard_delete_scanx_documents(
        db,
        [document_id],
        background_tasks=background_tasks,
        defer_storage=defer_storage,
    )
    if result.deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return ScanxDeleteResponse(
        ok=True,
        document_id=document_id,
        # When storage is deferred, keys were queued — treat as accepted cleanup.
        storage_removed=result.storage_removed > 0 or defer_storage,
    )


def _hard_delete_scanx_documents(
    db: Session,
    document_ids: list[int],
    *,
    background_tasks: BackgroundTasks | None = None,
    defer_storage: bool = False,
) -> ScanxBulkDeleteResponse:
    """Hard-delete many document rows (cascades chunks) and remove R2/local objects.

    When ``defer_storage`` is True, object storage cleanup runs in a background
    task so the HTTP response is not blocked by slow R2 (avoids SPA 60s AbortError).
    """
    # Preserve caller order; drop duplicates / non-positive ids.
    unique_ids = list(dict.fromkeys(int(i) for i in document_ids if int(i) > 0))
    if not unique_ids:
        return ScanxBulkDeleteResponse(deleted=0, skipped=0, ids=[], storage_removed=0)

    rows = (
        db.query(ScanxDocument)
        .filter(ScanxDocument.id.in_(unique_ids))
        .all()
    )
    group_ids = [row.document_group_id for row in rows if row.document_group_id]
    if group_ids:
        siblings = (
            db.query(ScanxDocument)
            .filter(ScanxDocument.document_group_id.in_(group_ids))
            .all()
        )
        extra = [row.id for row in siblings if row.id not in unique_ids]
        if extra:
            unique_ids.extend(extra)
            rows = list(rows) + [row for row in siblings if row.id in extra]
    found = {row.id: row for row in rows}
    deleted_ids: list[int] = []
    storage_keys: list[str] = []
    for doc_id in unique_ids:
        doc = found.get(doc_id)
        if not doc:
            continue
        for key in collect_scanx_document_storage_keys(doc):
            storage_keys.append(key)
        deleted_ids.append(doc.id)
        db.delete(doc)

    if deleted_ids:
        db.commit()

    storage_removed = 0
    if storage_keys:
        if defer_storage and background_tasks is not None:
            background_tasks.add_task(delete_scanx_objects, list(storage_keys))
            # Keys queued; actual removals happen after the response.
            storage_removed = 0
        else:
            storage_removed = delete_scanx_objects(storage_keys)

    return ScanxBulkDeleteResponse(
        deleted=len(deleted_ids),
        skipped=len(unique_ids) - len(deleted_ids),
        ids=deleted_ids,
        storage_removed=storage_removed,
    )


@router.post(
    "/documents/{document_id}/cancel",
    response_model=ScanxCancelResponse,
)
@log_action("scanx_cancel_document", "scanx_document")
def cancel_scanx_document_post(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Abort an in-progress ScanX job and hard-delete the file + extracted data.

    Exact resume from the current OCR/enhance page is not supported. Confirm in
    the UI before calling. Missing ids are success (idempotent).
    """
    _ = current_user
    result: ScanxCancelResult = cancel_scanx_document(db, document_id)
    return ScanxCancelResponse(
        ok=result.ok,
        document_id=result.document_id,
        cancelled=result.cancelled,
        already_gone=result.already_gone,
        storage_removed=result.storage_removed,
    )


@router.post(
    "/documents/{document_id}/delete",
    response_model=ScanxDeleteResponse,
)
@log_action("scanx_delete_document", "scanx_document")
def delete_scanx_document_post(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Preferred delete path (POST) — matches other Nexus entity deletes through Vite proxy."""
    _ = current_user
    return _hard_delete_scanx_document(
        db,
        document_id,
        background_tasks=background_tasks,
        defer_storage=True,
    )


@router.delete("/documents/{document_id}", response_model=ScanxDeleteResponse)
@log_action("scanx_delete_document", "scanx_document")
def delete_scanx_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """DELETE alias — same hard-delete as POST …/delete."""
    _ = current_user
    return _hard_delete_scanx_document(
        db,
        document_id,
        background_tasks=background_tasks,
        defer_storage=True,
    )


@router.post("/documents/{document_id}/reprocess", response_model=ScanxReprocessResponse)
@log_action("scanx_reprocess_document", "scanx_document")
def reprocess_scanx_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Re-queue parse/embed for an existing document (e.g. Verified-but-empty legacy rows)."""
    doc = db.query(ScanxDocument).filter(ScanxDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.r2_key:
        raise HTTPException(status_code=400, detail="Document has no stored file to reprocess.")
    doc.status = STATUS_PARSING
    doc.error_code = None
    # Clear prior categories so review UI does not show stale groups mid-parse.
    doc.extracted_fields_json = None
    metrics = dict(doc.metrics_json or {})
    metrics.pop("categories_count", None)
    metrics.pop("categories_error", None)
    metrics.pop("subjects_backfill", None)
    metrics.pop("subjects_backfill_version", None)
    metrics.pop("subjects_backfill_checked", None)
    steps = initial_progress_steps(
        waiting_for_worker=False,
        validate_done=bool(doc.r2_key),
    )
    metrics = apply_progress_to_metrics(metrics, steps)
    metrics.pop("rescue_thread_started", None)
    doc.metrics_json = metrics
    db.commit()
    db.refresh(doc)
    enqueue_result = schedule_process_document(doc.id, background_tasks)
    return ScanxReprocessResponse(
        document=_doc_out(doc),
        job_id=str(enqueue_result.get("job_id") or ""),
        enqueue_mode=str(enqueue_result.get("mode") or ""),
    )


@router.post("/documents", response_model=ScanxUploadResponse, status_code=202)
@log_action("scanx_upload_document", "scanx_document")
async def upload_scanx_document(
    request: Request,
    background_tasks: BackgroundTasks,
    lead_id: int = Form(...),
    document_type_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    upload_id: str | None = Form(default=None),
    booking_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    if lead_id < 1:
        raise scanx_error("M1")
    # Canonical folder id is always CRM Lead.id (never students_master / booking / slot ids).
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise scanx_error("M1")
    canonical_lead_id = int(lead.id)

    # Type is auto-detected after OCR. Upload accepts UNKNOWN/AUTO/omitted.
    type_id = (document_type_id or "").strip().upper() or "UNKNOWN"
    if type_id in {"", "AUTO"}:
        type_id = "UNKNOWN"
    subfolder = resolve_subfolder(type_id)

    in_flight = (
        db.query(ScanxDocument)
        .filter(
            ScanxDocument.uploader_user_id == current_user.id,
            ScanxDocument.status.in_([STATUS_UPLOADING, STATUS_PARSING]),
        )
        .count()
    )
    if in_flight >= CONCURRENT_UPLOAD_CAP:
        raise scanx_error("M9")

    if upload_id:
        existing = (
            db.query(ScanxDocument)
            .filter(
                ScanxDocument.upload_id == upload_id,
                ScanxDocument.uploader_user_id == current_user.id,
            )
            .first()
        )
        if existing:
            return ScanxUploadResponse(document=_doc_out(existing), job_id=None, enqueue_mode="idempotent")

    content = await file.read()
    original_filename = normalize_scanx_filename(file.filename)
    try:
        content_type = await asyncio.to_thread(
            validate_mime_and_size,
            filename=original_filename,
            content_type=file.content_type,
            content=content,
        )
        page_count, early_text = await asyncio.to_thread(
            validate_pages_for_content, content_type, content
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise scanx_error("M7") from exc

    digest = content_sha256(content)
    # Collapse accidental double POSTs of the same bytes while a job is still
    # in flight (new upload_id each click). Completed / failed / cancelled rows
    # are not matched so a later intentional rescan is allowed.
    near_dup = (
        db.query(ScanxDocument)
        .filter(
            ScanxDocument.lead_id == canonical_lead_id,
            ScanxDocument.content_sha256 == digest,
            ScanxDocument.status.in_([STATUS_UPLOADING, STATUS_PARSING]),
        )
        .order_by(ScanxDocument.created_at.desc())
        .first()
    )
    if near_dup:
        return ScanxUploadResponse(
            document=_doc_out(near_dup),
            job_id=None,
            enqueue_mode="idempotent",
        )

    # Same original filename already queued/running for this student → block
    # (even when bytes differ). Terminal statuses allow a later rescan.
    inflight_name = find_inflight_same_filename(
        db, lead_id=canonical_lead_id, original_filename=original_filename
    )
    if inflight_name:
        raise scanx_error("M17", name=original_filename)

    doc_uuid = uuid.uuid4()
    r2_key = build_r2_key(
        lead_id=canonical_lead_id,
        subfolder=subfolder,
        doc_uuid=doc_uuid,
        document_type_id=type_id,
        original_filename=original_filename,
    )

    doc = ScanxDocument(
        doc_uuid=doc_uuid,
        lead_id=canonical_lead_id,
        uploader_user_id=current_user.id,
        booking_id=booking_id,
        source=SOURCE_CRM,
        document_type_id=type_id,
        subfolder=subfolder,
        original_filename=original_filename,
        r2_key=None,
        content_sha256=digest,
        content_type=content_type,
        byte_size=len(content),
        page_count=page_count,
        status=STATUS_UPLOADING,
        extracted_text=early_text,
        metrics_json=apply_progress_to_metrics(
            {
                "upload_bytes": len(content),
                # Cloudflare archival is deferred until after local OCR + DB write.
                "r2_archive_pending": True,
            },
            initial_progress_steps(waiting_for_worker=False, validate_done=False),
        ),
        upload_id=(upload_id or None),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Local-first: persist under uploads/ and return 202 without waiting on R2.
    # Worker runs enhance → deskew → RapidOCR from local; R2 archive is post-OCR.
    try:
        await asyncio.to_thread(
            store_scanx_bytes_local,
            object_key=r2_key,
            content=content,
            content_type=content_type,
            original_filename=original_filename,
        )
    except HTTPException as exc:
        doc.status = "red_flag"
        doc.error_code = "M10"
        db.commit()
        raise exc

    doc.r2_key = r2_key
    doc.status = STATUS_PARSING
    metrics = dict(doc.metrics_json or {})
    metrics["r2_archive_pending"] = True
    metrics["storage_local_first"] = True
    steps = initial_progress_steps(waiting_for_worker=False, validate_done=True)
    metrics = apply_progress_to_metrics(metrics, steps)
    doc.metrics_json = metrics
    db.commit()
    db.refresh(doc)

    enqueue_result = schedule_process_document(doc.id, background_tasks)

    progress = progress_fields_from_metrics(
        doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
    )
    background_tasks.add_task(
        broadcast_nexus_event,
        "scanx.document.status",
        {
            "doc_id": doc.id,
            "doc_uuid": str(doc.doc_uuid),
            "lead_id": doc.lead_id,
            "status": doc.status,
            "original_filename": doc.original_filename,
            "progress_percent": progress.get("progress_percent"),
            "current_step_id": progress.get("current_step_id"),
            "current_step_label": progress.get("current_step_label"),
            "progress_steps": progress.get("progress_steps"),
        },
    )

    return ScanxUploadResponse(
        document=_doc_out(doc),
        job_id=str(enqueue_result.get("job_id") or ""),
        enqueue_mode=str(enqueue_result.get("mode") or ""),
    )


@router.post("/documents/group", response_model=ScanxUploadResponse, status_code=202)
@log_action("scanx_upload_document_group", "scanx_document")
async def upload_scanx_document_group(
    request: Request,
    background_tasks: BackgroundTasks,
    lead_id: int = Form(...),
    document_type_id: str | None = Form(default=None),
    files: list[UploadFile] = File(...),
    upload_id: str | None = Form(default=None),
    document_group_id: str | None = Form(default=None),
    booking_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_page_access(DOCUMENT_READINESS_ROUTE)),
):
    """Upload multiple image pages as one logical ScanX document (e.g. passport front+back).

    Files are stored as ordered ``source_pages`` on a single ``scanx_documents`` row and
    processed with the same multi-page OCR path used for scanned PDFs.
    """
    if lead_id < 1:
        raise scanx_error("M1")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise scanx_error("M1")
    canonical_lead_id = int(lead.id)

    type_id = (document_type_id or "").strip().upper() or "UNKNOWN"
    if type_id in {"", "AUTO"}:
        type_id = "UNKNOWN"
    subfolder = resolve_subfolder(type_id)

    in_flight = (
        db.query(ScanxDocument)
        .filter(
            ScanxDocument.uploader_user_id == current_user.id,
            ScanxDocument.status.in_([STATUS_UPLOADING, STATUS_PARSING]),
        )
        .count()
    )
    if in_flight >= CONCURRENT_UPLOAD_CAP:
        raise scanx_error("M9")

    if upload_id:
        existing = (
            db.query(ScanxDocument)
            .filter(
                ScanxDocument.upload_id == upload_id,
                ScanxDocument.uploader_user_id == current_user.id,
            )
            .first()
        )
        if existing:
            return ScanxUploadResponse(
                document=_doc_out(existing), job_id=None, enqueue_mode="idempotent"
            )

    members: list[tuple[str, bytes, str]] = []
    for upload in files or []:
        raw = await upload.read()
        if not raw:
            continue
        name = upload.filename or f"page_{len(members) + 1}.jpg"
        try:
            ctype = validate_mime_and_size(
                filename=name,
                content_type=upload.content_type,
                content=raw,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise scanx_error("M7") from exc
        if not str(ctype).lower().startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "M3",
                    "message": (
                        "Multi-file document groups must be images "
                        "(PNG/JPEG/TIFF). Use a single PDF for multi-page PDF uploads."
                    ),
                },
            )
        members.append((Path(name).name, raw, ctype))

    if len(members) < 2:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "M7",
                "message": "Upload at least two image pages to create a document group.",
            },
        )
    if len(members) > max_pages():
        raise scanx_error("M5", max_pages=max_pages())

    for member_name, _, _ in members:
        inflight_name = find_inflight_same_filename(
            db, lead_id=canonical_lead_id, original_filename=member_name
        )
        if inflight_name:
            raise scanx_error("M17", name=member_name)

    try:
        group_uuid = (
            uuid.UUID(str(document_group_id))
            if document_group_id
            else uuid.uuid4()
        )
    except ValueError:
        group_uuid = uuid.uuid4()

    doc_uuid = uuid.uuid4()
    first_name, first_bytes, first_ctype = members[0]
    primary_key = build_source_page_r2_key(
        lead_id=canonical_lead_id,
        subfolder=subfolder,
        doc_uuid=doc_uuid,
        document_type_id=type_id,
        original_filename=first_name,
        page_index=0,
    )
    combined_digest = content_sha256(b"".join(b for _, b, _ in members))

    source_pages: list[dict[str, Any]] = []
    total_bytes = 0
    for idx, (name, raw, ctype) in enumerate(members):
        page_key = build_source_page_r2_key(
            lead_id=canonical_lead_id,
            subfolder=subfolder,
            doc_uuid=doc_uuid,
            document_type_id=type_id,
            original_filename=name,
            page_index=idx,
        )
        try:
            # Local-first (no Cloudflare wait); archival after OCR succeeds.
            await asyncio.to_thread(
                store_scanx_bytes_local,
                object_key=page_key,
                content=raw,
                content_type=ctype,
                original_filename=name,
            )
        except HTTPException as exc:
            for prior in source_pages:
                delete_scanx_object(prior.get("r2_key"))
            raise exc
        source_pages.append(
            {
                "page_index": idx,
                "r2_key": page_key,
                "original_filename": name,
                "content_type": ctype,
                "byte_size": len(raw),
                "content_sha256": content_sha256(raw),
            }
        )
        total_bytes += len(raw)

    display_name = (
        f"{Path(first_name).stem} (+{len(members) - 1} page"
        f"{'s' if len(members) != 2 else ''})"
    )
    if len(display_name) > 480:
        display_name = f"Multi-page upload ({len(members)} images)"

    doc = ScanxDocument(
        doc_uuid=doc_uuid,
        lead_id=canonical_lead_id,
        uploader_user_id=current_user.id,
        booking_id=booking_id,
        source=SOURCE_CRM,
        document_type_id=type_id,
        subfolder=subfolder,
        original_filename=display_name,
        r2_key=primary_key,
        content_sha256=combined_digest,
        content_type=first_ctype,
        byte_size=total_bytes,
        page_count=len(members),
        status=STATUS_UPLOADING,
        document_group_id=group_uuid,
        source_pages=source_pages,
        metrics_json=apply_progress_to_metrics(
            {
                "upload_bytes": total_bytes,
                "document_group_id": str(group_uuid),
                "source_pages": source_pages,
                "source_page_count": len(source_pages),
                "multi_image_group": True,
                "r2_archive_pending": True,
                "storage_local_first": True,
            },
            initial_progress_steps(waiting_for_worker=False, validate_done=False),
        ),
        upload_id=(upload_id or None),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    doc.status = STATUS_PARSING
    metrics = dict(doc.metrics_json or {})
    metrics["r2_archive_pending"] = True
    metrics["storage_local_first"] = True
    steps = initial_progress_steps(waiting_for_worker=False, validate_done=True)
    metrics = apply_progress_to_metrics(metrics, steps)
    doc.metrics_json = metrics
    db.commit()
    db.refresh(doc)

    enqueue_result = schedule_process_document(doc.id, background_tasks)

    progress = progress_fields_from_metrics(
        doc.metrics_json if isinstance(doc.metrics_json, dict) else {}
    )
    background_tasks.add_task(
        broadcast_nexus_event,
        "scanx.document.status",
        {
            "doc_id": doc.id,
            "doc_uuid": str(doc.doc_uuid),
            "lead_id": doc.lead_id,
            "status": doc.status,
            "original_filename": doc.original_filename,
            "document_group_id": str(group_uuid),
            "page_count": len(members),
            "progress_percent": progress.get("progress_percent"),
            "current_step_id": progress.get("current_step_id"),
            "current_step_label": progress.get("current_step_label"),
            "progress_steps": progress.get("progress_steps"),
        },
    )

    return ScanxUploadResponse(
        document=_doc_out(doc),
        job_id=str(enqueue_result.get("job_id") or ""),
        enqueue_mode=str(enqueue_result.get("mode") or ""),
    )
