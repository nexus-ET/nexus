"""Guards against parallel ScanX jobs for the same original filename.

Blocks a second upload while another document for the same lead still has a
non-terminal status (``uploading`` / ``parsing``). Terminal rows
(``action_required``, ``verified``, ``red_flag``) — or a cancelled/deleted
row that no longer exists — allow a later rescan of the same name.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.scanx import STATUS_PARSING, STATUS_UPLOADING
from app.models.scanx import ScanxDocument

# Queued / running pipeline only. Terminal CRM statuses must not block a rescan.
SCANX_IN_FLIGHT_STATUSES: frozenset[str] = frozenset({STATUS_UPLOADING, STATUS_PARSING})


def normalize_scanx_filename(filename: str | None) -> str:
    """Basename only, stripped — used for case-insensitive duplicate checks."""
    return Path((filename or "document").strip() or "document").name


def filenames_match_ci(left: str | None, right: str | None) -> bool:
    return normalize_scanx_filename(left).lower() == normalize_scanx_filename(right).lower()


def is_in_flight_status(status: str | None) -> bool:
    return (status or "").strip().lower() in SCANX_IN_FLIGHT_STATUSES


def find_inflight_same_filename(
    db: Session,
    *,
    lead_id: int,
    original_filename: str,
) -> ScanxDocument | None:
    """Return an in-flight ScanX row for this lead with the same original filename."""
    name = normalize_scanx_filename(original_filename)
    if not name:
        return None
    return (
        db.query(ScanxDocument)
        .filter(
            ScanxDocument.lead_id == int(lead_id),
            ScanxDocument.status.in_(tuple(SCANX_IN_FLIGHT_STATUSES)),
            func.lower(ScanxDocument.original_filename) == name.lower(),
        )
        .order_by(ScanxDocument.created_at.desc())
        .first()
    )
