"""Register all SQLAlchemy models for standalone CLI scripts."""

from __future__ import annotations


def register_all_models() -> None:
    """Import every mapped model so relationships and FK targets resolve."""
    from app.models.admission_history import AdmissionHistory  # noqa: F401
    from app.models.admin_role import AdminRole  # noqa: F401
    from app.models.agent_config import AgentConfig  # noqa: F401
    from app.models.audit_log import AuditLog  # noqa: F401
    from app.models.business import Business  # noqa: F401
    from app.models.calendar_intake_alert import CalendarIntakeAlertLog  # noqa: F401
    from app.models.candidate_education import CandidateEducation  # noqa: F401
    from app.models.candidate_task import CandidateTask  # noqa: F401
    from app.models.candidate_test_score import CandidateTestScore  # noqa: F401
    from app.models.client import Client  # noqa: F401
    from app.models.consultation_slot import ConsultationSlot  # noqa: F401
    from app.models.conversation import Conversation  # noqa: F401
    from app.models.conversation_audit_log import ConversationAuditLog  # noqa: F401
    from app.models.conversation_participant import ConversationParticipant  # noqa: F401
    from app.models.counselling_booking import CounsellingBooking  # noqa: F401
    from app.models.counselling_note import CounsellingNote  # noqa: F401
    from app.models.country import Country  # noqa: F401
    from app.models.course_education_major_mapping import CourseEducationMajorMapping  # noqa: F401
    from app.models.digital_presence_link import DigitalPresenceLink  # noqa: F401
    from app.models.dynamic_setting import DynamicSetting  # noqa: F401
    from app.models.education_course import EducationCourse  # noqa: F401
    from app.models.education_degree import EducationDegree  # noqa: F401
    from app.models.education_major import EducationMajor  # noqa: F401
    from app.models.education_major_level import EducationMajorLevel  # noqa: F401
    from app.models.gpa_cgpa_score import GpaCgpaScore  # noqa: F401
    from app.models.internal_message import InternalMessage  # noqa: F401
    from app.models.lead import Lead  # noqa: F401
    from app.models.lead_quarantine import LeadQuarantine  # noqa: F401
    from app.models.level import Level  # noqa: F401
    from app.models.message import Message  # noqa: F401
    from app.models.message_history import MessageHistory  # noqa: F401
    from app.models.navigation_page import NavigationPage  # noqa: F401
    from app.models.non_academic_activity import NonAcademicActivity  # noqa: F401
    from app.models.note import Note  # noqa: F401
    from app.models.notification_log import NotificationLog  # noqa: F401
    from app.models.processed_message import ProcessedMessage  # noqa: F401
    from app.models.program import Program  # noqa: F401
    from app.models.program_education_major_mapping import ProgramEducationMajorMapping  # noqa: F401
    from app.models.public_holiday import PublicHoliday  # noqa: F401
    from app.models.raw_incoming_lead import RawIncomingLead  # noqa: F401
    from app.models.research_project import ResearchProject  # noqa: F401
    from app.models.role_page_permission import RolePagePermission  # noqa: F401
    from app.models.security_audit_run import SecurityAuditRun  # noqa: F401
    from app.models.status_change_reason import StatusChangeReason  # noqa: F401
    from app.models.status_definition import StatusDefinition  # noqa: F401
    from app.models.status_history import StatusHistory  # noqa: F401
    from app.models.status_transition import StatusTransition  # noqa: F401
    from app.models.students_master import StudentsMaster  # noqa: F401
    from app.models.sync_log import SyncLog  # noqa: F401
    from app.models.exception_log import ExceptionLog  # noqa: F401
    from app.models.system_log import SystemLog  # noqa: F401
    from app.models.target_course import TargetCourse  # noqa: F401
    from app.models.target_program import TargetProgram  # noqa: F401
    from app.models.team_chat_message import TeamChatMessage  # noqa: F401
    from app.models.university_matching import (  # noqa: F401
        MatchingShortlistItem,
        MatchingShortlistRun,
        MatchingWeightProfile,
    )
    from app.models.user import User  # noqa: F401
    from app.models.work_experience import WorkExperience, WorkProject  # noqa: F401
    from app.models.academia_geography import GeographyCity, GeographyState  # noqa: F401
    from app.models.academia_institution import Campus, CampusType, College, Institution  # noqa: F401
    from app.models.academia_wizard import (  # noqa: F401
        AcademiaAuditLog,
        InstitutionCourseOffering,
        InstitutionIntake,
        InstitutionPicture,
        InstitutionWizardDraft,
    )
    from app.models.academic_calendar import (  # noqa: F401
        GlobalAcademicTemplate,
        ProgramIntakeAssignment,
    )
