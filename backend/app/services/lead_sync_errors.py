from __future__ import annotations

import re


def format_lead_sync_error(leadgen_id: str, exc: Exception | str) -> str:
    """Short, report-friendly error text (no SQL dumps)."""
    message = str(exc)
    prefix = f"{leadgen_id}: "
    return _compact_duplicate_message(prefix, message) or f"{prefix}{_truncate_message(message)}"


def sanitize_stored_sync_error(line: str) -> str:
    """Normalize legacy sync log error lines for display."""
    cleaned = line.strip()
    if not cleaned:
        return cleaned
    if ": " not in cleaned:
        return _truncate_message(cleaned)
    leadgen_id, message = cleaned.split(": ", 1)
    if leadgen_id.isdigit():
        compact = _compact_duplicate_message(f"{leadgen_id}: ", message)
        if compact:
            return compact
        return f"{leadgen_id}: {_truncate_message(message)}"
    return _truncate_message(cleaned)


def _compact_duplicate_message(prefix: str, message: str) -> str | None:
    email_match = re.search(r"Key \(email\)=\(([^)]+)\)", message)
    if "ix_leads_email" in message or email_match:
        email = email_match.group(1) if email_match else "unknown"
        return f"{prefix}duplicate email ({email})"
    phone_match = re.search(r"Key \(phone_number\)=\(([^)]+)\)", message)
    if "phone_number" in message and phone_match:
        return f"{prefix}duplicate phone ({phone_match.group(1)})"
    if "meta_leadgen_id" in message:
        return f"{prefix}duplicate Meta lead id"
    return None


def _truncate_message(message: str) -> str:
    if len(message) <= 180 and "SQL:" not in message and "[SQL:" not in message:
        return message
    error_match = re.search(r"(\w+Error|\w+Violation)", message)
    if error_match:
        return error_match.group(1)
    return message[:180] + ("…" if len(message) > 180 else "")
