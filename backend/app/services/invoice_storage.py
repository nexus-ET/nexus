"""Cloudflare R2 storage for issued invoice PDFs.

Object keys follow:
    ADMIN/ACCOUNTS/INVOICES/FY_{start}_{end}/{filename}.pdf

Indian financial year runs 1 April → 31 March.
Example: 11 Aug 2026 → FY_2026_2027; 1 Apr 2027 → FY_2027_2028.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

INVOICE_ROOT_PREFIX = "ADMIN/ACCOUNTS/INVOICES"
MAX_INVOICE_PDF_BYTES = 15 * 1024 * 1024
FY_FOLDER_RE = re.compile(r"^FY_\d{4}_\d{4}$")
# New uploads use ADMIN/ACCOUNTS/INVOICES; legacy ADMIN/INVOICES keys still download.
INVOICE_KEY_RE = re.compile(
    r"^ADMIN/(?:ACCOUNTS/)?INVOICES/FY_\d{4}_\d{4}/[^/]+\.pdf$",
    re.IGNORECASE,
)
# Signed student download links remain valid for one year.
DOWNLOAD_TOKEN_TTL_SECONDS = 365 * 24 * 60 * 60


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
            detail=(
                "R2_ACCOUNT_ID must be your Cloudflare Account ID (32 hex characters). "
                "Do not use a Cloudflare API token (cfat_...)."
            ),
        )
    endpoint = (settings.R2_ENDPOINT_URL or "").strip() or (
        f"https://{account_id}.r2.cloudflarestorage.com"
    )
    if not endpoint.startswith("https://") or "r2.cloudflarestorage.com" not in endpoint:
        raise HTTPException(
            status_code=500,
            detail=(
                "R2_ENDPOINT_URL must look like "
                "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
            ),
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


def parse_invoice_calendar_date(value: str | None) -> date:
    """Parse YYYY-MM-DD (or ISO datetime) into a calendar date; default today UTC."""
    raw = (value or "").strip()
    if not raw:
        return datetime.utcnow().date()
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="invoice_date must be YYYY-MM-DD.",
        ) from exc


def indian_financial_year_folder(on: date) -> str:
    """Return FY_{start}_{end} for the Indian financial year containing `on`."""
    if on.month >= 4:
        start_year = on.year
    else:
        start_year = on.year - 1
    end_year = start_year + 1
    return f"FY_{start_year}_{end_year}"


def sanitize_invoice_pdf_filename(filename: str) -> str:
    raw_name = Path(filename or "").name
    if not raw_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invoice file must be a PDF.")
    stem = Path(raw_name).stem
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", stem)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = f"invoice-{uuid4().hex[:10]}"
    return f"{cleaned}.pdf"


def fy_prefix(fy_folder: str) -> str:
    if not FY_FOLDER_RE.fullmatch(fy_folder):
        raise HTTPException(status_code=400, detail="Invalid financial year folder.")
    return f"{INVOICE_ROOT_PREFIX}/{fy_folder}/"


def _prefix_exists(client, prefix: str) -> bool:
    try:
        response = client.list_objects_v2(
            Bucket=settings.R2_BUCKET_NAME,
            Prefix=prefix,
            MaxKeys=1,
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail=f"R2 list failed: {exc}") from exc
    return int(response.get("KeyCount") or 0) > 0


def _ensure_fy_folder(client, fy_folder: str) -> bool:
    """Create the FY folder marker in R2 when missing. Returns True if created."""
    prefix = fy_prefix(fy_folder)
    if _prefix_exists(client, prefix):
        return False
    folder_key = prefix  # trailing slash object acts as the folder
    try:
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=folder_key,
            Body=b"",
            ContentType="application/x-directory",
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail=f"R2 folder create failed: {exc}") from exc
    return True


def _local_uploads_root() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def upload_issued_invoice_pdf(
    *,
    filename: str,
    content: bytes,
    invoice_date: str | None = None,
) -> dict[str, object]:
    """Ensure FY folder exists under ADMIN/ACCOUNTS/INVOICES, then upload the PDF."""
    if not content:
        raise HTTPException(status_code=400, detail="Empty PDF upload.")
    if len(content) > MAX_INVOICE_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"PDF exceeds the {MAX_INVOICE_PDF_BYTES // (1024 * 1024)} MB limit.",
        )
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF.")

    sanitized = sanitize_invoice_pdf_filename(filename)
    on = parse_invoice_calendar_date(invoice_date)
    fy_folder = indian_financial_year_folder(on)
    object_key = f"{fy_prefix(fy_folder)}{sanitized}"
    if not object_key.startswith(f"{INVOICE_ROOT_PREFIX}/"):
        raise HTTPException(
            status_code=500,
            detail=(
                f"Refusing invoice upload outside {INVOICE_ROOT_PREFIX}/ "
                f"(got {object_key})."
            ),
        )
    folder_created = False
    logger.info(
        "Uploading invoice PDF to R2 key=%s fy=%s bytes=%s",
        object_key,
        fy_folder,
        len(content),
    )

    if _r2_configured():
        client = _r2_client()
        folder_created = _ensure_fy_folder(client, fy_folder)
        try:
            client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_key,
                Body=content,
                ContentType="application/pdf",
                ContentDisposition=f'inline; filename="{sanitized}"',
                CacheControl="private, max-age=0, no-cache",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(status_code=502, detail=f"R2 upload failed: {exc}") from exc
    else:
        local_root = _local_uploads_root()
        destination = local_root / object_key
        if not destination.parent.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            folder_created = True
        if destination.exists():
            stem = Path(sanitized).stem
            object_key = f"{fy_prefix(fy_folder)}{stem}-{uuid4().hex[:8]}.pdf"
            destination = local_root / object_key
        destination.write_bytes(content)

    return {
        "storage_key": object_key,
        "financial_year": fy_folder,
        "filename": Path(object_key).name,
        "folder_created": folder_created,
        "bytes": len(content),
    }


def normalize_invoice_storage_key(object_key: str | None) -> str:
    key = (object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/") or not INVOICE_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="Invalid invoice storage key.")
    return key


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def make_invoice_download_token(
    object_key: str,
    *,
    ttl_seconds: int = DOWNLOAD_TOKEN_TTL_SECONDS,
) -> str:
    """HMAC token granting unauthenticated PDF download for a stored invoice.

    Uses ``__`` (not ``.``) so email auto-linkers do not truncate the URL.
    """
    key = normalize_invoice_storage_key(object_key)
    exp = int(time.time()) + max(60, int(ttl_seconds))
    payload = f"{key}|{exp}".encode("utf-8")
    payload_b64 = _b64url_encode(payload)
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_b64}__{_b64url_encode(signature)}"


def verify_invoice_download_token(token: str) -> str:
    raw = (token or "").strip()
    # Accept legacy ``payload.sig`` tokens and current ``payload__sig`` tokens.
    if "__" in raw:
        payload_b64, sig_b64 = raw.rsplit("__", 1)
    elif "." in raw:
        payload_b64, sig_b64 = raw.rsplit(".", 1)
    else:
        raise HTTPException(status_code=400, detail="Invalid download token.")
    expected = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided = _b64url_decode(sig_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid download token.") from exc
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail="Invalid or tampered download link.")
    try:
        payload = _b64url_decode(payload_b64).decode("utf-8")
        key, exp_raw = payload.rsplit("|", 1)
        exp = int(exp_raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid download token.") from exc
    if exp < int(time.time()):
        raise HTTPException(status_code=410, detail="This invoice download link has expired.")
    return normalize_invoice_storage_key(key)


def public_api_base_url(request_base_url: str | None = None) -> str:
    """Prefer a reachable public origin so email links work outside localhost."""
    for candidate in (
        settings.PUBLIC_TUNNEL_BASE,
        settings.FRONTEND_URL,
        request_base_url,
    ):
        raw = (candidate or "").strip().rstrip("/")
        if not raw:
            continue
        # PUBLIC_TUNNEL_BASE is sometimes stored with /api/webhook — use origin only.
        if "://" in raw:
            parts = urlsplit(raw)
            if parts.scheme and parts.netloc:
                return urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        return raw
    return ""


def make_r2_presigned_download_url(
    object_key: str,
    *,
    ttl_seconds: int = DOWNLOAD_TOKEN_TTL_SECONDS,
    filename: str | None = None,
) -> str | None:
    """Return a time-limited HTTPS URL that streams the PDF from R2 directly."""
    if not _r2_configured():
        return None
    key = normalize_invoice_storage_key(object_key)
    # R2/SigV4 IAM-style credentials typically allow up to 7 days.
    expires = max(60, min(int(ttl_seconds), 7 * 24 * 60 * 60))
    display_name = (filename or Path(key).name or "invoice.pdf").replace('"', "")
    client = _r2_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": f'inline; filename="{display_name}"',
            },
            ExpiresIn=expires,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("R2 presign failed for %s: %s", key, exc)
        return None


def build_invoice_download_url(
    object_key: str,
    *,
    request_base_url: str | None = None,
    filename: str | None = None,
) -> str:
    """Prefer a direct R2 presigned URL; fall back to Nexus signed download API.

    Ephemeral trycloudflare tunnels go stale and path tokens with ``.`` get
    truncated by email clients — R2 presigned links avoid both problems.
    """
    presigned = make_r2_presigned_download_url(object_key, filename=filename)
    if presigned:
        return presigned

    token = make_invoice_download_token(object_key)
    base = public_api_base_url(request_base_url)
    encoded = quote(token, safe="")
    # Query-string token is safer for email auto-linkers than a path segment.
    if not base:
        return f"{settings.API_V1_STR}/invoices/download?token={encoded}"
    if base.endswith("/api/v1") or base.endswith(settings.API_V1_STR):
        return f"{base}/invoices/download?token={encoded}"
    return f"{base}{settings.API_V1_STR}/invoices/download?token={encoded}"


def fetch_invoice_pdf(object_key: str) -> tuple[bytes, str]:
    """Load an invoice PDF from R2 or the local uploads fallback."""
    key = normalize_invoice_storage_key(object_key)
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
                raise HTTPException(status_code=404, detail="Invoice PDF not found.") from exc
            raise HTTPException(status_code=502, detail=f"R2 fetch failed: {exc}") from exc

    local_path = _local_uploads_root() / key
    if not local_path.is_file():
        raise HTTPException(status_code=404, detail="Invoice PDF not found.")
    return local_path.read_bytes(), "application/pdf"
