"""Cloudflare R2 (or local fallback) storage for ScanX student documents.

Object keys follow D10:
  {SCANX_R2_KEY_ROOT}/{lead_id}/{SUBFOLDER}/{doc_uuid}__{document_type_id}__{safe}{ext}
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config import settings
from app.constants.scanx import SCANX_SUBFOLDERS

logger = logging.getLogger(__name__)

_KEY_RE = re.compile(
    r"^(?P<root>[^/]+)/(?P<lead_id>\d+)/"
    r"(?P<subfolder>"
    + "|".join(re.escape(s) for s in SCANX_SUBFOLDERS)
    + r")/"
    r"(?P<basename>[^/]+)$",
    re.IGNORECASE,
)


def _r2_configured() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET_NAME
    )


def _validate_r2_settings() -> str:
    account_id = (settings.R2_ACCOUNT_ID or "").strip()
    if account_id.startswith("cfat_") or not re.fullmatch(r"[a-f0-9]{32}", account_id):
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "M10",
                "message": "Upload didn’t complete. Check your connection and try again.",
            },
        )
    endpoint = (settings.R2_ENDPOINT_URL or "").strip() or (
        f"https://{account_id}.r2.cloudflarestorage.com"
    )
    return endpoint.rstrip("/")


def _r2_client(*, connect_timeout: int = 10, read_timeout: int = 60):
    endpoint = _validate_r2_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            connect_timeout=max(1, int(connect_timeout)),
            read_timeout=max(1, int(read_timeout)),
            retries={"max_attempts": 2, "mode": "standard"},
        ),
        region_name="auto",
    )


def _local_uploads_root() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def normalize_scanx_key(object_key: str | None) -> str:
    key = (object_key or "").strip().lstrip("/")
    root = (settings.SCANX_R2_KEY_ROOT or "STUDENTS").strip().strip("/") or "STUDENTS"
    if not key or ".." in key.split("/") or not _KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="Invalid ScanX storage key.")
    if not key.startswith(f"{root}/"):
        raise HTTPException(
            status_code=400,
            detail=f"ScanX key must start with {root}/.",
        )
    return key


def build_enhanced_preview_key(original_key: str, *, page_index: int = 0) -> str:
    """Sibling key under the same STUDENTS/.../SUBFOLDER for OpenCV preview JPEG.

    Page 0 keeps the legacy suffix for backward-compatible single-preview clients:
      …/mark__enhanced_preview.jpg
    Later pages use an explicit index:
      …/mark__enhanced_preview_p1.jpg
    """
    key = normalize_scanx_key(original_key)
    parent, base = key.rsplit("/", 1)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    # Strip prior enhanced suffixes so rebuilds stay stable.
    stem = re.sub(r"__enhanced_preview_p\d+$", "", stem)
    if stem.endswith("__enhanced_preview"):
        stem = stem[: -len("__enhanced_preview")]
    idx = max(0, int(page_index or 0))
    if idx <= 0:
        return f"{parent}/{stem}__enhanced_preview.jpg"
    return f"{parent}/{stem}__enhanced_preview_p{idx}.jpg"


def resolve_enhanced_preview_key(
    metrics: dict | None,
    *,
    page_index: int = 0,
) -> str | None:
    """Pick the storage key for an enhanced preview page from document metrics."""
    if not isinstance(metrics, dict):
        return None
    idx = max(0, int(page_index or 0))
    pages = metrics.get("enhanced_preview_pages")
    if isinstance(pages, list):
        for entry in pages:
            if not isinstance(entry, dict):
                continue
            try:
                entry_idx = int(entry.get("page_index", -1))
            except (TypeError, ValueError):
                continue
            if entry_idx != idx:
                continue
            key = entry.get("key")
            if isinstance(key, str) and key.strip():
                return key.strip()
    keys = metrics.get("enhanced_preview_keys")
    if isinstance(keys, list) and 0 <= idx < len(keys):
        key = keys[idx]
        if isinstance(key, str) and key.strip():
            return key.strip()
    if idx == 0:
        key = metrics.get("enhanced_preview_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def is_enhanced_preview_key(object_key: str | None) -> bool:
    """True when the basename looks like an OpenCV enhanced preview artifact."""
    if not object_key or not isinstance(object_key, str):
        return False
    base = object_key.strip().rsplit("/", 1)[-1].lower()
    return "__enhanced_preview" in base


def collect_enhanced_preview_keys(metrics: dict | None) -> list[str]:
    """All enhanced preview object keys referenced by metrics (local cleanup only)."""
    if not isinstance(metrics, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        if isinstance(raw, str) and raw.strip() and raw.strip() not in seen:
            seen.add(raw.strip())
            out.append(raw.strip())

    _add(metrics.get("enhanced_preview_key"))
    keys = metrics.get("enhanced_preview_keys")
    if isinstance(keys, list):
        for key in keys:
            _add(key)
    pages = metrics.get("enhanced_preview_pages")
    if isinstance(pages, list):
        for entry in pages:
            if isinstance(entry, dict):
                _add(entry.get("key"))
    return out


def collect_source_page_keys(source_pages: object, metrics: dict | None = None) -> list[str]:
    """R2/local keys for multi-image document groups (passport p1+p2, etc.)."""
    pages = source_pages if isinstance(source_pages, list) else None
    if not pages and isinstance(metrics, dict):
        raw = metrics.get("source_pages")
        pages = raw if isinstance(raw, list) else None
    out: list[str] = []
    seen: set[str] = set()
    for entry in pages or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("r2_key") or "").strip()
        if key and key not in seen and not is_enhanced_preview_key(key):
            seen.add(key)
            out.append(key)
    return out


def collect_scanx_original_archive_keys(doc: object) -> list[str]:
    """Keys eligible for Cloudflare R2: original upload (+ group page originals).

    Never includes enhanced PDFs, deskewed previews, or OCR preview JPEGs.
    Multi-page passport groups archive each uploaded page file (or the single
    original PDF when that is the stored source).
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        if not isinstance(raw, str):
            return
        key = raw.strip()
        if not key or key in seen or is_enhanced_preview_key(key):
            return
        seen.add(key)
        out.append(key)

    _add(getattr(doc, "r2_key", None))
    metrics = getattr(doc, "metrics_json", None)
    metrics_dict = metrics if isinstance(metrics, dict) else {}
    for key in collect_source_page_keys(getattr(doc, "source_pages", None), metrics_dict):
        _add(key)
    return out


def collect_scanx_document_storage_keys(doc: object) -> list[str]:
    """All keys to remove on cancel/delete: originals + leftover local enhanced."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        if isinstance(raw, str) and raw.strip() and raw.strip() not in seen:
            seen.add(raw.strip())
            out.append(raw.strip())

    for key in collect_scanx_original_archive_keys(doc):
        _add(key)
    metrics = getattr(doc, "metrics_json", None)
    metrics_dict = metrics if isinstance(metrics, dict) else {}
    for key in collect_enhanced_preview_keys(metrics_dict):
        _add(key)
    return out



def local_scanx_path(object_key: str) -> Path:
    """Filesystem path for a ScanX object under ``backend/uploads/``."""
    key = normalize_scanx_key(object_key)
    return _local_uploads_root() / key


def store_scanx_bytes_local(
    *,
    object_key: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    original_filename: str | None = None,
) -> dict[str, object]:
    """Persist bytes to local ``uploads/`` only (no Cloudflare round-trip).

    Used on HTTP upload so the 202 response is not blocked by R2. OCR/enhance
    read from this path; ``archive_scanx_key_to_r2`` copies to R2 afterward.
    """
    key = normalize_scanx_key(object_key)
    if not content:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "M7",
                "message": "We couldn’t read this file. It may be damaged — try re-exporting or a different copy.",
            },
        )
    destination = _local_uploads_root() / key
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    except OSError as exc:
        logger.exception("ScanX local store failed for key=%s", key)
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "M10",
                "message": "Upload didn’t complete. Check your connection and try again.",
            },
        ) from exc
    return {
        "storage_key": key,
        "bytes": len(content),
        "local_fallback": True,
        "local_only": True,
        "content_type": content_type or "application/octet-stream",
        "original_filename": Path(original_filename or "document").name,
    }


def archive_scanx_key_to_r2(
    object_key: str,
    *,
    content: bytes | None = None,
    content_type: str = "application/octet-stream",
    original_filename: str = "document",
) -> dict[str, object]:
    """Copy local (or provided) bytes to R2. Keeps the local file.

    Never deletes local on success — Review Scan data is already in the DB;
    local bytes remain until explicit cancel/delete. On R2 failure logs and
    returns ``ok=False`` so the caller can retry later.
    """
    key = normalize_scanx_key(object_key)
    local_path = _local_uploads_root() / key
    body = content
    if body is None:
        if not local_path.is_file():
            logger.warning("ScanX archive skipped — no local bytes for key=%s", key)
            return {"ok": False, "storage_key": key, "error": "missing_local"}
        body = local_path.read_bytes()
    if not body:
        return {"ok": False, "storage_key": key, "error": "empty"}

    if not _r2_configured():
        # Already local-only; treat as archived for this environment.
        return {
            "ok": True,
            "storage_key": key,
            "bytes": len(body),
            "local_fallback": True,
            "r2_skipped": True,
        }

    safe_name = Path(original_filename or "document").name.replace('"', "")
    try:
        # Ensure local copy exists before/while R2 put (tunnel blip safety).
        if not local_path.is_file():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(body)
        client = _r2_client()
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=content_type or "application/octet-stream",
            ContentDisposition=f'inline; filename="{safe_name}"',
            CacheControl="private, max-age=0, no-cache",
        )
        return {
            "ok": True,
            "storage_key": key,
            "bytes": len(body),
            "local_fallback": False,
            "local_retained": True,
        }
    except (BotoCoreError, ClientError, OSError) as exc:
        logger.exception("ScanX R2 archive failed for key=%s — local retained", key)
        return {
            "ok": False,
            "storage_key": key,
            "bytes": len(body),
            "error": f"{type(exc).__name__}: {exc}"[:200],
            "local_retained": True,
        }


def schedule_archive_scanx_keys(
    keys: list[str] | None,
    *,
    content_types: dict[str, str] | None = None,
    filenames: dict[str, str] | None = None,
) -> None:
    """Fire-and-forget R2 archival of original uploads only (non-blocking).

    Enhanced / deskewed / preview artifact keys are skipped even if passed.
    """
    if not keys:
        return
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in keys:
        if not raw or raw in seen:
            continue
        if is_enhanced_preview_key(raw):
            logger.debug("ScanX archive skipped enhanced preview key=%s", raw)
            continue
        seen.add(raw)
        deduped.append(raw)
    if not deduped:
        return
    ctypes = content_types or {}
    names = filenames or {}

    def _run() -> None:
        for key in deduped:
            try:
                result = archive_scanx_key_to_r2(
                    key,
                    content_type=ctypes.get(key) or "application/octet-stream",
                    original_filename=names.get(key) or Path(key).name,
                )
                if not result.get("ok"):
                    logger.warning(
                        "ScanX deferred R2 archive pending retry key=%s err=%s",
                        key,
                        result.get("error"),
                    )
            except Exception:
                logger.exception("ScanX deferred R2 archive crashed key=%s", key)

    import threading

    threading.Thread(
        target=_run,
        name="scanx-r2-archive",
        daemon=True,
    ).start()


def upload_scanx_bytes(
    *,
    object_key: str,
    content: bytes,
    content_type: str,
    original_filename: str,
    local_only: bool = False,
) -> dict[str, object]:
    """Store ScanX bytes.

    Default (``local_only=False``): write local first, then archive to R2 when
    configured (legacy sync path). Prefer ``store_scanx_bytes_local`` +
    ``schedule_archive_scanx_keys`` on the upload/OCR path so Cloudflare never
    blocks Review Scan.

    ``local_only=True``: disk only (same as ``store_scanx_bytes_local``).
    """
    if local_only:
        return store_scanx_bytes_local(
            object_key=object_key,
            content=content,
            content_type=content_type,
            original_filename=original_filename,
        )

    # Always persist locally first so OCR can proceed if R2 is slow/down.
    local_meta = store_scanx_bytes_local(
        object_key=object_key,
        content=content,
        content_type=content_type,
        original_filename=original_filename,
    )
    if not _r2_configured():
        logger.warning(
            "R2 not configured — stored ScanX object locally at %s",
            local_scanx_path(str(local_meta["storage_key"])),
        )
        return local_meta

    archived = archive_scanx_key_to_r2(
        str(local_meta["storage_key"]),
        content=content,
        content_type=content_type,
        original_filename=original_filename,
    )
    if not archived.get("ok"):
        # Local is enough for OCR; surface as soft failure only when caller
        # required immediate R2 (legacy). Keep raising for explicit sync puts
        # that are not the deferred-archive path — HTTP upload no longer uses this.
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "M10",
                "message": "Upload didn’t complete. Check your connection and try again.",
            },
        )
    return {
        "storage_key": local_meta["storage_key"],
        "bytes": len(content),
        "local_fallback": False,
        "local_retained": True,
    }


def fetch_scanx_bytes(object_key: str) -> tuple[bytes, str]:
    """Load ScanX bytes — local-first, then Cloudflare R2.

    Upload stores locally before OCR; preferring local avoids waiting on R2 and
    survives tunnel blips while extract is still in progress.
    """
    key = normalize_scanx_key(object_key)
    local_path = _local_uploads_root() / key

    if local_path.is_file():
        try:
            return local_path.read_bytes(), "application/octet-stream"
        except OSError:
            logger.warning("ScanX local read failed key=%s — trying R2", key, exc_info=True)

    if _r2_configured():
        client = _r2_client()
        try:
            response = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            body = response["Body"].read()
            ctype = response.get("ContentType") or "application/octet-stream"
            # Cache locally so reprocess / preview does not re-hit R2 every time.
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                if not local_path.is_file():
                    local_path.write_bytes(body)
            except OSError:
                logger.debug("ScanX local cache write skipped key=%s", key, exc_info=True)
            return body, ctype
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(status_code=404, detail="Document bytes not found.") from exc

    raise HTTPException(status_code=404, detail="Document bytes not found.")


def delete_scanx_object(object_key: str | None, *, fast: bool = False) -> bool:
    """Best-effort delete of R2 and/or local object. Returns True if anything removed.

    ``fast=True`` uses short boto timeouts so bulk-delete background cleanup cannot
    hang the request path when R2 is slow.
    """
    if not object_key:
        return False
    try:
        key = normalize_scanx_key(object_key)
    except HTTPException:
        return False

    removed = False
    if _r2_configured():
        try:
            client = _r2_client(
                connect_timeout=5 if fast else 10,
                read_timeout=15 if fast else 60,
            )
            client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            removed = True
        except (BotoCoreError, ClientError):
            logger.exception("Failed to delete ScanX R2 key=%s", key)

    local_path = _local_uploads_root() / key
    try:
        if local_path.is_file():
            local_path.unlink()
            removed = True
            # Clean empty parent dirs under uploads/STUDENTS/... (best-effort).
            parent = local_path.parent
            root = _local_uploads_root()
            while parent != root and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
    except OSError:
        logger.exception("Failed to delete local ScanX path=%s", local_path)

    return removed


def delete_scanx_objects(object_keys: list[str] | None) -> int:
    """Best-effort delete many keys (deduped). Returns count of successful removals."""
    if not object_keys:
        return 0
    seen: set[str] = set()
    removed = 0
    for key in object_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        if delete_scanx_object(key, fast=True):
            removed += 1
    return removed


def presign_scanx_download(object_key: str, *, expires_in: int = 900) -> str | None:
    """Return a short-lived R2 URL, or None when using local fallback."""
    key = normalize_scanx_key(object_key)
    if not _r2_configured():
        return None
    # Prefer local file when present and R2 may be empty (dev hybrid).
    local_path = _local_uploads_root() / key
    if local_path.is_file() and not _r2_object_exists(key):
        return None
    client = _r2_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
            ExpiresIn=max(60, int(expires_in)),
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to presign ScanX key=%s", key)
        return None


def _r2_object_exists(key: str) -> bool:
    if not _r2_configured():
        return False
    try:
        client = _r2_client()
        client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except (BotoCoreError, ClientError):
        return False
