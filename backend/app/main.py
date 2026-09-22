import os
import sys
import re
import logging
import asyncio
import mimetypes
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db.database import (
    Base,
    engine,
    install_quiet_tunnel_logging,
    is_ssh_tunnel_database_url,
    safe_close_session,
    sync_schema_columns,
    wait_for_database,
)
from app.config import settings

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
from app.models.education_sub_major import EducationSubMajor  # noqa: F401
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.models.gpa_cgpa_score import GpaCgpaScore
from app.models.full_time_study_year import FullTimeStudyYear  # noqa: F401
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
from app.api.v1 import analytics, notifications, dashboard, users, login, agents, rbac, countries, education_degrees, education_majors, gpa_cgpa_scores, full_time_study_years, qualification_programs, target_programs, conversation_audit, academia, academia_wizard, academic_calendar, nexus_intel, flowx
from app.models.nexus_intel import (  # noqa: F401
    IntelAcademyModule,
    IntelGlossary,
    IntelInquiryFaq,
    IntelScrapeReview,
    IntelScraperConfig,
    IntelTrivia,
    IntelTriviaAnswer,
    IntelUserPreferences,
)
from app.routers import (
    counselling,
    students_master,
    invoices,
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
    scanx,
)
from app.models.scanx import ScanxDocument, ScanxDocumentChunk  # noqa: F401
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
from starlette.requests import Request as StarletteRequest
from slowapi.middleware import SlowAPIMiddleware

# High-volume authenticated SPA traffic — must not share the 60/min global bucket
# with exception-log / audit / academia list pagination (that 429 loop can starve saves).
_RATE_LIMIT_DEFAULT_EXEMPT_PREFIXES = (
    "/api/v1/academia",
    "/api/v1/reports/exception-logs",
    "/api/v1/audit-events",
    "/api/v1/analytics",
)


class NexusSlowAPIMiddleware(SlowAPIMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in _RATE_LIMIT_DEFAULT_EXEMPT_PREFIXES
        ):
            return await call_next(request)
        return await super().dispatch(request, call_next)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

install_quiet_tunnel_logging()


class _RedactQuerySecretsFilter(logging.Filter):
    """Keep JWTs out of uvicorn access lines for /ws/nexus?token=..."""

    _TOKEN_RE = re.compile(r"([?&]token=)([^&\s\"]+)", re.I)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str) and "token=" in record.msg.lower():
                record.msg = self._TOKEN_RE.sub(r"\1[redacted]", record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: (
                            self._TOKEN_RE.sub(r"\1[redacted]", v)
                            if isinstance(v, str) and "token=" in v.lower()
                            else v
                        )
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        self._TOKEN_RE.sub(r"\1[redacted]", a)
                        if isinstance(a, str) and "token=" in a.lower()
                        else a
                        for a in record.args
                    )
        except Exception:
            pass
        return True


_secret_filter = _RedactQuerySecretsFilter()
for _logger_name in ("uvicorn.access", "uvicorn", "uvicorn.error"):
    logging.getLogger(_logger_name).addFilter(_secret_filter)

bootstrap_logger = logging.getLogger(__name__)


def bootstrap_application(*, include_deferred: bool = True) -> None:
    """Run one-time DB/schema seeding. Called from lifespan, not at import time."""
    skip_db_sync = os.getenv("NEXUS_SKIP_STARTUP_DB_SYNC", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        if skip_db_sync:
            bootstrap_logger.info(
                "Skipping create_all/sync_schema (NEXUS_SKIP_STARTUP_DB_SYNC is set)."
            )
        else:
            bootstrap_logger.info("Nexus database synchronization: checking table structures...")
            Base.metadata.create_all(bind=engine)
            sync_schema_columns()
            bootstrap_logger.info("Nexus database synchronization: tables initialized successfully.")
        bootstrap_db = SessionLocal()
        try:
            from sqlalchemy.exc import DBAPIError, OperationalError

            from app.db.database import dispose_db_pool, ensure_db_connection
            from app.services.navigation_rbac import ensure_navigation_rbac

            seed_attempts = 4
            last_seed_exc: BaseException | None = None
            for seed_attempt in range(seed_attempts):
                try:
                    if seed_attempt:
                        try:
                            bootstrap_db.rollback()
                        except Exception:
                            pass
                        dispose_db_pool(
                            reason=f"bootstrap seed retry {seed_attempt}"
                        )
                        try:
                            safe_close_session(bootstrap_db)
                        except Exception:
                            pass
                        wait_for_database(
                            attempts=8, delay_sec=1.0, dispose_between=True
                        )
                        bootstrap_db = SessionLocal()
                        ensure_db_connection(bootstrap_db)
                        time.sleep(min(1.0 * seed_attempt, 3.0))
                    get_or_create_agent_config(bootstrap_db)
                    bootstrap_logger.info("Agent runtime configuration initialized.")
                    recovered = recover_stale_sync_logs(bootstrap_db)
                    if recovered:
                        bootstrap_logger.info(
                            "Recovered %s stale in-progress sync log(s).", recovered
                        )
                    ensure_default_business(bootstrap_db)
                    ensure_navigation_rbac(bootstrap_db)
                    bootstrap_logger.info(
                        "Navigation pages and role access catalog synchronized."
                    )
                    last_seed_exc = None
                    break
                except (OperationalError, DBAPIError) as exc:
                    last_seed_exc = exc
                    bootstrap_logger.warning(
                        "Bootstrap seed failed attempt=%s/%s: %s",
                        seed_attempt + 1,
                        seed_attempts,
                        exc,
                    )
                    continue
            if last_seed_exc is not None:
                raise last_seed_exc
            bootstrap_logger.info("Startup catalog/reference seeds are disabled (manage data via Admin UI).")
            bootstrap_logger.info("Dynamic settings initialized.")
            if include_deferred:
                _bootstrap_deferred_services(bootstrap_db)
            bootstrap_logger.info("Application bootstrap complete.")
        finally:
            safe_close_session(bootstrap_db)
    except Exception:
        bootstrap_logger.exception(
            "Critical error during database sync lifecycle initialization"
        )
        raise


def _bootstrap_deferred_services(bootstrap_db) -> None:
    """Slow startup work (consultation slots can take 30–60s on cold Neon)."""
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


def _run_deferred_step(name: str, fn) -> None:
    """Run one deferred step on a fresh session; never abort sibling steps."""
    from sqlalchemy.exc import DBAPIError, OperationalError

    from app.db.database import dispose_db_pool, ensure_db_connection, wait_for_database

    for attempt in range(2):
        db = SessionLocal()
        try:
            if attempt:
                dispose_db_pool(reason=f"deferred step {name} retry")
                wait_for_database(attempts=6, delay_sec=1.0, dispose_between=True)
                ensure_db_connection(db)
            fn(db)
            bootstrap_logger.info("Deferred step ok: %s", name)
            return
        except (OperationalError, DBAPIError) as exc:
            bootstrap_logger.warning(
                "Deferred step %s failed attempt=%s/2: %s",
                name,
                attempt + 1,
                type(exc).__name__,
            )
            try:
                db.rollback()
            except Exception:
                pass
        except Exception:
            bootstrap_logger.exception("Deferred step %s failed", name)
            return
        finally:
            try:
                safe_close_session(db)
            except Exception:
                pass
    bootstrap_logger.error("Deferred step skipped after retries: %s", name)


def bootstrap_deferred_application() -> None:
    """Run after the HTTP server is accepting connections.

    Each step uses its own short-lived session so a tunnel drop during consultation
    slot seeding cannot block flow-key / webhook audit initialization.
    """
    def _slots(db) -> None:
        ensure_consultation_slots(db)

    def _flow(_db) -> None:
        ensure_flow_keypair()

    def _whatsapp_audit(_db) -> None:
        if os.getenv("WHATSAPP_FLOW_ID"):
            bootstrap_logger.info("WhatsApp Flow booking enabled.")
            bootstrap_logger.info(
                "Flow public key ready for Meta upload "
                "(GET /api/v1/webhooks/whatsapp-flow/public-key)"
            )
        from app.services.whatsapp_webhook_env import audit_whatsapp_webhook_routing

        audit_whatsapp_webhook_routing(check_reachability=False)

    _run_deferred_step("consultation_slots", _slots)
    _run_deferred_step("flow_keypair", _flow)
    _run_deferred_step("whatsapp_webhook_audit", _whatsapp_audit)
    bootstrap_logger.info("Deferred application bootstrap complete.")


def _silence_windows_proactor_disconnects() -> None:
    """Drop known-benign Proactor ERROR logs on abrupt client disconnects.

    Windows ProactorEventLoop raises ConnectionResetError / ConnectionAbortedError
    inside ``_ProactorBasePipeTransport._call_connection_lost`` when the peer
    already closed the TCP socket (browser refresh, Vite HMR, cloudflared, etc.).
    asyncio then logs ERROR even though the app and request handlers are fine.
    Only that callback pattern is suppressed; all other loop exceptions still
    use the default handler.
    """
    if sys.platform != "win32":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _handler(event_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
            message = context.get("message") or ""
            if "_call_connection_lost" in message:
                return
        event_loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _silence_windows_proactor_disconnects()

    # Hard gate for Hostinger SSH tunnel: do not run DB bootstrap (or look "ready")
    # until TCP + SELECT 1 succeed. start-dev.ps1 / run_dev.py also gate earlier.
    tunnel_db = is_ssh_tunnel_database_url(settings.DATABASE_URL)
    try:
        if tunnel_db:
            bootstrap_logger.info(
                "[db-tunnel] waiting for SELECT 1 before bootstrap "
                "(start tunnel: .\\start-hostinger-db-tunnel.ps1)"
            )
            await asyncio.to_thread(wait_for_database)
        else:
            await asyncio.to_thread(wait_for_database, attempts=10, delay_sec=1.0)
    except Exception:
        if tunnel_db:
            bootstrap_logger.exception(
                "[db-tunnel] database unreachable — refusing degraded start. "
                "Restart: powershell -ExecutionPolicy Bypass -File .\\start-dev.ps1"
            )
            raise
        bootstrap_logger.exception(
            "Database not ready at startup — continuing; requests may fail until DB is up"
        )

    # Fast path only — do not block uvicorn bind on consultation-slot generation.
    try:
        await asyncio.to_thread(bootstrap_application, include_deferred=False)
    except Exception:
        if tunnel_db:
            bootstrap_logger.exception(
                "[db-tunnel] bootstrap failed after healthy SELECT 1 — refusing degraded start"
            )
            raise
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

    # Pre-warm ScanX OCR off the critical path: Rapid (primary) first, then
    # Paddle (fallback) so first mark-sheet parse is inference-only.
    def _prewarm_scanx_ocr() -> None:
        try:
            from app.services.scanx_ocr import prewarm_ocr_engines

            bootstrap_logger.info("ScanX OCR pre-warm starting…")
            prewarm_ocr_engines(include_fallback=True)
            bootstrap_logger.info("ScanX OCR pre-warm finished")
        except Exception:
            bootstrap_logger.exception("ScanX OCR pre-warm failed (cold start on first doc)")

    asyncio.create_task(asyncio.to_thread(_prewarm_scanx_ocr))

    yield

    deferred.cancel()
    try:
        await deferred
    except asyncio.CancelledError:
        pass

    shutdown_raw_lead_processor_scheduler()
    shutdown_lead_sync_scheduler()
    shutdown_security_scheduler()
    from app.services.messaging import close_whatsapp_graph_http_client

    await close_whatsapp_graph_http_client()


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

from app.middleware.exception_capture import QuietDbTunnelMiddleware, register_exception_handlers

register_exception_handlers(app)

app.add_middleware(NexusSlowAPIMiddleware)
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
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Nexus-Page, X-Requested-With, ngrok-skip-browser-warning"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # 2. Process standard incoming HTTP stream request
    response = await call_next(request)
    
    # 3. Append global override authorization headers
    response.headers["Access-Control-Allow-Origin"] = allowed_origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Nexus-Page, X-Requested-With, ngrok-skip-browser-warning"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS, HEAD"
    return response

app.add_middleware(NavigationRBACMiddleware)

# Outermost user middleware: inside ServerErrorMiddleware, so tunnel drops
# become a 503 instead of a re-raised traceback in the uvicorn log.
app.add_middleware(QuietDbTunnelMiddleware)

@app.get("/")
@app.get("/health")
@app.get("/api/health")
@app.get("/api/v1")
@app.get("/api/v1/health")
async def read_nexus_root_health_check():
    from sqlalchemy import text

    from app.db.database import dispose_db_pool, is_ssh_tunnel_database_url

    # SSH-tunnel SELECT 1 often takes 5–15s under load; a 5s wait_for + pool dispose
    # on every miss thrashed connections and produced systemic API 500s.
    tunnel_db = is_ssh_tunnel_database_url(settings.DATABASE_URL)
    ping_timeout = 25.0 if tunnel_db else 5.0
    db_status = "unavailable"
    try:
        def _ping_db() -> None:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

        await asyncio.wait_for(asyncio.to_thread(_ping_db), timeout=ping_timeout)
        db_status = "active"
    except Exception as exc:
        db_status = "unavailable"
        # Only dispose on hard connectivity failures, and at most once per 60s,
        # so slow pings do not wipe a healthy pool.
        if tunnel_db:
            msg = f"{type(exc).__name__}: {exc}".lower()
            hard_fail = any(
                token in msg
                for token in (
                    "connection refused",
                    "connectionreset",
                    "connection reset",
                    "server closed",
                    "could not connect",
                    "no route to host",
                    "network is unreachable",
                    "connectiontimeout",
                    "timeout expired",
                )
            )
            now = asyncio.get_running_loop().time()
            last = getattr(read_nexus_root_health_check, "_last_pool_dispose_at", 0.0)
            if hard_fail and (now - last) >= 60.0:
                try:
                    dispose_db_pool(reason="health check SELECT 1 failed")
                    read_nexus_root_health_check._last_pool_dispose_at = now  # type: ignore[attr-defined]
                except Exception:
                    pass

    return {
        "status": "online" if db_status == "active" else "degraded",
        "system": "NEXUS Core Data Pipeline",
        "engine_version": "0.1.0",
        "database_connectivity": db_status,
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
app.include_router(full_time_study_years.router, prefix="/api/v1", tags=["Education"])
app.include_router(qualification_programs.router, prefix="/api/v1", tags=["Education"])
app.include_router(target_programs.router, prefix="/api/v1", tags=["Study Interest"])
app.include_router(academia.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(academic_calendar.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(academia_wizard.router, prefix="/api/v1", tags=["Academia Hub"])
app.include_router(nexus_intel.router, prefix="/api/v1", tags=["Nexus Intel"])
app.include_router(flowx.router, prefix="/api/v1", tags=["FlowX"])
app.include_router(login.router, prefix="/api/v1", tags=["Auth"])
app.include_router(counselling.router, prefix="/api/v1", tags=["Counselling"])
app.include_router(students_master.router, prefix="/api/v1", tags=["Students Master"])
app.include_router(invoices.router, prefix="/api/v1", tags=["Invoices"])
app.include_router(scanx.router, prefix="/api/v1", tags=["ScanX"])
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