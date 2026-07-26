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
from app.schemas.exception_log import (
    ExceptionLogAutoResolveRequest,
    ExceptionLogAutoResolveResponse,
    ExceptionLogCreateRequest,
    ExceptionLogOut,
    ExceptionLogRetentionSetting,
    ExceptionLogStatusUpdate,
    ExceptionLogsResponse,
)
from app.services.ingestion_report_service import get_ingestion_quality_report
from app.services.lead_sync_settings import get_lead_sync_config_for_api
from app.services.pdf_generator import generate_exception_logs_pdf, generate_sync_logs_pdf
from app.services.exception_log_service import (
    ALLOWED_EXCEPTION_LOG_LIMITS,
    EXCEPTION_LOG_SORT_FIELDS,
    RESOLVER_CURSOR,
    RESOLVER_PAGE_REFRESH,
    RESOLVER_SERVER_RECOVERY,
    RESOLVER_SUCCESSFUL_SYNC,
    auto_resolve_by_cursor,
    auto_resolve_lead_sync_failure_exceptions,
    auto_resolve_lead_sync_lock_exceptions,
    auto_resolve_transient_client_exceptions,
    build_auto_resolution_comment,
    cleanup_old_exception_logs,
    get_exception_log_retention_days,
    list_all_exception_logs_for_export,
    list_exception_logs,
    record_exception_event,
    serialize_exception_log,
    update_exception_log_status,
)
from app.services.sync_log_service import (
    ALLOWED_SYNC_LOG_LIMITS,
    MAX_SYNC_LOG_EXPORT_ROWS,
    SYNC_LOG_SORT_FIELDS,
    get_sync_log,
    list_all_sync_logs_for_export,
    list_sync_logs,
    format_user_label,
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
    _: User = Depends(deps.require_page_access("/reports/meta-leads")),
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
    _: User = Depends(deps.require_page_access("/reports/meta-leads")),
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
    _: User = Depends(deps.require_page_access("/reports/meta-leads")),
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
    _: User = Depends(deps.require_page_access("/reports/meta-leads")),
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
    _: User = Depends(deps.require_page_access("/reports/meta-leads")),
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


@router.get("/reports/exception-logs", response_model=ExceptionLogsResponse)
@router.get("/reports/exception-logs/", response_model=ExceptionLogsResponse)
def read_exception_logs(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    limit: int = Query(default=25, description="Rows per page (25, 50, or 100)"),
    start_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    end_date: str | None = Query(default=None, description="ISO date or datetime (inclusive)"),
    sort_by: str = Query(default="attempt_timestamp", description="Column to sort by"),
    sort_order: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports/exceptions")),
):
    if limit not in ALLOWED_EXCEPTION_LOG_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be one of {sorted(ALLOWED_EXCEPTION_LOG_LIMITS)}.",
        )
    if sort_by not in EXCEPTION_LOG_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of {sorted(EXCEPTION_LOG_SORT_FIELDS)}.",
        )

    logs, total_count = list_exception_logs(
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

    return ExceptionLogsResponse(
        logs=logs,
        total_count=total_count,
        page=safe_page,
        limit=limit,
        total_pages=total_pages,
    )


def _export_exception_logs_pdf_response(
    db: Session,
    *,
    start_date: str | None,
    end_date: str | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
) -> Response:
    if sort_by not in EXCEPTION_LOG_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of {sorted(EXCEPTION_LOG_SORT_FIELDS)}.",
        )

    parsed_start = _parse_date_param(start_date)
    parsed_end = _parse_date_param(end_date, end_of_day=True)

    try:
        logs, total_count = list_all_exception_logs_for_export(
            db,
            start_date=parsed_start,
            end_date=parsed_end,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    if total_count == 0:
        raise HTTPException(status_code=400, detail="No exception logs match the selected filters.")

    pdf_bytes = generate_exception_logs_pdf(
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
            "Content-Disposition": f'attachment; filename="exception-report-{filename_date}.pdf"',
        },
    )


@router.get("/reports/export/exception-logs")
@router.get("/reports/export/exception-logs/")
@router.get("/reports/exception-logs/export/pdf")
@router.get("/reports/exception-logs/export/pdf/")
def export_exception_logs_pdf(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    sort_by: str = Query(default="attempt_timestamp"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports/exceptions")),
):
    return _export_exception_logs_pdf_response(
        db,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/reports/exception-logs", response_model=ExceptionLogOut)
@router.post("/reports/exception-logs/", response_model=ExceptionLogOut)
def create_exception_log(
    payload: ExceptionLogCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Allow authenticated clients to report timeouts/errors into the Exception Report."""
    row = record_exception_event(
        db,
        severity=payload.severity,
        source=payload.source,
        category=payload.category,
        message=payload.message,
        details=payload.details,
        page_path=payload.page_path,
        exception_type=payload.exception_type,
        related_resource=payload.related_resource,
        related_id=payload.related_id,
        triggered_by_user=format_user_label(current_user),
        triggered_by_user_id=current_user.id,
        commit=True,
    )
    return serialize_exception_log(row)


@router.patch("/reports/exception-logs/{exception_log_id}/status", response_model=ExceptionLogOut)
def set_exception_log_status(
    exception_log_id: int,
    payload: ExceptionLogStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports/exceptions")),
):
    resolved_by = payload.resolved_by
    allow_auto = bool(resolved_by and resolved_by != "admin")
    try:
        row = update_exception_log_status(
            db,
            exception_log_id,
            status=payload.status,
            resolution_comment=payload.resolution_comment,
            resolved_by=resolved_by if allow_auto else None,
            allow_auto_comment=allow_auto,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Exception log not found.")
    return serialize_exception_log(row)


@router.post(
    "/reports/exception-logs/auto-resolve",
    response_model=ExceptionLogAutoResolveResponse,
)
@router.post(
    "/reports/exception-logs/auto-resolve/",
    response_model=ExceptionLogAutoResolveResponse,
)
def auto_resolve_exception_logs(
    payload: ExceptionLogAutoResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Bulk-resolve open exceptions with an automatically generated resolution comment.

    Used after Cursor fixes, page refresh (transient client errors), and server recovery.
    page_refresh / transient_client: any authenticated user (fires on healthy app load).
    Other modes: require Exception Report page access.
    """
    mode = payload.mode
    if mode not in {"page_refresh", "transient_client"}:
        from app.services.navigation_rbac import check_page_access

        if not check_page_access(db, current_user, "/reports/exceptions"):
            raise HTTPException(
                status_code=403,
                detail="Access denied for route '/reports/exceptions'.",
            )

    detail = payload.detail
    ids = payload.exception_ids

    if mode in {"page_refresh", "transient_client"}:
        count = auto_resolve_transient_client_exceptions(db, detail=detail)
        comment = build_auto_resolution_comment(RESOLVER_PAGE_REFRESH, detail=detail)
    elif mode in {"server_recovery", "lead_sync_lock"}:
        count = auto_resolve_lead_sync_lock_exceptions(db, detail=detail)
        comment = build_auto_resolution_comment(RESOLVER_SERVER_RECOVERY, detail=detail)
    elif mode == "successful_sync" or mode == "lead_sync_failure":
        count = auto_resolve_lead_sync_failure_exceptions(db, detail=detail)
        comment = build_auto_resolution_comment(RESOLVER_SUCCESSFUL_SYNC, detail=detail)
    elif mode == "cursor_agent":
        count = auto_resolve_by_cursor(
            db,
            exception_ids=ids,
            detail=detail,
        )
        comment = build_auto_resolution_comment(RESOLVER_CURSOR, detail=detail)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported auto-resolve mode: {mode}")

    return ExceptionLogAutoResolveResponse(
        resolved_count=count,
        mode=mode,
        resolution_comment=comment if count else None,
    )


@router.get("/reports/exception-logs/retention", response_model=ExceptionLogRetentionSetting)
@router.get("/reports/exception-logs/retention/", response_model=ExceptionLogRetentionSetting)
def read_exception_log_retention(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports/exceptions")),
):
    return ExceptionLogRetentionSetting(
        exception_log_retention_days=get_exception_log_retention_days(db)
    )


@router.put("/reports/exception-logs/retention", response_model=ExceptionLogRetentionSetting)
@router.put("/reports/exception-logs/retention/", response_model=ExceptionLogRetentionSetting)
def update_exception_log_retention(
    payload: ExceptionLogRetentionSetting,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_page_access("/reports/exceptions")),
):
    """Save retention window and immediately purge rows older than that window."""
    from app.models.dynamic_setting import DynamicSetting
    from app.services.settings_service import clear_settings_cache

    setting = (
        db.query(DynamicSetting)
        .filter(DynamicSetting.key == "EXCEPTION_LOG_RETENTION_DAYS")
        .first()
    )
    if setting is None:
        setting = DynamicSetting(
            key="EXCEPTION_LOG_RETENTION_DAYS",
            value=str(payload.exception_log_retention_days),
        )
        db.add(setting)
    else:
        setting.value = str(payload.exception_log_retention_days)
    db.commit()
    clear_settings_cache()

    deleted_count = cleanup_old_exception_logs(db)
    return ExceptionLogRetentionSetting(
        exception_log_retention_days=get_exception_log_retention_days(db),
        deleted_count=deleted_count,
    )
