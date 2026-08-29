from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.business import Business
from app.models.user import User
from app.utils.timezone import utc_now

DEFAULT_BUSINESS_ID = 1
DOMAIN_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
EMAIL_DOMAIN_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
OFFICE_PHONE_PATTERN = re.compile(r"^\+?[0-9()\-\s.]{7,50}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

UPLOADS_ROOT = Path(__file__).resolve().parents[1] / "uploads"
BUSINESS_LOGO_DIR = UPLOADS_ROOT / "business"
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_LOGO_BYTES = 5 * 1024 * 1024
LOGO_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def resolve_business_id_for_user(user: User) -> int:
    business_id = getattr(user, "business_id", None)
    return int(business_id) if business_id else DEFAULT_BUSINESS_ID


def ensure_default_business(db: Session) -> Business:
    business = db.query(Business).filter(Business.id == DEFAULT_BUSINESS_ID).first()
    if business:
        return business

    business = Business(
        id=DEFAULT_BUSINESS_ID,
        name="Default Business",
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return business


def get_business_profile(db: Session, business_id: int) -> dict:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        business = ensure_default_business(db)

    return _serialize_business(business)


def update_business_profile(
    db: Session,
    business_id: int,
    *,
    business_name: str,
    business_domain: str | None,
    address_line1: str | None,
    address_line2: str | None,
    address_line3: str | None,
    city: str | None,
    state: str | None,
    country: str | None,
    zip_code: str | None,
    office_phone_number: str | None,
    office_mobile_number: str | None,
    web_url: str | None,
    email_domain: str | None,
    office_phone_active: bool = True,
    office_mobile_active: bool = True,
    office_phone_contacts: list[dict[str, Any]] | None = None,
    office_email_contacts: list[dict[str, Any]] | None = None,
) -> dict:
    cleaned_name = business_name.strip()
    cleaned_domain = _optional_text(business_domain)
    cleaned_address_line1 = _optional_text(address_line1)
    cleaned_address_line2 = _optional_text(address_line2)
    cleaned_address_line3 = _optional_text(address_line3)
    cleaned_city = _optional_text(city)
    cleaned_state = _optional_text(state)
    cleaned_country = _optional_text(country)
    cleaned_zip_code = _optional_text(zip_code)
    cleaned_web_url = _optional_text(web_url)
    cleaned_email_domain = _optional_text(email_domain)
    phone_active = bool(office_phone_active)
    mobile_active = bool(office_mobile_active)

    phone_contacts = _normalize_contact_entries(
        office_phone_contacts,
        value_kind="phone",
        legacy_values=(office_phone_number, office_mobile_number),
        legacy_types=("Main Line", "WhatsApp"),
    )
    email_contacts = _normalize_contact_entries(
        office_email_contacts,
        value_kind="email",
        legacy_values=(),
        legacy_types=("General",),
    )

    # Keep legacy scalar columns in sync for older consumers.
    cleaned_office_phone = phone_contacts[0]["value"] if phone_contacts else None
    cleaned_office_mobile = phone_contacts[1]["value"] if len(phone_contacts) > 1 else None

    _validate_business_profile(
        business_name=cleaned_name,
        business_domain=cleaned_domain,
        office_phone_number=cleaned_office_phone,
        office_mobile_number=cleaned_office_mobile,
        web_url=cleaned_web_url,
        email_domain=cleaned_email_domain,
    )

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        business = Business(id=business_id, name=cleaned_name)
        db.add(business)

    business.name = cleaned_name
    business.domain = cleaned_domain
    business.address_line1 = cleaned_address_line1
    business.address_line2 = cleaned_address_line2
    business.address_line3 = cleaned_address_line3
    business.city = cleaned_city
    business.state = cleaned_state
    business.country = cleaned_country
    business.zip_code = cleaned_zip_code
    business.office_phone_number = cleaned_office_phone
    business.office_mobile_number = cleaned_office_mobile
    business.office_phone_active = phone_active
    business.office_mobile_active = mobile_active
    # Copy + flag_modified so JSON list changes always persist (SQLAlchemy mutability).
    business.office_phone_contacts = [dict(entry) for entry in phone_contacts]
    business.office_email_contacts = [dict(entry) for entry in email_contacts]
    flag_modified(business, "office_phone_contacts")
    flag_modified(business, "office_email_contacts")
    business.web_url = cleaned_web_url
    business.email_domain = cleaned_email_domain.lower() if cleaned_email_domain else None
    business.updated_at = utc_now()

    db.commit()
    db.refresh(business)
    return _serialize_business(business)


def save_business_logo(
    db: Session,
    business_id: int,
    *,
    content: bytes,
    filename: str | None,
) -> dict:
    if not content:
        raise HTTPException(status_code=400, detail="Logo file is empty.")
    if len(content) > MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Logo must be 5 MB or smaller.",
        )

    suffix = Path(filename or "logo.png").suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Logo must be a PNG, JPG, GIF, WebP, or SVG image.",
        )

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        if business_id == DEFAULT_BUSINESS_ID:
            business = ensure_default_business(db)
        else:
            business = Business(id=business_id, name="Default Business")
            db.add(business)
            db.flush()

    target_dir = BUSINESS_LOGO_DIR / str(business_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Overwrite any previous logo file (including different extensions).
    for existing in target_dir.glob("logo.*"):
        try:
            existing.unlink()
        except OSError:
            pass

    destination = target_dir / f"logo{suffix}"
    destination.write_bytes(content)

    relative_path = f"business/{business_id}/logo{suffix}"
    business.logo_path = relative_path
    business.updated_at = utc_now()
    db.commit()
    db.refresh(business)
    return _serialize_business(business)


def resolve_business_logo_file(db: Session, business_id: int) -> tuple[Path, str]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business or not business.logo_path:
        raise HTTPException(status_code=404, detail="Company logo not found.")

    relative = Path(business.logo_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(status_code=404, detail="Company logo not found.")

    uploads_root = UPLOADS_ROOT.resolve()
    path = (uploads_root / relative).resolve()
    try:
        path.relative_to(uploads_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Company logo not found.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Company logo not found.")

    media_type = LOGO_CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return path, media_type


def try_resolve_business_logo_path(db: Session, business_id: int) -> Path | None:
    """Return the on-disk logo path when present; never raises for missing logos."""
    try:
        path, _media_type = resolve_business_logo_file(db, business_id)
        return path
    except HTTPException:
        return None


def format_business_address_lines_from_profile(profile: dict) -> list[str]:
    """Build printable address lines from a serialized business profile dict."""
    lines: list[str] = []
    for key in ("address_line1", "address_line2", "address_line3"):
        cleaned = (profile.get(key) or "").strip()
        if cleaned:
            lines.append(cleaned)
    city_state_zip = ", ".join(
        part
        for part in (
            (profile.get("city") or "").strip(),
            (profile.get("state") or "").strip(),
            (profile.get("zip_code") or "").strip(),
        )
        if part
    )
    if city_state_zip:
        lines.append(city_state_zip)
    country = (profile.get("country") or "").strip()
    if country:
        lines.append(country)
    return lines


def get_business_pdf_branding(db: Session, business_id: int = DEFAULT_BUSINESS_ID) -> dict:
    """Tenant branding for PDF headers/footers (name, address, optional logo path)."""
    profile = get_business_profile(db, business_id)
    name = (profile.get("business_name") or "NEXUS").strip() or "NEXUS"
    logo_path = try_resolve_business_logo_path(db, int(profile.get("business_id") or business_id))
    return {
        "business_name": name,
        "address_lines": format_business_address_lines_from_profile(profile),
        "logo_path": str(logo_path) if logo_path else None,
    }


def _optional_text(value: str | None, *, allow_multiline: bool = False) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not allow_multiline:
        cleaned = " ".join(cleaned.split())
    return cleaned


def _validate_business_profile(
    *,
    business_name: str,
    business_domain: str | None,
    office_phone_number: str | None,
    office_mobile_number: str | None,
    web_url: str | None,
    email_domain: str | None,
) -> None:
    if not business_name:
        raise HTTPException(status_code=400, detail="Business name is required.")

    if business_domain and not DOMAIN_PATTERN.match(business_domain):
        raise HTTPException(
            status_code=400,
            detail="Business domain must be a valid domain (e.g. company.com).",
        )

    if office_phone_number and not OFFICE_PHONE_PATTERN.match(office_phone_number):
        raise HTTPException(
            status_code=400,
            detail="Office phone number must be a valid phone number.",
        )

    if office_mobile_number and not OFFICE_PHONE_PATTERN.match(office_mobile_number):
        raise HTTPException(
            status_code=400,
            detail="Office mobile number must be a valid phone number.",
        )

    if web_url and not _is_valid_web_url(web_url):
        raise HTTPException(
            status_code=400,
            detail="Web URL must be a valid http or https URL.",
        )

    if email_domain and not EMAIL_DOMAIN_PATTERN.match(email_domain):
        raise HTTPException(
            status_code=400,
            detail="Email domain must be a valid domain (e.g. company.com).",
        )


def _is_valid_web_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def _normalize_contact_entries(
    raw: list[dict[str, Any]] | None,
    *,
    value_kind: str,
    legacy_values: tuple[str | None, ...] = (),
    legacy_types: tuple[str, ...] = (),
    validate: bool = True,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            contact_type = str(item.get("type") or "").strip()
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            if validate and value_kind == "phone" and not OFFICE_PHONE_PATTERN.match(value):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid office phone number: {value}",
                )
            if validate and value_kind == "email" and not EMAIL_PATTERN.match(value):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid office email address: {value}",
                )
            if not contact_type:
                contact_type = legacy_types[0] if legacy_types else "General"
            entries.append({"type": contact_type, "value": value})
        # Explicit empty list means "clear contacts" (do not fall back to legacy).
        return entries

    for index, legacy in enumerate(legacy_values):
        cleaned = _optional_text(legacy)
        if not cleaned:
            continue
        contact_type = (
            legacy_types[index]
            if index < len(legacy_types)
            else (legacy_types[-1] if legacy_types else "General")
        )
        entries.append({"type": contact_type, "value": cleaned})
    return entries


def _phone_contacts_for_business(business: Business) -> list[dict[str, str]]:
    raw = getattr(business, "office_phone_contacts", None)
    return _normalize_contact_entries(
        raw if isinstance(raw, list) else None,
        value_kind="phone",
        legacy_values=(business.office_phone_number, business.office_mobile_number),
        legacy_types=("Main Line", "WhatsApp"),
        validate=False,
    )


def _email_contacts_for_business(business: Business) -> list[dict[str, str]]:
    raw = getattr(business, "office_email_contacts", None)
    return _normalize_contact_entries(
        raw if isinstance(raw, list) else None,
        value_kind="email",
        legacy_values=(),
        legacy_types=("General",),
        validate=False,
    )


def _serialize_business(business: Business) -> dict:
    has_logo = bool(business.logo_path)
    phone_active = getattr(business, "office_phone_active", None)
    mobile_active = getattr(business, "office_mobile_active", None)
    phone_contacts = _phone_contacts_for_business(business)
    email_contacts = _email_contacts_for_business(business)
    return {
        "business_id": business.id,
        "business_name": business.name,
        "business_domain": business.domain,
        "address_line1": business.address_line1,
        "address_line2": business.address_line2,
        "address_line3": business.address_line3,
        "city": business.city,
        "state": business.state,
        "country": business.country,
        "zip_code": business.zip_code,
        "office_phone_number": business.office_phone_number
        or (phone_contacts[0]["value"] if phone_contacts else None),
        "office_mobile_number": business.office_mobile_number
        or (phone_contacts[1]["value"] if len(phone_contacts) > 1 else None),
        "office_phone_active": True if phone_active is None else bool(phone_active),
        "office_mobile_active": True if mobile_active is None else bool(mobile_active),
        "office_phone_contacts": phone_contacts,
        "office_email_contacts": email_contacts,
        "web_url": business.web_url,
        "email_domain": business.email_domain,
        "has_logo": has_logo,
        "logo_url": "/api/v1/settings/business-profile/logo" if has_logo else None,
        "updated_at": business.updated_at,
    }
