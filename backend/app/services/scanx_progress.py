"""Step-level ScanX parse progress — persisted on document.metrics_json."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Discrete pipeline steps (weights sum to 100 for simple percent math).
STEP_DEFS: list[dict[str, Any]] = [
    {"id": "queued", "label": "Queued / Started", "weight": 6},
    {"id": "validate_store", "label": "Validate & store", "weight": 10},
    {"id": "classify", "label": "Classify document", "weight": 8},
    {"id": "enhance", "label": "Enhance image", "weight": 10},
    {"id": "extract", "label": "Extract text", "weight": 26},
    {"id": "chunk", "label": "Chunk text", "weight": 12},
    {"id": "embed", "label": "Embeddings (optional)", "weight": 20},
    {"id": "finalize", "label": "Finalize status", "weight": 8},
]

STEP_STATUS_PENDING = "pending"
STEP_STATUS_IN_PROGRESS = "in_progress"
STEP_STATUS_COMPLETE = "complete"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SKIPPED = "skipped"

# API/storage statuses → counsellor-facing labels
STEP_STATUS_LABELS: dict[str, str] = {
    STEP_STATUS_PENDING: "Started",
    STEP_STATUS_IN_PROGRESS: "Progressing",
    STEP_STATUS_COMPLETE: "Complete",
    STEP_STATUS_FAILED: "Failed",
    STEP_STATUS_SKIPPED: "Skipped",
}

# Short “what’s happening” copy for the current step highlight.
CURRENT_STEP_VERBS: dict[str, str] = {
    "queued": "Starting…",
    "validate_store": "Validating & storing…",
    "classify": "Classifying…",
    "enhance": "Enhancing image…",
    "extract": "Extracting text…",
    "chunk": "Chunking text…",
    "embed": "Embedding chunks…",
    "finalize": "Finalizing…",
}

# Seconds a job may sit on “Waiting for worker…” before thread rescue.
# Keep short: Redis may advertise a dead RQ worker while nothing consumes jobs.
STALE_WAITING_WORKER_SECONDS = 2

# Parsing with no metrics progress bump → force reprocess, then fail.
# Heartbeats during OCR should refresh progress_updated_at; this is a backstop
# for truly hung workers (Paddle first-run download can exceed 60s).
STALE_NO_PROGRESS_SECONDS = 180


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utcnow().isoformat()


def initial_progress_steps(
    *,
    waiting_for_worker: bool = False,
    validate_done: bool = False,
) -> list[dict[str, Any]]:
    """Build fresh step list for upload / reprocess."""
    steps: list[dict[str, Any]] = []
    for defn in STEP_DEFS:
        sid = defn["id"]
        row: dict[str, Any] = {
            "id": sid,
            "label": defn["label"],
            "weight": defn["weight"],
            "status": STEP_STATUS_PENDING,
            "status_label": STEP_STATUS_LABELS[STEP_STATUS_PENDING],
            "note": None,
            "started_at": None,
            "finished_at": None,
        }
        if sid == "queued":
            row["status"] = STEP_STATUS_IN_PROGRESS
            row["status_label"] = STEP_STATUS_LABELS[STEP_STATUS_IN_PROGRESS]
            row["started_at"] = _iso_now()
            if waiting_for_worker:
                row["note"] = "Waiting for worker…"
                row["label"] = "Waiting for worker…"
            else:
                row["note"] = "Starting…"
        elif sid == "validate_store" and validate_done:
            row["status"] = STEP_STATUS_COMPLETE
            row["status_label"] = STEP_STATUS_LABELS[STEP_STATUS_COMPLETE]
            row["finished_at"] = _iso_now()
            row["note"] = "Validated at upload"
        steps.append(row)
    return steps


def compute_progress_percent(steps: list[dict[str, Any]]) -> int:
    """Weighted percent: complete/skipped = full weight; in_progress = half."""
    total = sum(int(s.get("weight") or 0) for s in steps) or 100
    earned = 0.0
    for s in steps:
        w = float(s.get("weight") or 0)
        st = s.get("status")
        if st in {STEP_STATUS_COMPLETE, STEP_STATUS_SKIPPED}:
            earned += w
        elif st == STEP_STATUS_IN_PROGRESS:
            earned += w * 0.5
        elif st == STEP_STATUS_FAILED:
            # Count failed step as done for % so UI doesn't stall at mid-bar.
            earned += w
    return max(0, min(100, int(round(100.0 * earned / total))))


def current_step_payload(steps: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Return (step_id, highlight label) for the active or last interesting step."""
    for s in steps:
        if s.get("status") == STEP_STATUS_IN_PROGRESS:
            sid = str(s.get("id") or "")
            note = (s.get("note") or "").strip()
            verb = CURRENT_STEP_VERBS.get(sid) or f"{s.get('label')}…"
            return sid, note or verb
    for s in reversed(steps):
        if s.get("status") == STEP_STATUS_FAILED:
            return str(s.get("id") or ""), f"Failed: {s.get('label')}"
    for s in reversed(steps):
        if s.get("status") in {STEP_STATUS_COMPLETE, STEP_STATUS_SKIPPED}:
            return str(s.get("id") or ""), None
    return None, None


def apply_progress_to_metrics(
    metrics: dict[str, Any] | None,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    out = dict(metrics or {})
    pct = compute_progress_percent(steps)
    step_id, current_label = current_step_payload(steps)
    out["progress_steps"] = steps
    out["progress_percent"] = pct
    out["current_step_id"] = step_id
    out["current_step_label"] = current_label
    out["progress_updated_at"] = _iso_now()
    return out


def set_step(
    steps: list[dict[str, Any]],
    step_id: str,
    status: str,
    *,
    note: str | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    """Update one step; when starting a step, mark prior incomplete as complete."""
    now = _iso_now()
    found = False
    for s in steps:
        if s.get("id") != step_id:
            continue
        found = True
        prev = s.get("status")
        s["status"] = status
        s["status_label"] = STEP_STATUS_LABELS.get(status, status)
        if note is not None:
            s["note"] = note
        if label is not None:
            s["label"] = label
        if status == STEP_STATUS_IN_PROGRESS and not s.get("started_at"):
            s["started_at"] = now
        if status in {
            STEP_STATUS_COMPLETE,
            STEP_STATUS_FAILED,
            STEP_STATUS_SKIPPED,
        }:
            s["finished_at"] = now
            if prev == STEP_STATUS_PENDING and not s.get("started_at"):
                s["started_at"] = now
        break
    if not found:
        return steps

    # Auto-complete earlier pending/in_progress steps when we advance.
    if status in {STEP_STATUS_IN_PROGRESS, STEP_STATUS_COMPLETE}:
        for s in steps:
            if s.get("id") == step_id:
                break
            st = s.get("status")
            if st in {STEP_STATUS_PENDING, STEP_STATUS_IN_PROGRESS}:
                s["status"] = STEP_STATUS_COMPLETE
                s["status_label"] = STEP_STATUS_LABELS[STEP_STATUS_COMPLETE]
                s["finished_at"] = s.get("finished_at") or now
                if not s.get("started_at"):
                    s["started_at"] = now
    return steps


def progress_fields_from_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Slice progress fields for API serializers."""
    m = metrics if isinstance(metrics, dict) else {}
    steps = m.get("progress_steps")
    if not isinstance(steps, list):
        steps = None
    pct = m.get("progress_percent")
    try:
        pct_i = int(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct_i = None
    if pct_i is None and steps:
        pct_i = compute_progress_percent(steps)
    return {
        "progress_percent": pct_i,
        "progress_steps": steps,
        "current_step_id": m.get("current_step_id"),
        "current_step_label": m.get("current_step_label"),
    }


def is_waiting_for_worker(metrics: dict[str, Any] | None) -> bool:
    m = metrics if isinstance(metrics, dict) else {}
    steps = m.get("progress_steps")
    if not isinstance(steps, list):
        return False
    for s in steps:
        if s.get("id") != "queued":
            continue
        if s.get("status") != STEP_STATUS_IN_PROGRESS:
            return False
        note = (s.get("note") or "").lower()
        label = (s.get("label") or "").lower()
        return "waiting for worker" in note or "waiting for worker" in label
    return False


def is_still_on_queued_step(metrics: dict[str, Any] | None) -> bool:
    """True when the pipeline never left the Queued / Started step."""
    m = metrics if isinstance(metrics, dict) else {}
    steps = m.get("progress_steps")
    if not isinstance(steps, list) or not steps:
        return True
    for s in steps:
        if s.get("id") != "queued":
            continue
        return s.get("status") in {STEP_STATUS_PENDING, STEP_STATUS_IN_PROGRESS}
    return True


def _parse_iso_age_seconds(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (_utcnow() - dt).total_seconds())
    except (TypeError, ValueError):
        return None


def waiting_age_seconds(metrics: dict[str, Any] | None) -> float | None:
    """Seconds since queued step started (or progress_updated_at)."""
    m = metrics if isinstance(metrics, dict) else {}
    steps = m.get("progress_steps")
    started: str | None = None
    if isinstance(steps, list):
        for s in steps:
            if s.get("id") == "queued" and s.get("started_at"):
                started = str(s["started_at"])
                break
    if not started:
        started = m.get("progress_updated_at")
    return _parse_iso_age_seconds(started if isinstance(started, str) else None)


def progress_idle_seconds(metrics: dict[str, Any] | None) -> float | None:
    """Seconds since last progress_updated_at (falls back to queued started_at)."""
    m = metrics if isinstance(metrics, dict) else {}
    updated = m.get("progress_updated_at")
    age = _parse_iso_age_seconds(str(updated) if updated else None)
    if age is not None:
        return age
    return waiting_age_seconds(metrics)
