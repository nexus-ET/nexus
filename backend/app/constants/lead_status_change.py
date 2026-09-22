"""Allowed reason labels for All Leads active/inactive transitions."""

from __future__ import annotations

INACTIVE_STATUS_REASONS: tuple[str, ...] = (
    "Course Completed",
    "Fee Due / Non-Payment",
    "Dropped Out",
    "Personal Reasons",
    "Unresponsive",
)

ACTIVE_STATUS_REASONS: tuple[str, ...] = (
    "Fee Cleared / Paid",
    "Re-enrollment Requested",
    "Deferral Ended",
    "Administrative Correction",
    "Other",
)

MAX_STATUS_REASONS = 5


def allowed_reasons_for(is_active: bool) -> tuple[str, ...]:
    return ACTIVE_STATUS_REASONS if is_active else INACTIVE_STATUS_REASONS


def normalize_status_reasons(is_active: bool, reasons: list[str] | None) -> list[str]:
    allowed = set(allowed_reasons_for(is_active))
    normalized: list[str] = []
    seen: set[str] = set()
    for item in reasons or []:
        label = (item or "").strip()
        if not label or label in seen or label not in allowed:
            continue
        seen.add(label)
        normalized.append(label)
        if len(normalized) >= MAX_STATUS_REASONS:
            break
    return normalized
