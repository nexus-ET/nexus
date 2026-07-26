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
    BookingActivityLogResponse,
    BookingAssignRequest,
    BookingCommunicationsResponse,
    BookingCreateRequest,
    BookingInteractionLogResponse,
    BookingOut,
    BookingSwitchRequest,
    BookingCandidateProfileResponse,
    BookingViewDetailResponse,
    MyBookingReassignRequest,
    MyBookingsDayResponse,
    MyBookingsOverviewResponse,
    MyBookingsResponse,
    PendingBookingsResponse,
    ScheduleGridResponse,
)
from app.schemas.students_master import StudentMasterSaveRequest, StudentMasterSaveResponse
from app.schemas.student_aspirations import (
    StudentAspirationsResponse,
    StudentAspirationsSaveRequest,
)
from app.schemas.candidate_test_scores import (
    CandidateTestScoreSaveRequest,
    CandidateTestScoresResponse,
)
from app.schemas.work_experience import (
    WorkExperienceSaveRequest,
    WorkExperiencesResponse,
)
from app.schemas.research_project import (
    ResearchProjectInput,
    ResearchProjectsResponse,
)
from app.schemas.non_academic_activity import (
    NonAcademicActivitiesResponse,
    NonAcademicActivityInput,
)
from app.schemas.candidate_education import (
    CandidateEducationInput,
    CandidateEducationsResponse,
)
from app.schemas.digital_presence_link import (
    DigitalPresenceLinkInput,
    DigitalPresenceLinksResponse,
)
from app.schemas.university_matching import (
    MatchingWeightProfileOut,
    UniversityShortlistGenerateRequest,
    UniversityShortlistResponse,
)
from app.schemas.status_definition import (
    BookingStatusUpdateRequest,
    BookingStatusUpdateResponse,
    StatusDefinitionsResponse,
)
from app.schemas.counselling_note import (
    CounsellingSessionNoteOut,
    CounsellingSessionNoteSaveRequest,
    CounsellingSummarizeRequest,
    CounsellingSummarizeResponse,
)
from app.schemas.pipeline import (
    PipelineAnalyticsResponse,
    PipelineConfigResponse,
    SessionCompleteRequest,
    SessionCompleteResponse,
)
from app.services import counselling_service
from app.services import counselling_note_service
from app.services import university_matching_service
from app.services.audit_service import log_action
from app.services.notification_service import run_assignment_notifications
from app.services.pipeline_service import complete_session, get_pipeline_analytics, get_pipeline_config
from app.utils.timezone import office_today

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
    start_date: date | None = Query(default=None, description="Inclusive start of date period"),
    end_date: date | None = Query(default=None, description="Inclusive end of date period"),
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return counselling_service.get_schedule_grid(db, date, start_date, end_date)


@router.get("/bookings/mine", response_model=MyBookingsResponse)
@router.get("/bookings/mine/", response_model=MyBookingsResponse)
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_my_bookings(db, current_user)


@router.get("/bookings/mine/overview", response_model=MyBookingsOverviewResponse)
@router.get("/bookings/mine/overview/", response_model=MyBookingsOverviewResponse)
def get_my_bookings_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_my_bookings_overview(db, current_user)


@router.get("/bookings/mine/day", response_model=MyBookingsDayResponse)
@router.get("/bookings/mine/day/", response_model=MyBookingsDayResponse)
def list_my_bookings_for_date(
    date: date | None = Query(default=None, description="Booking date (defaults to today)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    selected = date or office_today(db)
    return counselling_service.get_my_bookings_for_date(db, current_user, selected)


@router.get("/status-definitions", response_model=StatusDefinitionsResponse)
@router.get("/status-definitions/", response_model=StatusDefinitionsResponse)
def read_status_definitions(
    db: Session = Depends(get_db),
    _: User = Depends(deps.get_current_active_user),
):
    from app.services.status_definition_service import list_status_definitions

    return StatusDefinitionsResponse(items=list_status_definitions(db))


@router.get("/bookings/mine/{booking_id}/activity", response_model=BookingActivityLogResponse)
@router.get("/bookings/mine/{booking_id}/activity/", response_model=BookingActivityLogResponse)
def get_my_booking_activity_log(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_activity_log(db, current_user.id, booking_id)


@router.get("/bookings/mine/{booking_id}/interactions", response_model=BookingInteractionLogResponse)
@router.get("/bookings/mine/{booking_id}/interactions/", response_model=BookingInteractionLogResponse)
def get_my_booking_interaction_log(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_interaction_log(db, current_user.id, booking_id)


@router.get("/bookings/{booking_id}/interactions", response_model=BookingInteractionLogResponse)
@router.get("/bookings/{booking_id}/interactions/", response_model=BookingInteractionLogResponse)
def get_schedule_booking_interaction_log(
    booking_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    """Manage Appointments interaction log — available before counsellor assignment."""
    return counselling_service.get_schedule_booking_interaction_log(db, booking_id)


@router.get("/bookings/mine/{booking_id}/view", response_model=BookingViewDetailResponse)
@router.get("/bookings/mine/{booking_id}/view/", response_model=BookingViewDetailResponse)
def get_my_booking_view_detail(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_view_detail(db, current_user.id, booking_id)


@router.get("/bookings/mine/{booking_id}/profile", response_model=BookingCandidateProfileResponse)
@router.get("/bookings/mine/{booking_id}/profile/", response_model=BookingCandidateProfileResponse)
def get_my_booking_candidate_profile(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_candidate_profile(db, current_user.id, booking_id)


@router.post("/bookings/mine/{booking_id}/students-master", response_model=StudentMasterSaveResponse)
@router.post("/bookings/mine/{booking_id}/students-master/", response_model=StudentMasterSaveResponse)
def save_my_booking_students_master(
    booking_id: int,
    payload: StudentMasterSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.save_booking_students_master(db, current_user.id, booking_id, payload)


@router.get("/bookings/mine/{booking_id}/aspirations", response_model=StudentAspirationsResponse)
@router.get("/bookings/mine/{booking_id}/aspirations/", response_model=StudentAspirationsResponse)
def get_my_booking_aspirations(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_candidate_aspirations(db, current_user.id, booking_id)


@router.put("/bookings/mine/{booking_id}/aspirations", response_model=StudentAspirationsResponse)
@router.put("/bookings/mine/{booking_id}/aspirations/", response_model=StudentAspirationsResponse)
def save_my_booking_aspirations(
    booking_id: int,
    payload: StudentAspirationsSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.save_booking_candidate_aspirations(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.get("/bookings/mine/{booking_id}/test-scores", response_model=CandidateTestScoresResponse)
@router.get("/bookings/mine/{booking_id}/test-scores/", response_model=CandidateTestScoresResponse)
def get_my_booking_test_scores(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_candidate_test_scores(db, current_user.id, booking_id)


@router.post("/bookings/mine/{booking_id}/test-scores", response_model=CandidateTestScoresResponse)
@router.post("/bookings/mine/{booking_id}/test-scores/", response_model=CandidateTestScoresResponse)
def save_my_booking_test_scores(
    booking_id: int,
    payload: CandidateTestScoreSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.save_booking_candidate_test_scores(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.get("/bookings/mine/{booking_id}/work-experiences", response_model=WorkExperiencesResponse)
@router.get("/bookings/mine/{booking_id}/work-experiences/", response_model=WorkExperiencesResponse)
def get_my_booking_work_experiences(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_work_experiences(db, current_user.id, booking_id)


@router.put("/bookings/mine/{booking_id}/work-experiences", response_model=WorkExperiencesResponse)
@router.put("/bookings/mine/{booking_id}/work-experiences/", response_model=WorkExperiencesResponse)
def save_my_booking_work_experiences(
    booking_id: int,
    payload: WorkExperienceSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.save_booking_work_experiences(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.get("/bookings/mine/{booking_id}/research-projects", response_model=ResearchProjectsResponse)
@router.get("/bookings/mine/{booking_id}/research-projects/", response_model=ResearchProjectsResponse)
def get_my_booking_research_projects(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_research_projects(db, current_user.id, booking_id)


@router.post("/bookings/mine/{booking_id}/research-projects", response_model=ResearchProjectsResponse)
@router.post("/bookings/mine/{booking_id}/research-projects/", response_model=ResearchProjectsResponse)
def create_my_booking_research_project(
    booking_id: int,
    payload: ResearchProjectInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.create_booking_research_project(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.put(
    "/bookings/mine/{booking_id}/research-projects/{project_id}",
    response_model=ResearchProjectsResponse,
)
@router.put(
    "/bookings/mine/{booking_id}/research-projects/{project_id}/",
    response_model=ResearchProjectsResponse,
)
def update_my_booking_research_project(
    booking_id: int,
    project_id: int,
    payload: ResearchProjectInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.update_booking_research_project(
        db,
        current_user.id,
        booking_id,
        project_id,
        payload,
    )


@router.delete(
    "/bookings/mine/{booking_id}/research-projects/{project_id}",
    response_model=ResearchProjectsResponse,
)
@router.delete(
    "/bookings/mine/{booking_id}/research-projects/{project_id}/",
    response_model=ResearchProjectsResponse,
)
def delete_my_booking_research_project(
    booking_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.delete_booking_research_project(
        db,
        current_user.id,
        booking_id,
        project_id,
    )


@router.get("/bookings/mine/{booking_id}/educations", response_model=CandidateEducationsResponse)
@router.get("/bookings/mine/{booking_id}/educations/", response_model=CandidateEducationsResponse)
def get_my_booking_candidate_educations(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_candidate_educations(db, current_user.id, booking_id)


@router.get(
    "/bookings/matching/weight-profiles",
    response_model=list[MatchingWeightProfileOut],
)
@router.get(
    "/bookings/matching/weight-profiles/",
    response_model=list[MatchingWeightProfileOut],
)
def list_matching_weight_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return university_matching_service.list_weight_profiles(db)


@router.get(
    "/bookings/mine/{booking_id}/university-shortlist",
    response_model=UniversityShortlistResponse,
)
@router.get(
    "/bookings/mine/{booking_id}/university-shortlist/",
    response_model=UniversityShortlistResponse,
)
def get_my_booking_university_shortlist(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return university_matching_service.get_university_shortlist_for_booking(
        db, current_user, booking_id
    )


@router.get(
    "/bookings/mine/{booking_id}/university-shortlist/{run_id}",
    response_model=UniversityShortlistResponse,
)
@router.get(
    "/bookings/mine/{booking_id}/university-shortlist/{run_id}/",
    response_model=UniversityShortlistResponse,
)
def get_my_booking_university_shortlist_run(
    booking_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return university_matching_service.get_university_shortlist_for_booking(
        db, current_user, booking_id, run_id=run_id
    )


@router.post(
    "/bookings/mine/{booking_id}/university-shortlist",
    response_model=UniversityShortlistResponse,
)
@router.post(
    "/bookings/mine/{booking_id}/university-shortlist/",
    response_model=UniversityShortlistResponse,
)
def generate_my_booking_university_shortlist(
    booking_id: int,
    payload: UniversityShortlistGenerateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    body = payload or UniversityShortlistGenerateRequest()
    return university_matching_service.generate_university_shortlist_for_booking(
        db,
        current_user.id,
        booking_id,
        weight_profile_code=body.weight_profile_code,
        limit=body.limit,
    )


@router.post("/bookings/mine/{booking_id}/educations", response_model=CandidateEducationsResponse)
@router.post("/bookings/mine/{booking_id}/educations/", response_model=CandidateEducationsResponse)
def create_my_booking_candidate_education(
    booking_id: int,
    payload: CandidateEducationInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.create_booking_candidate_education(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.put(
    "/bookings/mine/{booking_id}/educations/{education_id}",
    response_model=CandidateEducationsResponse,
)
@router.put(
    "/bookings/mine/{booking_id}/educations/{education_id}/",
    response_model=CandidateEducationsResponse,
)
def update_my_booking_candidate_education(
    booking_id: int,
    education_id: int,
    payload: CandidateEducationInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.update_booking_candidate_education(
        db,
        current_user.id,
        booking_id,
        education_id,
        payload,
    )


@router.delete(
    "/bookings/mine/{booking_id}/educations/{education_id}",
    response_model=CandidateEducationsResponse,
)
@router.delete(
    "/bookings/mine/{booking_id}/educations/{education_id}/",
    response_model=CandidateEducationsResponse,
)
def delete_my_booking_candidate_education(
    booking_id: int,
    education_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.delete_booking_candidate_education(
        db,
        current_user.id,
        booking_id,
        education_id,
    )


@router.get(
    "/bookings/mine/{booking_id}/non-academic-activities",
    response_model=NonAcademicActivitiesResponse,
)
@router.get(
    "/bookings/mine/{booking_id}/non-academic-activities/",
    response_model=NonAcademicActivitiesResponse,
)
def get_my_booking_non_academic_activities(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_non_academic_activities(db, current_user.id, booking_id)


@router.post(
    "/bookings/mine/{booking_id}/non-academic-activities",
    response_model=NonAcademicActivitiesResponse,
)
@router.post(
    "/bookings/mine/{booking_id}/non-academic-activities/",
    response_model=NonAcademicActivitiesResponse,
)
def create_my_booking_non_academic_activity(
    booking_id: int,
    payload: NonAcademicActivityInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.create_booking_non_academic_activity(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.put(
    "/bookings/mine/{booking_id}/non-academic-activities/{activity_id}",
    response_model=NonAcademicActivitiesResponse,
)
@router.put(
    "/bookings/mine/{booking_id}/non-academic-activities/{activity_id}/",
    response_model=NonAcademicActivitiesResponse,
)
def update_my_booking_non_academic_activity(
    booking_id: int,
    activity_id: int,
    payload: NonAcademicActivityInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.update_booking_non_academic_activity(
        db,
        current_user.id,
        booking_id,
        activity_id,
        payload,
    )


@router.delete(
    "/bookings/mine/{booking_id}/non-academic-activities/{activity_id}",
    response_model=NonAcademicActivitiesResponse,
)
@router.delete(
    "/bookings/mine/{booking_id}/non-academic-activities/{activity_id}/",
    response_model=NonAcademicActivitiesResponse,
)
def delete_my_booking_non_academic_activity(
    booking_id: int,
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.delete_booking_non_academic_activity(
        db,
        current_user.id,
        booking_id,
        activity_id,
    )


@router.get(
    "/bookings/mine/{booking_id}/digital-presence-links",
    response_model=DigitalPresenceLinksResponse,
)
@router.get(
    "/bookings/mine/{booking_id}/digital-presence-links/",
    response_model=DigitalPresenceLinksResponse,
)
def get_my_booking_digital_presence_links(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_booking_digital_presence_links(db, current_user.id, booking_id)


@router.post(
    "/bookings/mine/{booking_id}/digital-presence-links",
    response_model=DigitalPresenceLinksResponse,
)
@router.post(
    "/bookings/mine/{booking_id}/digital-presence-links/",
    response_model=DigitalPresenceLinksResponse,
)
def create_my_booking_digital_presence_link(
    booking_id: int,
    payload: DigitalPresenceLinkInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.create_booking_digital_presence_link(
        db,
        current_user.id,
        booking_id,
        payload,
    )


@router.put(
    "/bookings/mine/{booking_id}/digital-presence-links/{link_id}",
    response_model=DigitalPresenceLinksResponse,
)
@router.put(
    "/bookings/mine/{booking_id}/digital-presence-links/{link_id}/",
    response_model=DigitalPresenceLinksResponse,
)
def update_my_booking_digital_presence_link(
    booking_id: int,
    link_id: int,
    payload: DigitalPresenceLinkInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.update_booking_digital_presence_link(
        db,
        current_user.id,
        booking_id,
        link_id,
        payload,
    )


@router.delete(
    "/bookings/mine/{booking_id}/digital-presence-links/{link_id}",
    response_model=DigitalPresenceLinksResponse,
)
@router.delete(
    "/bookings/mine/{booking_id}/digital-presence-links/{link_id}/",
    response_model=DigitalPresenceLinksResponse,
)
def delete_my_booking_digital_presence_link(
    booking_id: int,
    link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.delete_booking_digital_presence_link(
        db,
        current_user.id,
        booking_id,
        link_id,
    )


@router.get("/bookings/mine/{booking_id}/communications", response_model=BookingCommunicationsResponse)
@router.get("/bookings/mine/{booking_id}/communications/", response_model=BookingCommunicationsResponse)
def get_my_booking_communications(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_service.get_my_booking_communications(db, current_user.id, booking_id)


@router.post("/counselling/summarize", response_model=CounsellingSummarizeResponse)
@router.post("/counselling/summarize/", response_model=CounsellingSummarizeResponse)
async def summarize_counselling_notes(
    payload: CounsellingSummarizeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(deps.get_current_active_user),
):
    return await counselling_note_service.summarize_counselling_text(db, payload.raw_text)


@router.get("/bookings/mine/{booking_id}/session-notes", response_model=CounsellingSessionNoteOut)
@router.get("/bookings/mine/{booking_id}/session-notes/", response_model=CounsellingSessionNoteOut)
def get_my_booking_session_notes(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_note_service.get_session_note(db, current_user.id, booking_id)


@router.post("/bookings/mine/{booking_id}/session-notes", response_model=CounsellingSessionNoteOut)
@router.post("/bookings/mine/{booking_id}/session-notes/", response_model=CounsellingSessionNoteOut)
@log_action("save_session_notes", "counselling_booking", resource_id_key="booking_id")
def save_my_booking_session_notes(
    booking_id: int,
    payload: CounsellingSessionNoteSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return counselling_note_service.save_session_note(db, current_user.id, booking_id, payload)


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


@router.post("/bookings/mine/{booking_id}/status", response_model=BookingStatusUpdateResponse)
@router.post("/bookings/mine/{booking_id}/status/", response_model=BookingStatusUpdateResponse)
@log_action("update_booking_status", "counselling_booking", resource_id_key="booking_id")
async def update_my_booking_status(
    request: Request,
    booking_id: int,
    payload: BookingStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    from app.models.lead import Lead
    from app.services.twilio_ai_conversation import initiate_ai_outreach

    result = counselling_service.update_my_booking_status(
        db,
        current_user.id,
        booking_id,
        payload.status_definition_id,
        payload.notes,
    )

    if result.get("trigger_outreach") and result.get("lead_id"):
        lead_id = int(result["lead_id"])

        async def _run_outreach(target_lead_id: int) -> None:
            from app.db.database import SessionLocal

            outreach_db = SessionLocal()
            try:
                outreach_lead = outreach_db.query(Lead).filter(Lead.id == target_lead_id).first()
                if outreach_lead:
                    await initiate_ai_outreach(outreach_db, outreach_lead)
            finally:
                outreach_db.close()

        background_tasks.add_task(_run_outreach, lead_id)

    from app.services.websocket_service import broadcast_nexus_event

    background_tasks.add_task(
        broadcast_nexus_event,
        "pipeline.updated",
        {"lead_id": result.get("lead_id")},
    )
    return BookingStatusUpdateResponse(**result)


@router.post("/bookings/mine/{booking_id}/complete", response_model=SessionCompleteResponse)
@router.post("/bookings/mine/{booking_id}/complete/", response_model=SessionCompleteResponse)
@log_action("complete_session", "counselling_booking", resource_id_key="booking_id")
def complete_my_booking_session(
    request: Request,
    booking_id: int,
    payload: SessionCompleteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    counselling_service._get_owned_booking(db, current_user.id, booking_id)
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
