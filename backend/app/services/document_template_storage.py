"""Cloudflare R2 storage for document requirement sample templates.

Object keys:
  {DOCUMENT_TEMPLATE_R2_PREFIX}/{uuid}__{safe_filename}

Legacy keys (still readable):
  DOCUMENT_TEMPLATES/{uuid}__{safe_filename}
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# Historical prefix — existing DB rows keep working; new uploads use settings.
LEGACY_KEY_ROOT = "DOCUMENT_TEMPLATES"
DEFAULT_KEY_PREFIX = "INSTITUTIONS/DOCUMENTS/TEMPLATES"
MAX_TEMPLATE_BYTES = 10 * 1024 * 1024

ALLOWED_CONTENT_TYPES: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        ".docx"
    },
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}

CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "application/x-pdf": "application/pdf",
}

_LEAF_RE = re.compile(r"^[a-zA-Z0-9._\-]+$")


def template_key_prefix() -> str:
    """Normalized R2 prefix for new template uploads (no leading/trailing slash)."""
    raw = (settings.DOCUMENT_TEMPLATE_R2_PREFIX or DEFAULT_KEY_PREFIX).strip().strip("/")
    return raw or DEFAULT_KEY_PREFIX


# Module-level name kept for import compatibility; prefer template_key_prefix().
KEY_ROOT = DEFAULT_KEY_PREFIX


def allowed_template_key_prefixes() -> tuple[str, ...]:
    """Prefixes accepted for read/download (current, default, and legacy)."""
    ordered: list[str] = []
    for prefix in (template_key_prefix(), DEFAULT_KEY_PREFIX, LEGACY_KEY_ROOT):
        if prefix and prefix not in ordered:
            ordered.append(prefix)
    return tuple(ordered)


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
            detail="Document template storage is misconfigured.",
        )
    endpoint = (settings.R2_ENDPOINT_URL or "").strip() or (
        f"https://{account_id}.r2.cloudflarestorage.com"
    )
    return endpoint.rstrip("/")


def _r2_client():
    endpoint = _validate_r2_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _is_private_s3_api_base(base: str) -> bool:
    host = (base or "").rstrip("/").lower()
    return "r2.cloudflarestorage.com" in host


def sanitize_template_filename(filename: str) -> str:
    base = Path(filename or "template").name
    cleaned = re.sub(r"[^A-Za-z0-9._\-]+", "_", base).strip("._")
    if not cleaned:
        cleaned = "template"
    return cleaned[:120]


def normalize_content_type(content_type: str | None, filename: str) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    normalized = CONTENT_TYPE_ALIASES.get(normalized, normalized)
    if normalized in ALLOWED_CONTENT_TYPES:
        return normalized
    suffix = Path(filename or "").suffix.lower()
    inferred = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix)
    if inferred:
        return inferred
    return normalized


def validate_template_upload(*, filename: str, content: bytes, content_type: str | None) -> str:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_TEMPLATE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB limit.")
    normalized = normalize_content_type(content_type, filename)
    suffix = Path(filename or "").suffix.lower()
    allowed = ALLOWED_CONTENT_TYPES.get(normalized)
    if not allowed or suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Allowed file types: PDF, DOC, DOCX, JPEG, PNG, WEBP, GIF.",
        )
    return normalized


def build_template_object_key(filename: str) -> str:
    safe = sanitize_template_filename(filename)
    return f"{template_key_prefix()}/{uuid4().hex}__{safe}"


def _key_matches_allowed_prefix(key: str) -> bool:
    for prefix in allowed_template_key_prefixes():
        if not key.startswith(f"{prefix}/"):
            continue
        leaf = key[len(prefix) + 1 :]
        if leaf and "/" not in leaf and _LEAF_RE.fullmatch(leaf):
            return True
    return False


def normalize_template_key(object_key: str | None) -> str:
    key = (object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/") or not _key_matches_allowed_prefix(key):
        raise HTTPException(status_code=400, detail="Invalid document template storage key.")
    return key


def ensure_template_media_key(object_key: str) -> str:
    """Normalize a media-route path, prepending the active prefix when missing."""
    key = (object_key or "").strip().lstrip("/")
    if _key_matches_allowed_prefix(key):
        return key
    return f"{template_key_prefix()}/{key}"


def storage_key_from_file_url(file_url: str | None) -> str | None:
    """Extract a template object key from a stored URL or raw key."""
    if not file_url:
        return None
    value = file_url.strip()
    markers = (
        f"{settings.API_V1_STR}/document-requirements/media/",
        "/document-requirements/media/",
        "/uploads/",
    )

    def _if_allowed(candidate: str) -> str | None:
        candidate = candidate.lstrip("/")
        if _key_matches_allowed_prefix(candidate):
            return candidate
        return None

    for marker in markers:
        if marker in value:
            found = _if_allowed(value.split(marker, 1)[1])
            if found:
                return found
    found = _if_allowed(value)
    if found:
        return found
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and value.startswith(f"{base}/") and not _is_private_s3_api_base(base):
        found = _if_allowed(value[len(base) + 1 :])
        if found:
            return found
    if "r2.cloudflarestorage.com/" in value:
        found = _if_allowed(value.split("r2.cloudflarestorage.com/", 1)[1])
        if found:
            return found
    return None


def public_url_for_template_key(object_key: str) -> str:
    """Browser-safe URL (CDN or authenticated API media path). No secrets."""
    key = normalize_template_key(object_key)
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and not _is_private_s3_api_base(base):
        return f"{base}/{key}"
    return f"{settings.API_V1_STR}/document-requirements/media/{key}"


def upload_document_template(
    *,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> dict[str, object]:
    """Upload a sample template to R2 (or local uploads fallback)."""
    normalized_type = validate_template_upload(
        filename=filename,
        content=content,
        content_type=content_type,
    )
    object_key = build_template_object_key(filename)
    safe_name = Path(filename or "template").name.replace('"', "")

    if _r2_configured():
        client = _r2_client()
        try:
            client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_key,
                Body=content,
                ContentType=normalized_type,
                ContentDisposition=f'inline; filename="{safe_name}"',
                CacheControl="private, max-age=0, no-cache",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Document template R2 upload failed key=%s", object_key)
            raise HTTPException(status_code=502, detail=f"R2 upload failed: {exc}") from exc
    else:
        local_root = Path(__file__).resolve().parents[2] / "uploads"
        destination = local_root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    return {
        "storage_key": object_key,
        "file_url": public_url_for_template_key(object_key),
        "file_size": len(content),
        "content_type": normalized_type,
        "template_name": Path(filename or "template").name[:150],
    }


def make_presigned_download_url(
    object_key: str,
    *,
    filename: str | None = None,
    expires_in: int = 900,
) -> str | None:
    if not _r2_configured():
        return None
    key = normalize_template_key(object_key)
    display = (filename or Path(key).name or "template").replace('"', "")
    client = _r2_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
                "ResponseContentDisposition": f'inline; filename="{display}"',
            },
            ExpiresIn=max(60, min(int(expires_in), 3600)),
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Document template presign failed for %s: %s", key, exc)
        return None


def fetch_template_bytes(object_key: str) -> tuple[bytes, str]:
    key = normalize_template_key(object_key)
    if _r2_configured():
        client = _r2_client()
        try:
            response = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            body = response["Body"].read()
            content_type = response.get("ContentType") or "application/octet-stream"
            return body, content_type
        except ClientError as exc:
            code = (exc.response or {}).get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise HTTPException(status_code=404, detail="Template file not found.") from exc
            raise HTTPException(status_code=502, detail=f"R2 fetch failed: {exc}") from exc

    local_path = Path(__file__).resolve().parents[2] / "uploads" / key
    if not local_path.is_file():
        raise HTTPException(status_code=404, detail="Template file not found.")
    suffix = local_path.suffix.lower()
    content_type = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")
    return local_path.read_bytes(), content_type


def resolve_download_url(file_url: str, *, filename: str | None = None) -> str:
    """Prefer R2 presign; fall back to stored proxy URL (never embeds secrets)."""
    key = storage_key_from_file_url(file_url)
    if key:
        presigned = make_presigned_download_url(key, filename=filename)
        if presigned:
            return presigned
        return public_url_for_template_key(key)
    return file_url
