from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


BookingStatus = Literal["PENDING", "SCHEDULED", "CANCELLED", "COMPLETED"]
AdminCellStatus = Literal["available", "booked", "past", "complete"]


class BookingCreateRequest(BaseModel):
    scheduled_time: datetime
    candidate_name: str = Field(min_length=1, max_length=255)
    candidate_email: EmailStr | None = None
    candidate_phone: str | None = None
    lead_id: int | None = None
    notes: str | None = None


class BookingAssignRequest(BaseModel):
    booking_id: int
    admin_id: int


class BookingSwitchRequest(BaseModel):
    booking_id: int
    target_admin_id: int


class PendingBookingOut(BaseModel):
    id: int
    scheduled_time: datetime
    candidate_name: str
    candidate_email: str | None = None
    candidate_phone: str | None = None
    notes: str | None = None
    status: BookingStatus


class UpcomingDateGroupOut(BaseModel):
    date: date
    label: str
    bookings: list[PendingBookingOut]


class PendingBookingsResponse(BaseModel):
    today: list[PendingBookingOut]
    upcoming: list[UpcomingDateGroupOut]


class AvailableAdminOut(BaseModel):
    id: int
    name: str
    email: str


class AvailableAdminsResponse(BaseModel):
    time: datetime
    admins: list[AvailableAdminOut]


class BookingOut(BaseModel):
    id: int
    scheduled_time: datetime
    admin_id: int | None
    admin_name: str | None = None
    candidate_name: str
    candidate_email: str | None = None
    candidate_phone: str | None = None
    status: BookingStatus
    notes: str | None = None


class MyBookingOut(BookingOut):
    lead_id: int | None = None
    candidate_stage: str | None = None
    candidate_stage_label: str | None = None
    time_label: str
    date_label: str
    section: Literal["past", "today", "upcoming"]


class MyBookingsResponse(BaseModel):
    past: list[MyBookingOut]
    today: list[MyBookingOut]
    upcoming: list[MyBookingOut]
    calendar_today: date
    total_count: int


class MyBookingReassignRequest(BaseModel):
    booking_id: int
    target_admin_id: int


class GridAdminOut(BaseModel):
    id: int
    name: str


class GridPendingOut(BaseModel):
    id: int
    candidate_name: str
    scheduled_time: datetime
    notes: str | None = None


class GridPendingQueueSlotOut(BaseModel):
    queue_position: int
    booking: GridPendingOut | None = None


class GridAdminCellOut(BaseModel):
    admin_id: int
    status: AdminCellStatus
    label: str
    candidate_name: str | None = None
    booking_id: int | None = None


class GridRowOut(BaseModel):
    start_time: datetime
    time_label: str
    pending_queue: list[GridPendingQueueSlotOut]
    hidden_pending_count: int
    admin_cells: list[GridAdminCellOut]


class NavigationDayOut(BaseModel):
    date: date
    label: str


class ScheduleNavigationOut(BaseModel):
    past: NavigationDayOut
    selected: NavigationDayOut
    upcoming: NavigationDayOut


class DayScheduleGridOut(BaseModel):
    date: date
    label: str
    section: Literal["past", "selected", "upcoming"]
    admins: list[GridAdminOut]
    rows: list[GridRowOut]


CommunicationParticipant = Literal["candidate", "ai_agent", "handoff_admin", "system"]


class BookingCommunicationMessageOut(BaseModel):
    id: int | str
    participant: CommunicationParticipant
    participant_label: str
    text: str
    created_at: datetime
    media_url: str | None = None
    file_name: str | None = None


class BookingCommunicationsResponse(BaseModel):
    booking_id: int
    lead_id: int | None = None
    candidate_name: str
    candidate_email: str | None = None
    candidate_phone: str | None = None
    candidate_stage: str | None = None
    candidate_stage_label: str | None = None
    admin_name: str | None = None
    message_count: int
    messages: list[BookingCommunicationMessageOut]


class ScheduleGridResponse(BaseModel):
    days: list[DayScheduleGridOut]
    legend: dict[str, str]
    max_bookings_per_slot: int
    visible_pending_columns: int
    focus_date: date
    calendar_today: date
    navigation: ScheduleNavigationOut
