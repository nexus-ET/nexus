"""Cloudflare R2 storage for generated Document Checklist PDFs.

Object keys:
  Global:
    {DOCUMENT_CHECKLIST_R2_PREFIX}/{BusinessShortName}_DOCUMENT_CHECKLIST_{Level}.pdf
  Country-Specific:
    {DOCUMENT_CHECKLIST_R2_PREFIX}/{BusinessShortName}_DOCUMENT_CHECKLIST_{Level}_{Country}.pdf
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

logger = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "INSTITUTIONS/DOCUMENTS/CHECKLIST"
MAX_CHECKLIST_BYTES = 10 * 1024 * 1024

_LEAF_RE = re.compile(r"^[a-zA-Z0-9._\-]+$")
_UNSAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def checklist_key_prefix() -> str:
    """Normalized R2 prefix for checklist uploads (no leading/trailing slash)."""
    raw = (settings.DOCUMENT_CHECKLIST_R2_PREFIX or DEFAULT_KEY_PREFIX).strip().strip("/")
    return raw or DEFAULT_KEY_PREFIX


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
            detail="Document checklist storage is misconfigured.",
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


def sanitize_checklist_key_segment(value: str) -> str:
    """Trim, replace spaces with _, strip path separators and R2-unsafe characters."""
    cleaned = (value or "").strip().replace(" ", "_")
    cleaned = cleaned.replace("/", "").replace("\\", "").replace("..", "")
    cleaned = _UNSAFE_SEGMENT_RE.sub("", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned


def format_level_for_checklist_filename(level_name: str) -> str:
    """Catalog level name for the object key leaf (spaces become underscores)."""
    return sanitize_checklist_key_segment(level_name) or "Level"


def build_checklist_filename(
    *,
    business_short_name: str,
    level_name: str,
    country_name: str | None = None,
) -> str:
    short = sanitize_checklist_key_segment(business_short_name)
    if not short:
        raise HTTPException(
            status_code=400,
            detail=(
                "Business short name is required to create a document checklist. "
                "Set Business short name in Settings before creating a checklist."
            ),
        )
    level = format_level_for_checklist_filename(level_name)
    country = sanitize_checklist_key_segment(country_name or "")
    if country:
        return f"{short}_DOCUMENT_CHECKLIST_{level}_{country}.pdf"
    return f"{short}_DOCUMENT_CHECKLIST_{level}.pdf"


def build_checklist_object_key(
    *,
    business_short_name: str,
    level_name: str,
    country_name: str | None = None,
) -> str:
    filename = build_checklist_filename(
        business_short_name=business_short_name,
        level_name=level_name,
        country_name=country_name,
    )
    return f"{checklist_key_prefix()}/{filename}"


def _key_matches_prefix(key: str) -> bool:
    prefix = checklist_key_prefix()
    if not key.startswith(f"{prefix}/"):
        return False
    leaf = key[len(prefix) + 1 :]
    return bool(leaf and "/" not in leaf and _LEAF_RE.fullmatch(leaf))


def normalize_checklist_key(object_key: str | None) -> str:
    key = (object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/") or not _key_matches_prefix(key):
        raise HTTPException(status_code=400, detail="Invalid document checklist storage key.")
    return key


def upload_document_checklist(
    *,
    level_name: str,
    business_short_name: str,
    content: bytes,
    country_name: str | None = None,
) -> dict[str, object]:
    """Upload a checklist PDF to R2 (or local uploads fallback when R2 is unset).

    Regenerating the same scope+level(+country) replaces the same object key.
    """
    if not content:
        raise HTTPException(status_code=400, detail="Checklist PDF is empty.")
    if len(content) > MAX_CHECKLIST_BYTES:
        raise HTTPException(status_code=400, detail="Checklist PDF exceeds the 10 MB limit.")

    object_key = build_checklist_object_key(
        business_short_name=business_short_name,
        level_name=level_name,
        country_name=country_name,
    )
    safe_name = Path(object_key).name.replace('"', "")

    if _r2_configured():
        client = _r2_client()
        try:
            client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_key,
                Body=content,
                ContentType="application/pdf",
                ContentDisposition=f'attachment; filename="{safe_name}"',
                CacheControl="private, max-age=0, no-cache",
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("Document checklist R2 upload failed key=%s", object_key)
            raise HTTPException(status_code=502, detail=f"R2 upload failed: {exc}") from exc
    else:
        local_root = Path(__file__).resolve().parents[2] / "uploads"
        destination = local_root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        logger.info("Document checklist stored locally (R2 not configured): %s", object_key)

    return {
        "storage_key": object_key,
        "file_size": len(content),
        "content_type": "application/pdf",
        "filename": safe_name,
    }


def _is_private_s3_api_base(base: str) -> bool:
    host = (base or "").rstrip("/").lower()
    return "r2.cloudflarestorage.com" in host


def public_url_for_checklist_key(object_key: str) -> str:
    """Browser-safe URL (CDN or authenticated API media path). No secrets."""
    key = normalize_checklist_key(object_key)
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and not _is_private_s3_api_base(base):
        return f"{base}/{key}"
    return f"{settings.API_V1_STR}/document-requirements/media/{key}"


def make_presigned_checklist_url(
    object_key: str,
    *,
    filename: str | None = None,
    expires_in: int = 900,
) -> str | None:
    if not _r2_configured():
        return None
    key = normalize_checklist_key(object_key)
    display = (filename or Path(key).name or "checklist.pdf").replace('"', "")
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
        logger.warning("Document checklist presign failed for %s: %s", key, exc)
        return None


def resolve_checklist_download_url(
    object_key: str,
    *,
    filename: str | None = None,
) -> str:
    """Prefer R2 presign; fall back to public/CDN or API media path."""
    key = normalize_checklist_key(object_key)
    presigned = make_presigned_checklist_url(key, filename=filename)
    if presigned:
        return presigned
    return public_url_for_checklist_key(key)


def fetch_checklist_bytes(object_key: str) -> tuple[bytes, str]:
    key = normalize_checklist_key(object_key)
    if _r2_configured():
        client = _r2_client()
        try:
            response = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
            body = response["Body"].read()
            content_type = response.get("ContentType") or "application/pdf"
            return body, content_type
        except ClientError as exc:
            code = (exc.response or {}).get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise HTTPException(status_code=404, detail="Checklist file not found.") from exc
            raise HTTPException(status_code=502, detail=f"R2 fetch failed: {exc}") from exc

    local_path = Path(__file__).resolve().parents[2] / "uploads" / key
    if not local_path.is_file():
        raise HTTPException(status_code=404, detail="Checklist file not found.")
    return local_path.read_bytes(), "application/pdf"
