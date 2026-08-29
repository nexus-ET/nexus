from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constants.contact_types import (
    EMAIL_CONTACT_TYPES,
    EMAIL_TYPE_GENERAL,
    FAX_CONTACT_TYPES,
    FAX_TYPE_MAIN,
    PHONE_CONTACT_TYPES,
    PHONE_TYPE_MAIN,
    WEB_LINK_TYPE_WEBSITE,
    WEB_LINK_TYPES,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactEntry(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    value: str = Field(default="", max_length=250)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: object) -> str:
        return str(value or "").strip()


def _normalize_contact_items(
    raw: object,
    *,
    allowed_types: tuple[str, ...],
    default_type: str,
) -> list[ContactEntry]:
    if raw is None:
        return [ContactEntry(type=default_type, value="")]

    if not isinstance(raw, list):
        return [ContactEntry(type=default_type, value="")]

    if not raw:
        return [ContactEntry(type=default_type, value="")]

    normalized: list[ContactEntry] = []
    for index, item in enumerate(raw):
        if isinstance(item, ContactEntry):
            contact_type = item.type.strip() or (
                default_type if index == 0 else allowed_types[-1]
            )
            value = item.value.strip()
            if contact_type not in allowed_types:
                contact_type = allowed_types[-1]
            if value:
                normalized.append(ContactEntry(type=contact_type, value=value))
            continue

        if isinstance(item, str):
            stripped = item.strip()
            if not stripped:
                continue
            contact_type = default_type if index == 0 else allowed_types[-1]
            normalized.append(ContactEntry(type=contact_type, value=stripped))
            continue

        if isinstance(item, dict):
            contact_type = str(item.get("type") or "").strip() or (
                default_type if index == 0 else allowed_types[-1]
            )
            value = str(item.get("value") or "").strip()
            if contact_type not in allowed_types:
                contact_type = allowed_types[-1]
            if value:
                normalized.append(ContactEntry(type=contact_type, value=value))
            continue

        # Duck-type objects that expose type/value attributes (e.g. ORM rows).
        contact_type = str(getattr(item, "type", "") or "").strip() or (
            default_type if index == 0 else allowed_types[-1]
        )
        value = str(getattr(item, "value", "") or "").strip()
        if not value:
            continue
        if contact_type not in allowed_types:
            contact_type = allowed_types[-1]
        normalized.append(ContactEntry(type=contact_type, value=value))

    return normalized or [ContactEntry(type=default_type, value="")]


def normalize_phone_contacts(raw: object) -> list[ContactEntry]:
    return _normalize_contact_items(
        raw,
        allowed_types=PHONE_CONTACT_TYPES,
        default_type=PHONE_TYPE_MAIN,
    )


def normalize_fax_contacts(raw: object, legacy_fax_number: object = None) -> list[ContactEntry]:
    if isinstance(raw, list) and raw:
        return _normalize_contact_items(
            raw,
            allowed_types=FAX_CONTACT_TYPES,
            default_type=FAX_TYPE_MAIN,
        )
    legacy = str(legacy_fax_number or "").strip()
    if legacy:
        return [ContactEntry(type=FAX_TYPE_MAIN, value=legacy)]
    return [ContactEntry(type=FAX_TYPE_MAIN, value="")]


def normalize_email_contacts(raw: object) -> list[ContactEntry]:
    return _normalize_contact_items(
        raw,
        allowed_types=EMAIL_CONTACT_TYPES,
        default_type=EMAIL_TYPE_GENERAL,
    )


def web_url_to_origin(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    candidate = cleaned if cleaned.startswith(("http://", "https://")) else f"https://{cleaned}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return cleaned
    scheme = parsed.scheme or "https"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


def _strip_web_link_origins(entries: list[ContactEntry]) -> list[ContactEntry]:
    stripped: list[ContactEntry] = []
    for entry in entries:
        value = entry.value.strip()
        if not value:
            continue
        origin = web_url_to_origin(value)
        if origin:
            stripped.append(ContactEntry(type=entry.type, value=origin))
    return stripped or [ContactEntry(type=WEB_LINK_TYPE_WEBSITE, value="")]


def normalize_web_links(raw: object, legacy_url: object = None) -> list[ContactEntry]:
    if isinstance(raw, list) and raw:
        entries = _normalize_contact_items(
            raw,
            allowed_types=WEB_LINK_TYPES,
            default_type=WEB_LINK_TYPE_WEBSITE,
        )
        return _strip_web_link_origins(entries)
    legacy = str(legacy_url or "").strip()
    if legacy:
        origin = web_url_to_origin(legacy)
        if origin:
            return [ContactEntry(type=WEB_LINK_TYPE_WEBSITE, value=origin)]
    return [ContactEntry(type=WEB_LINK_TYPE_WEBSITE, value="")]


def primary_web_url(entries: list[ContactEntry] | None) -> str | None:
    serialized = serialize_contacts(entries or [])
    if not serialized:
        return None
    for entry in serialized:
        if entry["type"] == WEB_LINK_TYPE_WEBSITE:
            return entry["value"]
    return serialized[0]["value"]


def migrate_legacy_web_link_fields(
    data: object,
    *,
    links_key: str = "web_links",
    legacy_key: str = "institution_web_url",
) -> object:
    """Promote a legacy single URL string into web_links when needed."""
    if not isinstance(data, dict):
        return data
    if data.get(links_key) not in (None, []):
        return data
    legacy = data.get(legacy_key)
    if legacy in (None, ""):
        return data
    return {
        **data,
        links_key: [{"type": WEB_LINK_TYPE_WEBSITE, "value": str(legacy).strip()}],
    }


def serialize_contacts(entries: list[ContactEntry]) -> list[dict[str, str]]:
    return [
        {"type": entry.type, "value": entry.value.strip()}
        for entry in entries
        if entry.value.strip()
    ]


def assert_optional_email_formats(entries: list[ContactEntry] | None) -> None:
    """Reject malformed emails; empty lists and blank values are allowed."""
    for entry in entries or []:
        value = (entry.value or "").strip()
        if value and not _EMAIL_RE.match(value):
            raise ValueError(f"Invalid email address: {value}")


def migrate_legacy_fax_fields(data: object) -> object:
    """Promote legacy fax_number string into fax_numbers list when needed."""
    if not isinstance(data, dict):
        return data
    if data.get("fax_numbers") not in (None, []):
        return data
    legacy = data.get("fax_number")
    if legacy in (None, ""):
        return data
    return {
        **data,
        "fax_numbers": [{"type": FAX_TYPE_MAIN, "value": str(legacy).strip()}],
    }


class ContactListFields(BaseModel):
    phone_numbers: list[ContactEntry] = Field(default_factory=list)
    email_addresses: list[ContactEntry] = Field(default_factory=list)

    @field_validator("phone_numbers", mode="before")
    @classmethod
    def coerce_phone_numbers(cls, value: object) -> list[ContactEntry]:
        return normalize_phone_contacts(value)

    @field_validator("email_addresses", mode="before")
    @classmethod
    def coerce_email_addresses(cls, value: object) -> list[ContactEntry]:
        return normalize_email_contacts(value)


class FaxContactListFields(BaseModel):
    fax_numbers: list[ContactEntry] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fax(cls, data: object) -> object:
        return migrate_legacy_fax_fields(data)

    @field_validator("fax_numbers", mode="before")
    @classmethod
    def coerce_fax_numbers(cls, value: object) -> list[ContactEntry]:
        return normalize_fax_contacts(value)

    @model_validator(mode="after")
    def validate_fax_numbers(self) -> FaxContactListFields:
        allowed = set(FAX_CONTACT_TYPES)
        for entry in self.fax_numbers:
            if entry.type not in allowed:
                raise ValueError(f"Invalid fax type: {entry.type}")
        return self


class WebLinkListFields(BaseModel):
    web_links: list[ContactEntry] = Field(default_factory=list)

    @field_validator("web_links", mode="before")
    @classmethod
    def coerce_web_links(cls, value: object) -> list[ContactEntry]:
        return normalize_web_links(value)

    @model_validator(mode="after")
    def validate_web_links(self) -> WebLinkListFields:
        allowed = set(WEB_LINK_TYPES)
        for entry in self.web_links:
            if entry.type not in allowed:
                raise ValueError(f"Invalid web link type: {entry.type}")
            value = entry.value.strip()
            if not value:
                continue
            if len(value) > 250:
                raise ValueError("Web URL must be 250 characters or fewer.")
            if not (value.startswith("http://") or value.startswith("https://")):
                raise ValueError(f"Invalid web URL: {value}")
        return self


class InstitutionWebLinkListFields(WebLinkListFields):
    institution_web_url: str | None = Field(default=None, max_length=250)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_institution_web_url(cls, data: object) -> object:
        return migrate_legacy_web_link_fields(
            data,
            links_key="web_links",
            legacy_key="institution_web_url",
        )

    @model_validator(mode="after")
    def sync_institution_web_url(self) -> InstitutionWebLinkListFields:
        self.institution_web_url = primary_web_url(self.web_links)
        return self


class CollegeWebLinkListFields(WebLinkListFields):
    web_url: str | None = Field(default=None, max_length=250)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_college_web_url(cls, data: object) -> object:
        return migrate_legacy_web_link_fields(
            data,
            links_key="web_links",
            legacy_key="web_url",
        )

    @model_validator(mode="after")
    def sync_college_web_url(self) -> CollegeWebLinkListFields:
        self.web_url = primary_web_url(self.web_links)
        return self


class PhoneContactListMixin(ContactListFields):
    @model_validator(mode="after")
    def validate_phone_numbers(self) -> PhoneContactListMixin:
        allowed = set(PHONE_CONTACT_TYPES)
        for entry in self.phone_numbers:
            if entry.type not in allowed:
                raise ValueError(f"Invalid phone type: {entry.type}")

        has_phone = any(entry.value.strip() for entry in self.phone_numbers)
        if not has_phone:
            raise ValueError("At least one phone number is required.")

        return self


class OptionalPhoneContactListMixin(ContactListFields):
    """Phone list with type checks only — empty phone lists are allowed."""

    @model_validator(mode="after")
    def validate_phone_numbers(self) -> OptionalPhoneContactListMixin:
        allowed = set(PHONE_CONTACT_TYPES)
        for entry in self.phone_numbers:
            if entry.type not in allowed:
                raise ValueError(f"Invalid phone type: {entry.type}")
        return self


class EmailContactListMixin(ContactListFields):
    @model_validator(mode="after")
    def validate_email_addresses(self) -> EmailContactListMixin:
        allowed = set(EMAIL_CONTACT_TYPES)
        for entry in self.email_addresses:
            if entry.type not in allowed:
                raise ValueError(f"Invalid email type: {entry.type}")
            value = entry.value.strip()
            if value and not _EMAIL_RE.match(value):
                raise ValueError(f"Invalid email address: {value}")

        has_email = any(entry.value.strip() for entry in self.email_addresses)
        if not has_email:
            raise ValueError("At least one email address is required.")

        return self


class OptionalEmailContactListMixin(ContactListFields):
    """Email list with type/format checks — empty email lists are allowed."""

    @model_validator(mode="after")
    def validate_email_addresses(self) -> OptionalEmailContactListMixin:
        allowed = set(EMAIL_CONTACT_TYPES)
        for entry in self.email_addresses:
            if entry.type not in allowed:
                raise ValueError(f"Invalid email type: {entry.type}")
            value = entry.value.strip()
            if value and not _EMAIL_RE.match(value):
                raise ValueError(f"Invalid email address: {value}")
        return self
