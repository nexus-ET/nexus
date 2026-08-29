"""Cloudflare R2 storage for institution logos, banners, and gallery images.

R2 keys follow:
    INSTITUTIONS/PICTURES/INS-{id}-{NICK}/{asset_type}/{filename}

Example:
    INSTITUTIONS/PICTURES/INS-7-JHU/logo/primary-logo.svg
    INSTITUTIONS/PICTURES/INS-6-UCLA/banner/hero-main.webp
    INSTITUTIONS/PICTURES/INS-7-JHU/gallery/campus-library.webp

Legacy keys (pre-migration) looked like:
    jhu/logo/primary-logo.svg
    INSTITUTIONS/PICTURES/7_JHU/logo/primary-logo.svg
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.config import settings
from app.models.academia_institution import Institution

ALLOWED_ASSET_TYPES = frozenset({"logo", "banner", "gallery"})
LEGACY_ASSET_TYPE_ALIASES = {"campus": "banner"}
MAX_ASSET_BYTES = 500 * 1024

INSTITUTION_PICTURES_ROOT = "INSTITUTIONS/PICTURES"

ALLOWED_UPLOADS: dict[str, dict[str, set[str]]] = {
    "logo": {
        "image/svg+xml": {".svg"},
        "image/png": {".png"},
    },
    "banner": {
        "image/webp": {".webp"},
        "image/jpeg": {".jpg", ".jpeg"},
        "image/jpg": {".jpg", ".jpeg"},
    },
    "gallery": {
        "image/webp": {".webp"},
        "image/jpeg": {".jpg", ".jpeg"},
        "image/jpg": {".jpg", ".jpeg"},
    },
}

CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
}

_MEDIA_KEY_RE = re.compile(
    r"^(?:"
    r"INSTITUTIONS/PICTURES/(?:INS-)?[0-9]+[_-][A-Z0-9]+/"
    r"|"
    r"[a-z0-9]+(?:-[a-z0-9]+)*/"
    r")"
    r"(?:logo|banner|gallery)/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*\.(?:svg|png|webp|jpe?g)$",
    re.IGNORECASE,
)


def normalize_upload_content_type(content_type: str | None, filename: str) -> str:
    """Normalize browser MIME types and infer from extension when needed."""
    normalized = (content_type or "").split(";")[0].strip().lower()
    normalized = CONTENT_TYPE_ALIASES.get(normalized, normalized)
    if normalized in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/svg+xml",
    }:
        return normalized

    suffix = Path(filename or "").suffix.lower()
    inferred = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(suffix)
    if inferred:
        return inferred
    return normalized


def normalize_asset_type(asset_type: str) -> str:
    normalized = (asset_type or "").strip().lower()
    normalized = LEGACY_ASSET_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_ASSET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid asset type. Allowed values: {', '.join(sorted(ALLOWED_ASSET_TYPES))}.",
        )
    return normalized


def institution_nick_folder(institution: Institution) -> str:
    """Folder name under INSTITUTIONS/PICTURES — e.g. ``INS-7-JHU`` or ``INS-6-UCLA``."""
    raw_code = (institution.code or "").strip()
    if raw_code:
        nick = re.sub(r"[^A-Za-z0-9]+", "", raw_code).upper()
    else:
        nick = re.sub(r"[^A-Za-z0-9]+", "", (institution.name or "")).upper()
    if not nick:
        nick = f"INSTITUTION{int(institution.id)}"
    return f"INS-{int(institution.id)}-{nick}"


def institution_asset_prefix(institution: Institution) -> str:
    """Canonical R2/local prefix for an institution's picture assets."""
    return f"{INSTITUTION_PICTURES_ROOT}/{institution_nick_folder(institution)}"


def legacy_institution_asset_prefixes(institution: Institution) -> list[str]:
    """Older top-level prefixes used before INSTITUTIONS/PICTURES/INS-{id}-{NICK}/."""
    prefixes: list[str] = []
    code = (institution.code or "").strip().lower()
    if code and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", code):
        prefixes.append(code)
    slug = re.sub(r"[^a-z0-9]+", "-", (institution.name or "").strip().lower()).strip("-")
    if slug and slug not in prefixes:
        prefixes.append(slug)
    fallback = f"institution-{institution.id}"
    if fallback not in prefixes:
        prefixes.append(fallback)
    # Intermediate format used briefly: INSTITUTIONS/PICTURES/{id}_{NICK}
    raw_code = (institution.code or "").strip()
    nick = re.sub(r"[^A-Za-z0-9]+", "", raw_code or (institution.name or "")).upper()
    if nick:
        prefixes.append(f"{INSTITUTION_PICTURES_ROOT}/{int(institution.id)}_{nick}")
    # Also cover pre-PICTURES nesting under INSTITUTIONS/{nick}/ if it existed.
    for nick_prefix in list(prefixes):
        if nick_prefix.startswith(f"{INSTITUTION_PICTURES_ROOT}/"):
            continue
        nested = f"INSTITUTIONS/{nick_prefix}"
        if nested not in prefixes:
            prefixes.append(nested)
    return prefixes


def sanitize_asset_filename(filename: str) -> str:
    """Lowercase, hyphenate, and strip special characters from the filename."""
    raw_name = Path(filename or "").name
    suffix = Path(raw_name).suffix.lower()
    stem = Path(raw_name).stem
    sanitized_stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not sanitized_stem:
        raise HTTPException(
            status_code=400,
            detail="Filename must contain descriptive letters or numbers.",
        )
    if suffix not in {".svg", ".png", ".webp", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")
    return f"{sanitized_stem}{suffix}"


def build_r2_object_key(institution_prefix: str, asset_type: str, filename: str) -> str:
    asset_type = normalize_asset_type(asset_type)
    sanitized = sanitize_asset_filename(filename)
    return f"{institution_prefix.rstrip('/')}/{asset_type}/{sanitized}"


def parse_institution_asset_key(object_key: str) -> tuple[str, str, str] | None:
    """Return (institution_folder_or_prefix, asset_type, filename) when key is valid."""
    parts = [part for part in (object_key or "").lstrip("/").split("/") if part]
    if len(parts) >= 5 and parts[0].upper() == "INSTITUTIONS" and parts[1].upper() == "PICTURES":
        asset_type = parts[3].lower()
        if asset_type in ALLOWED_ASSET_TYPES:
            return parts[2], asset_type, parts[4]
        return None
    if len(parts) >= 4 and parts[0].upper() == "INSTITUTIONS":
        asset_type = parts[2].lower()
        if asset_type in ALLOWED_ASSET_TYPES:
            return parts[1], asset_type, parts[3]
        return None
    if len(parts) >= 3:
        asset_type = parts[1].lower()
        if asset_type in ALLOWED_ASSET_TYPES:
            return parts[0], asset_type, parts[2]
    return None


def validate_image_signature(content: bytes, content_type: str) -> None:
    valid = False
    if content_type == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff")
    elif content_type == "image/webp":
        valid = (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    elif content_type == "image/svg+xml":
        text = content.decode("utf-8", errors="ignore").lower().lstrip()
        valid = (
            ("<svg" in text[:500])
            and "<script" not in text
            and "<foreignobject" not in text
            and "javascript:" not in text
            and not re.search(r"\son[a-z]+\s*=", text)
            and not re.search(r"(?:href|xlink:href)\s*=\s*[\"']https?://", text)
            and "<!doctype" not in text
        )
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file content does not match its image format.",
        )


def _r2_configured() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET_NAME
    )


def _validate_r2_settings() -> str:
    """Return the S3 API endpoint URL, or raise a clear configuration error."""
    account_id = (settings.R2_ACCOUNT_ID or "").strip()
    if account_id.startswith("cfat_") or not re.fullmatch(r"[a-f0-9]{32}", account_id):
        raise HTTPException(
            status_code=500,
            detail=(
                "R2_ACCOUNT_ID must be your Cloudflare Account ID (32 hex characters). "
                "Do not use a Cloudflare API token (cfat_...). "
                "Find it in Cloudflare Dashboard → R2 → Overview, or in the S3 API endpoint URL."
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


def _is_private_s3_api_base(base: str) -> bool:
    host = (base or "").rstrip("/").lower()
    return "r2.cloudflarestorage.com" in host


def public_url_for_key(object_key: str) -> str:
    """Return a browser-loadable URL for an uploaded object.

    Prefer a true public CDN/custom domain. If R2_PUBLIC_BASE_URL is the private
    S3 API host (or unset), route through the backend media proxy instead.
    """
    key = object_key.lstrip("/")
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and not _is_private_s3_api_base(base):
        return f"{base}/{key}"
    # Same-origin API path — works with Vite proxy and authenticated R2 reads.
    return f"{settings.API_V1_STR}/academia/media/{key}"


def fetch_r2_object(object_key: str) -> tuple[bytes, str]:
    """Download an object from R2 (or local uploads fallback)."""
    key = object_key.lstrip("/")
    if not _MEDIA_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="Invalid media object key.")

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
                raise HTTPException(status_code=404, detail="Media object not found.") from exc
            raise HTTPException(status_code=502, detail=f"R2 fetch failed: {exc}") from exc

    local_path = Path(__file__).resolve().parents[2] / "uploads" / key
    if not local_path.is_file():
        raise HTTPException(status_code=404, detail="Media object not found.")
    suffix = local_path.suffix.lower()
    content_type = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
    return local_path.read_bytes(), content_type


def storage_key_from_url(url: str | None) -> str | None:
    """Extract object key from a stored public/proxy/S3 URL when possible."""
    if not url:
        return None
    value = url.strip()
    markers = (
        f"{settings.API_V1_STR}/academia/media/",
        "/academia/media/",
        "/uploads/",
    )
    for marker in markers:
        if marker in value:
            return value.split(marker, 1)[1].lstrip("/")
    # Private S3 API host style: https://<account>.r2.cloudflarestorage.com/<key>
    if "r2.cloudflarestorage.com/" in value:
        key = value.split("r2.cloudflarestorage.com/", 1)[1].lstrip("/")
        parsed = parse_institution_asset_key(key)
        if parsed:
            # Prefer the shortest trailing key that still parses as an asset.
            parts = [part for part in key.split("/") if part]
            asset_type_index = next(
                (index for index, part in enumerate(parts) if part.lower() in ALLOWED_ASSET_TYPES),
                -1,
            )
            if asset_type_index >= 1:
                # Keep INSTITUTIONS/PICTURES/{folder}/... when present.
                if (
                    asset_type_index >= 3
                    and parts[0].upper() == "INSTITUTIONS"
                    and parts[1].upper() == "PICTURES"
                ):
                    return "/".join(parts[: asset_type_index + 2])
                if asset_type_index >= 2 and parts[0].upper() == "INSTITUTIONS":
                    return "/".join(parts[: asset_type_index + 2])
                return "/".join(parts[asset_type_index - 1 : asset_type_index + 2])
        return key
    # Public CDN: https://cdn.example.com/<key>
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base and value.startswith(f"{base}/") and not _is_private_s3_api_base(base):
        return value[len(base) + 1 :].lstrip("/")
    return None


def rewrite_media_url(url: str | None) -> str | None:
    """Normalize stored media URLs so the Gallery page can load them."""
    if not url:
        return url
    key = storage_key_from_url(url)
    if not key:
        return url
    return public_url_for_key(key)


def _content_type_for_suffix(suffix: str) -> str:
    return {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix.lower(), "application/octet-stream")


def _list_assets_under_prefix(prefix: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    normalized_prefix = prefix if prefix.endswith("/") else f"{prefix}/"

    if _r2_configured():
        client = _r2_client()
        try:
            continuation: str | None = None
            while True:
                kwargs: dict[str, object] = {
                    "Bucket": settings.R2_BUCKET_NAME,
                    "Prefix": normalized_prefix,
                    "MaxKeys": 100,
                }
                if continuation:
                    kwargs["ContinuationToken"] = continuation
                response = client.list_objects_v2(**kwargs)
                for obj in response.get("Contents") or []:
                    key = str(obj.get("Key") or "")
                    parsed = parse_institution_asset_key(key)
                    if not parsed:
                        continue
                    _, asset_type, filename = parsed
                    items.append(
                        {
                            "url": public_url_for_key(key),
                            "caption": None,
                            "picture_type": asset_type,
                            "file_name": filename,
                            "file_type": _content_type_for_suffix(Path(filename).suffix),
                            "file_size": int(obj.get("Size") or 0),
                            "storage_key": key,
                        }
                    )
                if not response.get("IsTruncated"):
                    break
                continuation = response.get("NextContinuationToken")
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(status_code=502, detail=f"R2 list failed: {exc}") from exc
        return items

    local_root = Path(__file__).resolve().parents[2] / "uploads" / prefix
    if not local_root.exists():
        return []
    uploads_root = Path(__file__).resolve().parents[2] / "uploads"
    for path in sorted(local_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(uploads_root).as_posix()
        parsed = parse_institution_asset_key(relative)
        if not parsed:
            continue
        _, asset_type, filename = parsed
        items.append(
            {
                "url": public_url_for_key(relative),
                "caption": None,
                "picture_type": asset_type,
                "file_name": filename,
                "file_type": _content_type_for_suffix(path.suffix),
                "file_size": path.stat().st_size,
                "storage_key": relative,
            }
        )
    return items


def list_institution_assets(institution: Institution) -> list[dict[str, object]]:
    """List logo/banner/gallery objects already stored for an institution."""
    return _list_assets_under_prefix(institution_asset_prefix(institution))


def upload_institution_asset(
    *,
    institution: Institution,
    asset_type: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict[str, object]:
    """Upload one institution asset and return metadata for persistence."""
    normalized_type = normalize_asset_type(asset_type)
    if len(content) > MAX_ASSET_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f'"{filename}" exceeds the 500 KB file-size limit.',
        )

    suffix = Path(filename).suffix.lower()
    content_type = normalize_upload_content_type(content_type, filename)
    allowed_extensions = ALLOWED_UPLOADS[normalized_type].get(content_type)
    if not allowed_extensions or suffix not in allowed_extensions:
        format_message = {
            "logo": "Logos must be SVG or PNG.",
            "banner": "Banner (Hero) images must be WebP or JPEG.",
            "gallery": "Gallery images must be WebP or JPEG.",
        }[normalized_type]
        raise HTTPException(status_code=400, detail=f'"{filename}": {format_message}')

    validate_image_signature(content, content_type)

    institution_prefix = institution_asset_prefix(institution)
    sanitized_name = sanitize_asset_filename(filename)
    object_key = build_r2_object_key(institution_prefix, normalized_type, sanitized_name)

    if _r2_configured():
        client = _r2_client()
        try:
            client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_key,
                Body=content,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(status_code=502, detail=f"R2 upload failed: {exc}") from exc
    else:
        local_root = Path(__file__).resolve().parents[2] / "uploads"
        destination = local_root / object_key
        if destination.exists():
            stem = Path(sanitized_name).stem
            ext = Path(sanitized_name).suffix
            object_key = f"{institution_prefix}/{normalized_type}/{stem}-{uuid4().hex[:8]}{ext}"
            destination = local_root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    # Preserve the original upload filename for UI display; storage uses sanitized_name.
    return {
        "url": public_url_for_key(object_key),
        "caption": None,
        "picture_type": normalized_type,
        "file_name": Path(filename).name,
        "file_type": content_type,
        "file_size": len(content),
        "storage_key": object_key,
    }


def _owned_prefixes(institution: Institution) -> list[str]:
    return [institution_asset_prefix(institution), *legacy_institution_asset_prefixes(institution)]


def _assert_key_belongs_to_institution(institution: Institution, object_key: str) -> str:
    key = (object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/"):
        raise HTTPException(status_code=400, detail="Invalid storage key.")
    if not parse_institution_asset_key(key):
        raise HTTPException(status_code=400, detail="Invalid institution asset key.")
    owned = _owned_prefixes(institution)
    if not any(key == prefix or key.startswith(f"{prefix}/") for prefix in owned):
        raise HTTPException(
            status_code=400,
            detail="Storage key does not belong to this institution.",
        )
    return key


def delete_institution_asset(
    *,
    institution: Institution,
    object_key: str | None = None,
    url: str | None = None,
) -> dict[str, object]:
    """Delete one logo/banner/gallery object from R2 or local uploads."""
    key = object_key or storage_key_from_url(url)
    if not key:
        raise HTTPException(status_code=400, detail="A storage key or media URL is required.")
    key = _assert_key_belongs_to_institution(institution, key)

    if _r2_configured():
        client = _r2_client()
        try:
            client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(status_code=502, detail=f"R2 delete failed: {exc}") from exc
    else:
        local_path = Path(__file__).resolve().parents[2] / "uploads" / key
        if local_path.is_file():
            local_path.unlink()

    return {"ok": True, "storage_key": key}


def _delete_prefix(prefix: str) -> int:
    deleted = 0
    normalized_prefix = prefix if prefix.endswith("/") else f"{prefix}/"

    if _r2_configured():
        client = _r2_client()
        continuation: str | None = None
        while True:
            kwargs: dict[str, object] = {
                "Bucket": settings.R2_BUCKET_NAME,
                "Prefix": normalized_prefix,
                "MaxKeys": 1000,
            }
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = client.list_objects_v2(**kwargs)
            objects = [
                {"Key": str(obj.get("Key"))}
                for obj in (response.get("Contents") or [])
                if obj.get("Key")
            ]
            if objects:
                client.delete_objects(
                    Bucket=settings.R2_BUCKET_NAME,
                    Delete={"Objects": objects, "Quiet": True},
                )
                deleted += len(objects)
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
        return deleted

    local_root = Path(__file__).resolve().parents[2] / "uploads" / prefix
    if local_root.exists():
        for path in sorted(local_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                deleted += 1
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            local_root.rmdir()
        except OSError:
            pass
    return deleted


def delete_all_institution_assets(institution: Institution) -> dict[str, object]:
    """Delete every logo/banner/gallery object under current and legacy prefixes."""
    deleted = 0
    prefixes = _owned_prefixes(institution)
    try:
        for prefix in prefixes:
            deleted += _delete_prefix(prefix)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=502, detail=f"R2 bulk delete failed: {exc}"
        ) from exc
    return {
        "ok": True,
        "deleted": deleted,
        "prefix": institution_asset_prefix(institution),
        "prefixes": prefixes,
    }
