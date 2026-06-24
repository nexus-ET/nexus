from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.counselling import (
    AvailableAdminsResponse,
    BookingAssignRequest,
    BookingCommunicationsResponse,
    BookingCreateRequest,
    BookingOut,
    BookingSwitchRequest,
    MyBookingReassignRequest,
    MyBookingsResponse,
    PendingBookingsResponse,
    ScheduleGridResponse,
)
from app.schemas.pipeline import (
    PipelineAnalyticsResponse,
    PipelineConfigResponse,
    SessionCompleteRequest,
    SessionCompleteResponse,
)
from app.services import counselling_service
from app.services.audit_service import log_action
from app.services.notification_service import run_assignment_notifications
from app.services.pipeline_service import complete_session, get_pipeline_analytics, get_pipeline_config

router = APIRouter()


def _serialize_booking_out(booking, admin=None) -> BookingOut:
    payload = counselling_service._serialize_booking(booking, admin)
    return BookingOut(**payload)


@router.get("/bookings/pending", response_model=PendingBookingsResponse)
@router.get("/bookings/pending/", response_model=PendingBookingsResponse)
def list_pending_bookings(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return counselling_service.get_pending_bookings(db)


@router.get("/bookings/grid", response_model=ScheduleGridResponse)
@router.get("/bookings/grid/", response_model=ScheduleGridResponse)
def get_schedule_grid(
    date: date | None = Query(default=None, description="Focus date (T) for the schedule grid"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return counselling_service.get_schedule_grid(db, date)


@router.get("/bookings/mine", response_model=MyBookingsResponse)
@router.get("/bookings/mine/", response_model=MyBookingsResponse)
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_my_bookings(db, current_user.id)


@router.get("/bookings/mine/{booking_id}/communications", response_model=BookingCommunicationsResponse)
@router.get("/bookings/mine/{booking_id}/communications/", response_model=BookingCommunicationsResponse)
def get_my_booking_communications(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_my_booking_communications(db, current_user.id, booking_id)


@router.get("/bookings/{booking_id}/communications", response_model=BookingCommunicationsResponse)
@router.get("/bookings/{booking_id}/communications/", response_model=BookingCommunicationsResponse)
def get_booking_communications(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    return counselling_service.get_booking_communications(db, booking_id)


@router.get("/admins/available", response_model=AvailableAdminsResponse)
@router.get("/admins/available/", response_model=AvailableAdminsResponse)
def list_available_admins(
    time: datetime = Query(..., description="Exact appointment timestamp"),
    exclude_booking_id: int | None = Query(default=None),
    exclude_admin_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return counselling_service.get_available_admins(
        db, time, exclude_booking_id, exclude_admin_id
    )


@router.get("/pipeline/config", response_model=PipelineConfigResponse)
@router.get("/pipeline/config/", response_model=PipelineConfigResponse)
def read_pipeline_config(
    _: User = Depends(deps.require_counselling_admin),
):
    return PipelineConfigResponse(**get_pipeline_config())


@router.get("/pipeline/analytics", response_model=PipelineAnalyticsResponse)
@router.get("/pipeline/analytics/", response_model=PipelineAnalyticsResponse)
def read_pipeline_analytics(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return PipelineAnalyticsResponse(**get_pipeline_analytics(db))


@router.post("/bookings", response_model=BookingOut)
@router.post("/bookings/", response_model=BookingOut)
def create_pending_booking(
    payload: BookingCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    booking = counselling_service.create_pending_booking(
        db,
        payload.scheduled_time,
        payload.candidate_name,
        str(payload.candidate_email) if payload.candidate_email else None,
        payload.candidate_phone,
        payload.lead_id,
        payload.notes,
    )
    return _serialize_booking_out(booking)


@router.post("/bookings/assign", response_model=BookingOut)
@router.post("/bookings/assign/", response_model=BookingOut)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("assign_booking", "counselling_booking")
def assign_booking(
    request: Request,
    payload: BookingAssignRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    booking = counselling_service.assign_booking(db, payload.booking_id, payload.admin_id)
    _, admin = counselling_service.get_booking_with_admin(db, booking.id)
    background_tasks.add_task(run_assignment_notifications, booking.id)
    return _serialize_booking_out(booking, admin)


@router.post("/bookings/mine/reassign", response_model=BookingOut)
@router.post("/bookings/mine/reassign/", response_model=BookingOut)
@log_action("reassign_my_booking", "counselling_booking")
def reassign_my_booking(
    request: Request,
    payload: MyBookingReassignRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    booking = counselling_service.reassign_my_booking(
        db,
        current_user.id,
        payload.booking_id,
        payload.target_admin_id,
    )
    _, admin = counselling_service.get_booking_with_admin(db, booking.id)
    background_tasks.add_task(run_assignment_notifications, booking.id)
    return _serialize_booking_out(booking, admin)


@router.post("/bookings/cancel/{booking_id}", response_model=BookingOut)
@router.post("/bookings/cancel/{booking_id}/", response_model=BookingOut)
@log_action("cancel_booking", "counselling_booking", resource_id_key="booking_id")
def cancel_booking(
    request: Request,
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    booking = counselling_service.cancel_booking(db, booking_id)
    return _serialize_booking_out(booking)


@router.post("/bookings/switch", response_model=BookingOut)
@router.post("/bookings/switch/", response_model=BookingOut)
@log_action("switch_booking_admin", "counselling_booking")
def switch_booking_admin(
    request: Request,
    payload: BookingSwitchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    booking = counselling_service.switch_booking_admin(
        db, payload.booking_id, payload.target_admin_id
    )
    _, admin = counselling_service.get_booking_with_admin(db, booking.id)
    background_tasks.add_task(run_assignment_notifications, booking.id)
    return _serialize_booking_out(booking, admin)


@router.post("/sessions/{booking_id}/complete", response_model=SessionCompleteResponse)
@router.post("/sessions/{booking_id}/complete/", response_model=SessionCompleteResponse)
@log_action("complete_session", "counselling_booking", resource_id_key="booking_id")
def complete_counselling_session(
    request: Request,
    booking_id: int,
    payload: SessionCompleteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    result = complete_session(
        db,
        booking_id=booking_id,
        counsellor=current_user,
        outcome_key=payload.outcome_key,
        next_stage=payload.next_stage,
        notes=payload.notes,
        action_items=payload.action_items,
    )
    from app.services.websocket_service import broadcast_nexus_event

    background_tasks.add_task(
        broadcast_nexus_event,
        "pipeline.updated",
        {"lead_id": result.get("candidate_id")},
    )
    background_tasks.add_task(broadcast_nexus_event, "tasks.updated", {})
    return SessionCompleteResponse(**result)
