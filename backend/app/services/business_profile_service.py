from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.user import User

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
    cleaned_office_phone = _optional_text(office_phone_number)
    cleaned_office_mobile = _optional_text(office_mobile_number)
    cleaned_web_url = _optional_text(web_url)
    cleaned_email_domain = _optional_text(email_domain)

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
    business.web_url = cleaned_web_url
    business.email_domain = cleaned_email_domain.lower() if cleaned_email_domain else None
    business.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(business)
    return _serialize_business(business)


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


def _serialize_business(business: Business) -> dict:
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
        "office_phone_number": business.office_phone_number,
        "office_mobile_number": business.office_mobile_number,
        "web_url": business.web_url,
        "email_domain": business.email_domain,
        "updated_at": business.updated_at,
    }
