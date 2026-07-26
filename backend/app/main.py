import os
import logging
import asyncio
import mimetypes
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db.database import Base, engine, sync_schema_columns

# 🛠️ CRITICAL DATABASE SCHEMATIC REGISTRATION
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import User
from app.models.client import Client
from app.models.agent_config import AgentConfig
from app.models.status_change_reason import StatusChangeReason
from app.models.admin_role import AdminRole
from app.models.navigation_page import NavigationPage
from app.models.role_page_permission import RolePagePermission
from app.models.message_history import MessageHistory
from app.models.calendar_intake_alert import CalendarIntakeAlertLog
from app.models.counselling_booking import CounsellingBooking
from app.models.counselling_note import CounsellingNote
from app.models.notification_log import NotificationLog
from app.models.processed_message import ProcessedMessage
from app.models.dynamic_setting import DynamicSetting
from app.models.business import Business
from app.models.public_holiday import PublicHoliday
from app.models.sync_log import SyncLog
from app.models.exception_log import ExceptionLog
from app.models.raw_incoming_lead import RawIncomingLead
from app.models.lead_quarantine import LeadQuarantine
from app.models.audit_log import AuditLog
from app.models.country import Country
from app.models.education_course import EducationCourse
from app.models.course_education_major_mapping import CourseEducationMajorMapping
from app.models.education_degree import EducationDegree
from app.models.education_major import EducationMajor
from app.models.education_major_level import EducationMajorLevel
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.gpa_cgpa_score import GpaCgpaScore
from app.models.target_program import TargetProgram
from app.models.target_course import TargetCourse
from app.models.security_audit_run import SecurityAuditRun
from app.models.admission_history import AdmissionHistory
from app.models.status_history import StatusHistory
from app.models.system_log import SystemLog
from app.models.status_definition import StatusDefinition
from app.models.candidate_task import CandidateTask
from app.models.team_chat_message import TeamChatMessage
from app.models.conversation import Conversation
from app.models.conversation_audit_log import ConversationAuditLog
from app.models.conversation_participant import ConversationParticipant
from app.models.internal_message import InternalMessage
from app.models.university_matching import (
    MatchingShortlistItem,
    MatchingShortlistRun,
    MatchingWeightProfile,
)
from app.api.v1.endpoints import leads
from app.api.v1 import analytics, notifications, dashboard, users, login, agents, rbac, countries, education_degrees, education_majors, gpa_cgpa_scores, target_programs, conversation_audit, academia, academia_wizard, academic_calendar
from app.routers import (
    counselling,
    whatsapp_flow_webhook,
    whatsapp_webhook,
    webhooks,
    settings as settings_router,
    lead_sync,
    meta_leads,
    security_admin,
    command_center,
    chat,
    nexus_ws,
    reports,
    admin,
    audit_events,
)
from app.db.database import SessionLocal
from app.services.agent_runtime import get_or_create_agent_config
from app.services.admissions_intake_flow import ensure_consultation_slots, dedupe_consultation_slots
from app.services.whatsapp_flow_crypto import ensure_flow_keypair
from app.services.sync_log_service import recover_stale_sync_logs
from app.services.business_profile_service import ensure_default_business
from app.middleware.audit_middleware import audit_middleware
from app.middleware.rbac_middleware import NavigationRBACMiddleware
from app.middleware.security_middleware import SecurityHeadersMiddleware
from app.core.rate_limit import RateLimitExceeded, _rate_limit_exceeded_handler, limiter
from app.services.scheduler_service import shutdown_security_scheduler, start_security_scheduler
from app.services.scheduler import shutdown_lead_sync_scheduler, start_lead_sync_scheduler
from app.services.lead_processor_scheduler import (
    shutdown_raw_lead_processor_scheduler,
    start_raw_lead_processor_scheduler,
)
from slowapi.middleware import SlowAPIMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

bootstrap_logger = logging.getLogger(__name__)


def bootstrap_application(*, include_deferred: bool = True) -> None:
    """Run one-time DB/schema seeding. Called from lifespan, not at import time."""
    try:
        bootstrap_logger.info("Nexus database synchronization: checking table structures...")
        Base.metadata.create_all(bind=engine)
        sync_schema_columns()
        bootstrap_logger.info("Nexus database synchronization: tables initialized successfully.")
        bootstrap_db = SessionLocal()
        try:
            get_or_create_agent_config(bootstrap_db)
            bootstrap_logger.info("Agent runtime configuration initialized.")
            recovered = recover_stale_sync_logs(bootstrap_db)
            if recovered:
                bootstrap_logger.info("Recovered %s stale in-progress sync log(s).", recovered)
            ensure_default_business(bootstrap_db)
            bootstrap_logger.info("Startup catalog/reference seeds are disabled (manage data via Admin UI).")
            bootstrap_logger.info("Dynamic settings initialized.")
            if include_deferred:
                _bootstrap_deferred_services(bootstrap_db)
            bootstrap_logger.info("Application bootstrap complete.")
        finally:
            bootstrap_db.close()
    except Exception:
        bootstrap_logger.exception(
            "Critical error during database sync lifecycle initialization"
        )
        raise


def _bootstrap_deferred_services(bootstrap_db) -> None:
    """Slow startup work (consultation slots can take 30–60s on cold Neon)."""
    dedupe_consultation_slots(bootstrap_db)
    ensure_consultation_slots(bootstrap_db)
    ensure_flow_keypair()
    bootstrap_logger.info("Consultation slots initialized.")
    if os.getenv("WHATSAPP_FLOW_ID"):
        bootstrap_logger.info("WhatsApp Flow booking enabled.")
        bootstrap_logger.info(
            "Flow public key ready for Meta upload "
            "(GET /api/v1/webhooks/whatsapp-flow/public-key)"
        )
    from app.services.whatsapp_webhook_env import audit_whatsapp_webhook_routing

    audit_whatsapp_webhook_routing(check_reachability=False)


def bootstrap_deferred_application() -> None:
    """Run after the HTTP server is accepting connections."""
    bootstrap_db = SessionLocal()
    try:
        _bootstrap_deferred_services(bootstrap_db)
        bootstrap_logger.info("Deferred application bootstrap complete.")
    except Exception:
        bootstrap_logger.exception("Deferred bootstrap failed")
    finally:
        bootstrap_db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fast path only — do not block uvicorn bind on consultation-slot generation.
    try:
        await asyncio.to_thread(bootstrap_application, include_deferred=False)
    except Exception:
        bootstrap_logger.exception("Bootstrap failed — server starting with degraded initialization")

    try:
        start_security_scheduler()
    except Exception:
        bootstrap_logger.exception("Security scheduler failed to start")
    try:
        start_lead_sync_scheduler()
    except Exception:
        bootstrap_logger.exception("Lead sync scheduler failed to start")
    try:
        start_raw_lead_processor_scheduler()
    except Exception:
        bootstrap_logger.exception("Raw lead processor scheduler failed to start")

    deferred = asyncio.create_task(asyncio.to_thread(bootstrap_deferred_application))

    yield

    deferred.cancel()
    try:
        await deferred
    except asyncio.CancelledError:
        pass

    shutdown_raw_lead_processor_scheduler()
    shutdown_lead_sync_scheduler()
    shutdown_security_scheduler()


app = FastAPI(
    title="NEXUS",
    description="AI-Powered Client Growth Workspace Engine",
    version="0.1.0",
    lifespan=lifespan,
)

uploads_directory = Path(__file__).resolve().parents[1] / "uploads"
try:
    uploads_directory.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=uploads_directory), name="uploads")
except OSError:
    bootstrap_logger.exception(
        "Could not create/mount uploads directory at %s — continuing without /uploads",
        uploads_directory,
    )

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.middleware.exception_capture import register_exception_handlers

register_exception_handlers(app)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.middleware("http")(audit_middleware)

# 🌐 DYNAMIC SECURITY LAYER: CROSS-ORIGIN RESOURCE SHARING (CORS)
frontend_url = os.getenv("FRONTEND_URL")

DEVELOPMENT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:3000",
]

if frontend_url:
    DEVELOPMENT_ORIGINS.append(frontend_url.strip().rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEVELOPMENT_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ⚡ GLOBAL NGROK BYPASS & ABSOLUTE CORS ENFORCEMENT MIDDLEWARE
@app.middleware("http")
async def absolute_cors_and_ngrok_bypass(request: Request, call_next):
    request_origin = request.headers.get("origin")
    
    # Dynamically resolve origin from whitelist or fallback to first entry
    if request_origin in DEVELOPMENT_ORIGINS:
        allowed_origin = request_origin
    elif frontend_url:
        allowed_origin = frontend_url.strip().rstrip("/")
    else:
        allowed_origin = DEVELOPMENT_ORIGINS[0]

    # 1. Handle Browser Preflight Options checks
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS, HEAD"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # 2. Process standard incoming HTTP stream request
    response = await call_next(request)
    
    # 3. Append global override authorization headers
    response.headers["Access-Control-Allow-Origin"] = allowed_origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, ngrok-skip-browser-warning"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS, HEAD"
    return response

app.add_middleware(NavigationRBACMiddleware)

@app.get("/")
@app.get("/api/v1")
async def read_nexus_root_health_check():
    return {
        "status": "online",
        "system": "NEXUS Core Data Pipeline",
        "engine_version": "0.1.0",
        "database_connectivity": "active"
    }

# 🔌 ROUTER ENDPOINT INJECTION
app.include_router(leads.router, prefix="/api/v1/leads", tags=["Leads"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
app.include_router(conversation_audit.router, prefix="/api/v1", tags=["Agent Audit"])
app.include_router(rbac.router, prefix="/api/v1", tags=["RBAC"])
app.include_router(countries.router, prefix="/api/v1", tags=["Countries"])
app.include_router(education_degrees.router, prefix="/api/v1", tags=["Education"])
app.include_router(education_majors.router, prefix="/api/v1", tags=["Education"])
app.include_router(gpa_cgpa_scores.router, prefix="/api/v1", tags=["Education"])
app.include_router(target_programs.router, prefix="/api/v1", tags=["Study Interest"])
app.include_router(academia.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(academic_calendar.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(academia_wizard.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(login.router, prefix="/api/v1", tags=["Auth"])
app.include_router(counselling.router, prefix="/api/v1", tags=["Counselling"])
app.include_router(command_center.router, prefix="/api/v1", tags=["Command Center"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(nexus_ws.router, prefix="/api/v1", tags=["WebSocket"])
app.include_router(settings_router.router, prefix="/api/v1", tags=["Settings"])
app.include_router(lead_sync.router, prefix="/api/v1", tags=["Settings"])
app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
app.include_router(audit_events.router, prefix="/api/v1", tags=["Audit"])
app.include_router(meta_leads.router, prefix="/api/v1", tags=["Meta Leads"])
app.include_router(security_admin.router, prefix="/api/v1", tags=["Security"])
app.include_router(whatsapp_webhook.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(whatsapp_flow_webhook.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])