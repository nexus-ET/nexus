"""Configurable ScanX date parse / format helpers.

``SCANX_DATE_FORMAT`` controls counsellor-facing passport dates
(``date_of_birth``, ``date_of_issue``, ``date_of_expiry``).

Supported tokens: ``DD``, ``MM``, ``YYYY``, ``YY`` plus separators
``-``, ``/``, ``.``. Default: ``DD-MM-YYYY``.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.config import settings

_DATE_KEYS = frozenset({"date_of_birth", "date_of_issue", "date_of_expiry"})

_TOKEN_RE = re.compile(r"(DD|MM|YYYY|YY|[^DYM]+)", re.IGNORECASE)


def scanx_date_format_pattern() -> str:
    """Return the configured display pattern (e.g. DD-MM-YYYY)."""
    raw = (getattr(settings, "SCANX_DATE_FORMAT", None) or "DD-MM-YYYY").strip()
    return raw or "DD-MM-YYYY"


def _strptime_formats_for_pattern(pattern: str) -> list[str]:
    """Build strptime patterns from SCANX_DATE_FORMAT plus common OCR variants."""
    p = pattern.upper()
    mapping = [
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("DD", "%d"),
        ("MM", "%m"),
    ]
    out = p
    for token, repl in mapping:
        out = out.replace(token, repl)
    formats = [out]
    # Always accept ISO + common Indian OCR variants regardless of display fmt.
    for extra in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d-%m-%y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%m/%d/%Y",
    ):
        if extra not in formats:
            formats.append(extra)
    return formats


def parse_scanx_date(raw: str | None) -> date | None:
    """Parse OCR / ISO / configured-format date text into a ``date``."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Already ISO
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    for fmt in _strptime_formats_for_pattern(scanx_date_format_pattern()):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})$", s)
    if not m:
        return None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000 if y < 50 else 1900
    # Prefer DMY (Indian passports); fall back to MDY.
    for day, month in ((a, b), (b, a)):
        try:
            return date(y, month, day)
        except ValueError:
            continue
    return None


def format_scanx_date(value: date | datetime | str | None) -> str | None:
    """Format a date with ``SCANX_DATE_FORMAT`` (default DD-MM-YYYY)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        d = parse_scanx_date(str(value))
        if d is None:
            return None
    pattern = scanx_date_format_pattern().upper()
    repl = {
        "DD": f"{d.day:02d}",
        "MM": f"{d.month:02d}",
        "YYYY": f"{d.year:04d}",
        "YY": f"{d.year % 100:02d}",
    }
    out: list[str] = []
    for tok in _TOKEN_RE.findall(pattern):
        key = tok.upper()
        if key in repl:
            out.append(repl[key])
        else:
            out.append(tok)
    return "".join(out) or None


def normalize_scanx_date(raw: str | None) -> str | None:
    """Parse any common OCR date and return the configured display string."""
    d = parse_scanx_date(raw)
    if d is None:
        return None
    return format_scanx_date(d)


def apply_scanx_date_format_to_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Normalize passport date keys in-place (and return the same dict)."""
    if not isinstance(fields, dict):
        return fields
    for key in _DATE_KEYS:
        if key not in fields or fields.get(key) in (None, ""):
            continue
        formatted = normalize_scanx_date(str(fields[key]))
        if formatted:
            fields[key] = formatted
    return fields
