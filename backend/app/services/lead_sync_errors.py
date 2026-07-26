from __future__ import annotations

import json
import re


META_RATE_LIMIT_USER_MESSAGE = (
    "Meta Graph rate limit reached (#4). Facebook temporarily blocked Lead Ads API calls. "
    "Wait 15–60 minutes, then try Sync Now again. Details are in Reports → Meta Leads / Exception Report."
)


def format_lead_sync_error(leadgen_id: str, exc: Exception | str) -> str:
    """Short, report-friendly error text (no SQL dumps)."""
    message = str(exc)
    prefix = f"{leadgen_id}: "
    return _compact_duplicate_message(prefix, message) or f"{prefix}{_truncate_message(message)}"


def is_meta_rate_limit_error(text: str | Exception | None) -> bool:
    """True when Meta returns OAuthException code 4 (application request limit)."""
    if text is None:
        return False
    message = str(text)
    if "(#4)" in message or "Application request limit reached" in message:
        return True
    if re.search(r'"code"\s*:\s*4\b', message):
        return True
    return False


def format_user_facing_sync_error(text: str | Exception | None) -> str:
    """Dashboard-friendly sync failure copy (collapses raw Meta Graph JSON)."""
    if text is None:
        return "Meta lead sync failed."
    message = str(text).strip()
    if not message:
        return "Meta lead sync failed."
    if is_meta_rate_limit_error(message):
        return META_RATE_LIMIT_USER_MESSAGE
    return _truncate_message(message, limit=500)


def sanitize_stored_sync_error(line: str) -> str:
    """Normalize legacy sync log error lines for display."""
    cleaned = line.strip()
    if not cleaned:
        return cleaned
    if is_meta_rate_limit_error(cleaned):
        return META_RATE_LIMIT_USER_MESSAGE
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


def _truncate_message(message: str, *, limit: int = 180) -> str:
    if len(message) <= limit and "SQL:" not in message and "[SQL:" not in message:
        return message
    # Prefer a compact Meta Graph summary over a bare exception class name.
    try:
        json_match = re.search(r"\{.*\}", message)
        if json_match:
            payload = json.loads(json_match.group(0))
            err = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(err, dict):
                code = err.get("code")
                err_message = str(err.get("message") or "").strip()
                if code is not None and err_message:
                    return f"Meta Graph error #{code}: {err_message}"[:limit]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    error_match = re.search(r"(\w+Error|\w+Violation)", message)
    if error_match and len(message) > limit:
        # Avoid collapsing long Graph payloads to just "OAuthException".
        if error_match.group(1) == "OAuthException":
            return message[:limit] + ("…" if len(message) > limit else "")
        return error_match.group(1)
    return message[:limit] + ("…" if len(message) > limit else "")
