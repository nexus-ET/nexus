from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.pipeline import PipelineOutcomeOut, PipelineStageOut
from app.schemas.status_definition import LeadStatusHistoryItemOut, StatusDefinitionOut


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
    lead_id: int | None = None


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
    current_location: str | None = None
    preferred_country: str | None = None
    course_interest: str | None = None
    status_definition_id: int | None = None
    status_stage_name: str | None = None
    status_category: str | None = None
    # Legacy aliases kept for transitional clients
    admission_stage: str | None = None
    admission_stage_label: str | None = None
    admission_stage_category: str | None = None
    session_status_label: str | None = None
    outcome_key: str | None = None
    outcome_label: str | None = None
    time_label: str
    date_label: str
    section: Literal["past", "today", "upcoming"]


class MyBookingsResponse(BaseModel):
    past: list[MyBookingOut]
    today: list[MyBookingOut]
    upcoming: list[MyBookingOut]
    calendar_today: date
    total_count: int
    view_all_bookings: bool = False


class MyBookingsOverviewResponse(BaseModel):
    past_count: int
    today_count: int
    upcoming_count: int
    calendar_today: date
    view_all_bookings: bool = False


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
    lead_id: int | None = None


class GridPendingQueueSlotOut(BaseModel):
    queue_position: int
    booking: GridPendingOut | None = None


class GridAdminCellOut(BaseModel):
    admin_id: int
    admin_name: str | None = None
    status: AdminCellStatus
    label: str
    candidate_name: str | None = None
    booking_id: int | None = None
    lead_id: int | None = None


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


class BookingTimelineItemOut(BaseModel):
    id: str
    kind: Literal["whatsapp", "session_note", "audio", "system"]
    participant: str
    participant_label: str
    text: str
    created_at: datetime
    media_url: str | None = None
    file_name: str | None = None


class DataExchangeItemOut(BaseModel):
    id: str
    title: str
    url: str
    shared_by: Literal["student", "admin"]
    created_at: datetime
    file_name: str | None = None


class MyBookingsDayResponse(BaseModel):
    date: date
    calendar_today: date
    bookings: list[MyBookingOut]
    view_all_bookings: bool = False


class BookingActivityLogResponse(BaseModel):
    booking: MyBookingOut
    status_history: list[LeadStatusHistoryItemOut]
    shared_by_student: list[DataExchangeItemOut]
    shared_by_admin: list[DataExchangeItemOut]
    status_definitions: list[StatusDefinitionOut]
    current_status_definition_id: int | None = None
    suggested_next_status_definition_id: int | None = None
    previous_stage_id: int | None = None
    appointment_date: date | None = None
    calendar_today: date | None = None
    forward_status_changes_blocked: bool = False
    backward_status_ids: list[int] = Field(default_factory=list)
    lead_jump_path: str | None = None
    can_update_status: bool = False
    candidate_profile: CandidateProfileOut | None = None


class BookingInteractionLogResponse(BaseModel):
    booking: MyBookingOut
    timeline: list[BookingTimelineItemOut]


class CandidateProfileLocationOut(BaseModel):
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    city: str | None = None
    state: str | None = None
    country_iso2: str | None = None
    country: str | None = None
    zipcode: str | None = None


class CandidateProfileEducationOut(BaseModel):
    degree_code: str | None = None
    degree: str | None = None
    degree_other: str | None = None
    major: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    gpa_cgpa_code: str | None = None
    gpa_cgpa: str | None = None
    gpa_cgpa_other: str | None = None


class CandidateProfileStudyInterestOut(BaseModel):
    target_destination_iso2: str | None = None
    target_destination: str | None = None
    target_program_code: str | None = None
    target_program: str | None = None
    target_course_code: str | None = None
    target_course: str | None = None


class CandidateProfileAptitudeOut(BaseModel):
    english_test_scores: str | None = None
    gre_score: str | None = None
    gmat_score: str | None = None


class CandidateProfileOut(BaseModel):
    lead_id: int | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    marital_status: str | None = None
    email: str | None = None
    phone_country_iso2: str | None = None
    phone_local: str | None = None
    phone_number: str | None = None
    phone_country_iso2_secondary: str | None = None
    phone_local_secondary: str | None = None
    phone_number_secondary: str | None = None
    location: CandidateProfileLocationOut
    education: CandidateProfileEducationOut
    study_interest: CandidateProfileStudyInterestOut
    aptitude_scores: CandidateProfileAptitudeOut = Field(default_factory=CandidateProfileAptitudeOut)
    students_master_id: int | None = None
    saved_at: str | None = None


class BookingCandidateProfileResponse(BaseModel):
    booking_id: int
    candidate_name: str
    profile: CandidateProfileOut


class BookingViewDetailResponse(BaseModel):
    """Deprecated alias — use BookingActivityLogResponse."""
    booking: MyBookingOut
    timeline: list[BookingTimelineItemOut] = Field(default_factory=list)
    shared_by_student: list[DataExchangeItemOut] = Field(default_factory=list)
    shared_by_admin: list[DataExchangeItemOut] = Field(default_factory=list)
    lead_jump_path: str | None = None
    can_complete_session: bool = False
    session_outcomes: list[PipelineOutcomeOut] = Field(default_factory=list)
    pipeline_stages: list[PipelineStageOut] = Field(default_factory=list)
    status_history: list[LeadStatusHistoryItemOut] = Field(default_factory=list)
    status_definitions: list[StatusDefinitionOut] = Field(default_factory=list)
    current_status_definition_id: int | None = None
    can_update_status: bool = False


class ScheduleGridResponse(BaseModel):
    days: list[DayScheduleGridOut]
    legend: dict[str, str]
    max_bookings_per_slot: int
    visible_pending_columns: int
    focus_date: date
    calendar_today: date
    navigation: ScheduleNavigationOut

