from __future__ import annotations

import math
from datetime import datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.lead_quarantine import IngestionQualityReport
from app.schemas.sync_log import ReportsSyncScheduleOut, SyncLogOut, SyncLogsResponse
from app.services.ingestion_report_service import get_ingestion_quality_report
from app.services.lead_sync_settings import get_lead_sync_config_for_api
from app.services.pdf_generator import generate_sync_logs_pdf
from app.services.sync_log_service import (
    ALLOWED_SYNC_LOG_LIMITS,
    MAX_SYNC_LOG_EXPORT_ROWS,
    SYNC_LOG_SORT_FIELDS,
    get_sync_log,
    list_all_sync_logs_for_export,
    list_sync_logs,
)

router = APIRouter()


def _parse_date_param(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        if end_of_day and parsed.time() == time.min:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date value: {value}") from exc


def _build_reports_schedule_help(config: dict) -> str:
    mode = (config.get("mode") or "manual").strip().lower()
    if mode != "automated":
        return "Lead sync is set to Manual in Settings. Only Sync Now runs ingestion; this report is read-only history."
    interval_label = f"{config.get('interval_value')} {config.get('interval_unit')}"
    configured_schedule = config.get("configured_schedule") or interval_label
    next_run = config.get("next_scheduled_run_at")
    if next_run:
        return (
            f"Automated sync is configured in Settings for {interval_label} ({configured_schedule}). "
            f"Next run: {next_run}. This page never triggers sync."
        )
    return (
        f"Automated sync is configured in Settings for {interval_label} ({configured_schedule}). "
        "This page never triggers sync."
    )


@router.get("/reports/sync-schedule", response_model=ReportsSyncScheduleOut)
@router.get("/reports/sync-schedule/", response_model=ReportsSyncScheduleOut)
def read_reports_sync_schedule(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports")),
):
    from app.services.scheduler import reconcile_lead_sync_scheduler_from_settings

    reconcile_lead_sync_scheduler_from_settings()
    config = get_lead_sync_config_for_api(db)
    interval_label = f"{config['interval_value']} {config['interval_unit_label'].lower()}"
    return ReportsSyncScheduleOut(
        mode=config["mode"],
        interval_value=config["interval_value"],
        interval_unit=config["interval_unit"],
        interval_label=interval_label,
        configured_schedule=config.get("configured_schedule"),
        scheduler_enabled=config.get("scheduler_enabled", True),
        scheduler_active=config.get("scheduler_active", False),
        scheduler_is_leader=config.get("scheduler_is_leader", False),
        next_scheduled_run_at=config.get("next_scheduled_run_at"),
        help_text=_build_reports_schedule_help(config),
    )


@router.get("/reports/sync-logs", response_model=SyncLogsResponse)
@router.get("/reports/sync-logs/", response_model=SyncLogsResponse)
def read_sync_logs(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    limit: int = Query(default=25, description="Rows per page (25, 50, or 100)"),
    start_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    end_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    sort_by: str = Query(default="attempt_timestamp", description="Column to sort by"),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports")),
):
    if limit not in ALLOWED_SYNC_LOG_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be one of {sorted(ALLOWED_SYNC_LOG_LIMITS)}.",
        )
    if sort_by not in SYNC_LOG_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of {sorted(SYNC_LOG_SORT_FIELDS)}.",
        )

    logs, total_count = list_sync_logs(
        db,
        start_date=_parse_date_param(start_date),
        end_date=_parse_date_param(end_date, end_of_day=True),
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total_pages = max(1, math.ceil(total_count / limit)) if total_count else 1
    safe_page = min(page, total_pages) if total_count else page

    return SyncLogsResponse(
        logs=logs,
        total_count=total_count,
        page=safe_page,
        limit=limit,
        total_pages=total_pages,
    )


def _export_sync_logs_pdf_response(
    db: Session,
    *,
    start_date: str | None,
    end_date: str | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
) -> Response:
    if sort_by not in SYNC_LOG_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of {sorted(SYNC_LOG_SORT_FIELDS)}.",
        )

    parsed_start = _parse_date_param(start_date)
    parsed_end = _parse_date_param(end_date, end_of_day=True)

    try:
        logs, total_count = list_all_sync_logs_for_export(
            db,
            start_date=parsed_start,
            end_date=parsed_end,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    if total_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No sync logs match the selected filters.",
        )

    pdf_bytes = generate_sync_logs_pdf(
        db,
        logs=logs,
        start_date=parsed_start,
        end_date=parsed_end,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    filename_date = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="sync-logs-{filename_date}.pdf"',
            "X-Export-Row-Count": str(total_count),
            "X-Export-Row-Limit": str(MAX_SYNC_LOG_EXPORT_ROWS),
        },
    )


@router.get("/reports/export/sync-logs")
@router.get("/reports/export/sync-logs/")
@router.get("/reports/sync-logs/export/pdf")
@router.get("/reports/sync-logs/export/pdf/")
def export_sync_logs_pdf(
    start_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    end_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    sort_by: str = Query(default="attempt_timestamp", description="Column to sort by"),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports")),
):
    """Export all matching sync logs as PDF (ignores pagination)."""
    return _export_sync_logs_pdf_response(
        db,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/reports/sync-logs/by-id/{log_id}", response_model=SyncLogOut)
@router.get("/reports/sync-logs/by-id/{log_id}/", response_model=SyncLogOut)
@router.get("/reports/sync-logs/{log_id}", response_model=SyncLogOut, include_in_schema=False)
@router.get("/reports/sync-logs/{log_id}/", response_model=SyncLogOut, include_in_schema=False)
def read_sync_log(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports")),
):
    log = get_sync_log(db, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Sync log not found.")
    return log


@router.get("/reports/ingestion-quality", response_model=IngestionQualityReport)
@router.get("/reports/ingestion-quality/", response_model=IngestionQualityReport)
def read_ingestion_quality(
    start_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    end_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    sync_mode: Literal["AUTOMATED", "MANUAL", "automated", "manual"] | None = Query(
        default=None,
        description="Filter by sync mode",
    ),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports")),
):
    mode_filter = sync_mode.upper() if sync_mode else None
    if mode_filter and mode_filter not in {"AUTOMATED", "MANUAL"}:
        raise HTTPException(status_code=400, detail="sync_mode must be AUTOMATED or MANUAL.")
    return get_ingestion_quality_report(
        db,
        start_date=_parse_date_param(start_date),
        end_date=_parse_date_param(end_date, end_of_day=True),
        sync_mode=mode_filter,
    )
