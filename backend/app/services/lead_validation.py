from __future__ import annotations

import re
import unicodedata
from typing import Any

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
# E.164-style international numbers (+country code, 7–15 digits total).
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")

ERROR_INVALID_EMAIL = "Invalid Email"
ERROR_INVALID_PHONE = "Invalid Phone"
ERROR_UNICODE = "Unicode Issues"
ERROR_MISSING_LEADGEN = "Missing Leadgen ID"


def _is_synthetic_meta_email(email: str | None) -> bool:
    if not email:
        return True
    return email.endswith("@meta.nexus") or email.startswith("meta_")


def _normalize_phone(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"[\s().-]", "", cleaned)
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    return cleaned


def detect_unicode_issues(value: str) -> bool:
    for char in value:
        category = unicodedata.category(char)
        if category in {"Cc", "Cf"} and char not in {"\t", "\n"}:
            return True
        if category == "Co":
            return True
    return False


def validate_lead_payload(lead_data: dict[str, Any]) -> list[str]:
    """Return human-readable validation error labels (empty list = valid)."""
    errors: list[str] = []

    leadgen_id = (lead_data.get("leadgen_id") or lead_data.get("meta_leadgen_id") or "").strip()
    if not leadgen_id:
        errors.append(ERROR_MISSING_LEADGEN)

    email = lead_data.get("email")
    if email and not _is_synthetic_meta_email(str(email)):
        if not EMAIL_PATTERN.match(str(email).strip()):
            errors.append(ERROR_INVALID_EMAIL)

    phone = lead_data.get("phone_number") or lead_data.get("phone")
    if phone:
        normalized = _normalize_phone(str(phone))
        if not PHONE_PATTERN.match(normalized):
            errors.append(ERROR_INVALID_PHONE)

    for field in ("full_name", "academic_summary"):
        value = lead_data.get(field)
        if value and detect_unicode_issues(str(value)) and ERROR_UNICODE not in errors:
            errors.append(ERROR_UNICODE)

    additional = lead_data.get("additional_data")
    if isinstance(additional, dict):
        for value in additional.values():
            if isinstance(value, str) and detect_unicode_issues(value):
                if ERROR_UNICODE not in errors:
                    errors.append(ERROR_UNICODE)
                break

    return errors


def primary_error_code(errors: list[str]) -> str:
    if not errors:
        return "valid"
    mapping = {
        ERROR_INVALID_EMAIL: "invalid_email",
        ERROR_INVALID_PHONE: "invalid_phone",
        ERROR_UNICODE: "unicode_issues",
        ERROR_MISSING_LEADGEN: "missing_leadgen_id",
    }
    return mapping.get(errors[0], "validation_failed")
