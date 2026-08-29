from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from app.config import normalize_database_url, settings


def _engine_pool_recycle(database_url: str) -> int:
    if database_url.startswith("sqlite"):
        return 1800
    # Neon/serverless Postgres terminates idle connections; recycle before that.
    # Fine on Hostinger too (idle TCP / SSH-tunnel drops).
    return 300


def _engine_connect_args(database_url: str) -> dict:
    """Optional libpq options — keep empty unless PG_STATEMENT_TIMEOUT_MS is set."""
    if database_url.startswith("sqlite"):
        return {}
    timeout_ms = int(getattr(settings, "PG_STATEMENT_TIMEOUT_MS", 0) or 0)
    if timeout_ms <= 0:
        return {}
    # Applied on every new connection (pool checkout of a fresh conn).
    return {"options": f"-c statement_timeout={timeout_ms}"}


# Belt-and-suspenders: Settings already normalizes, but re-apply so engine never
# sees Neon console channel_binding=require or bare postgresql:// (psycopg2).
_DATABASE_URL = normalize_database_url(settings.DATABASE_URL)

# Pool notes for remote / SSH-tunnel Postgres:
# - pool_pre_ping=True costs one SELECT 1 after idle; over an SSH tunnel that is
#   often 200–500 ms RTT (server-side work is ~0.01 ms). Prefer backend-on-VPS
#   or firewall-to-home-IP when developing against Hostinger.
# - pool_size=10 is appropriate for local single-worker uvicorn; Hostinger does
#   not use Neon's pooler endpoint, so this is direct Postgres connections.
engine = create_engine(
    _DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=_engine_pool_recycle(_DATABASE_URL),
    pool_pre_ping=True,
    connect_args=_engine_connect_args(_DATABASE_URL),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    from app.models.lead import Lead
    from app.models.message import Message

    Base.metadata.create_all(bind=engine)


def _column_type_name(inspector, table_name: str, column_name: str) -> str:
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return str(column["type"]).upper()
    return ""


def _is_text_column(type_name: str) -> bool:
    return "VARCHAR" in type_name or "CHARACTER VARYING" in type_name or type_name == "TEXT"


class _SchemaSnapshot:
    """Lazy schema introspection — one table list, cached per-table columns."""

    def __init__(self, db_engine):
        self._engine = db_engine
        self._inspector = inspect(db_engine)
        self._tables: set[str] | None = None
        self._columns: dict[str, dict[str, dict]] = {}

    def has_table(self, name: str) -> bool:
        return name in self._table_names()

    def column_names(self, name: str) -> set[str]:
        return set(self.columns(name).keys())

    def columns(self, name: str) -> dict[str, dict]:
        if name not in self._columns:
            if not self.has_table(name):
                self._columns[name] = {}
            else:
                self._columns[name] = {
                    col["name"]: col for col in self._inspector.get_columns(name)
                }
        return self._columns[name]

    def column_type_name(self, table: str, column: str) -> str:
        col = self.columns(table).get(column)
        return str(col["type"]).upper() if col else ""

    def refresh(self) -> None:
        self._tables = None
        self._columns.clear()
        self._inspector = inspect(self._engine)

    def drop_table(self, name: str) -> None:
        self._table_names().discard(name)
        self._columns.pop(name, None)

    def note_table(self, name: str) -> None:
        self._table_names().add(name)
        self._columns.pop(name, None)

    def _table_names(self) -> set[str]:
        if self._tables is None:
            self._tables = set(self._inspector.get_table_names())
        return self._tables


def sync_schema_columns() -> None:
    """Add or rename columns that create_all() cannot backfill on existing tables."""
    snap = _SchemaSnapshot(engine)
    _ensure_institution_types_catalog()

    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        if "assigned_advisor_id" not in lead_columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE leads ADD COLUMN assigned_advisor_id INTEGER "
                        "REFERENCES users(id)"
                    )
                )

        intake_columns = {
            "intake_step": "VARCHAR(50)",
            "current_location": "VARCHAR(255)",
            "english_test_scores": "VARCHAR(100)",
            "gre_score": "VARCHAR(50)",
            "gmat_score": "VARCHAR(50)",
            "wants_consultation_call": "BOOLEAN",
            "consultation_scheduled_at": "TIMESTAMP",
            "intake_context": "TEXT",
        }
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            for column_name, column_type in intake_columns.items():
                if column_name not in lead_columns:
                    conn.execute(
                        text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
                    )

    if not snap.has_table("users"):
        return

    user_columns = snap.column_names("users")

    with engine.begin() as conn:
        if "status_change_reason_id" in user_columns and "activation_reason" not in user_columns:
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN status_change_reason_id TO activation_reason")
            )
            user_columns.remove("status_change_reason_id")
            user_columns.add("activation_reason")

        if "status_changed_at" in user_columns and "activation_date" not in user_columns:
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN status_changed_at TO activation_date")
            )
            user_columns.remove("status_changed_at")
            user_columns.add("activation_date")

        if "creation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN creation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "creation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN creation_date TIMESTAMP"))

        if "deactivation_reason" in user_columns and _is_text_column(
            snap.column_type_name("users", "deactivation_reason")
        ):
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN deactivation_reason_fk INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET deactivation_reason_fk = scr.id
                    FROM status_change_reason scr
                    WHERE scr.reason_type = 'Deactivate'
                      AND scr.reason = u.deactivation_reason
                      AND u.deactivation_reason IS NOT NULL
                      AND btrim(u.deactivation_reason) <> ''
                    """
                )
            )
            conn.execute(text("ALTER TABLE users DROP COLUMN deactivation_reason"))
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN deactivation_reason_fk TO deactivation_reason")
            )
            user_columns.discard("deactivation_reason")
            user_columns.add("deactivation_reason")

        if "deactivation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN deactivation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "deactivation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN deactivation_date TIMESTAMP"))

        if "activation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN activation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "activation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN activation_date TIMESTAMP"))

        if "admin_role_id" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN admin_role_id INTEGER "
                    "REFERENCES admin_roles(id)"
                )
            )
            user_columns.add("admin_role_id")

        if "phone_number" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(50)"))

        if "role" in user_columns and _is_text_column(
            snap.column_type_name("users", "role")
        ):
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) = lower(btrim(ar.name))
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) IN ('admin', 'web admin')
                      AND ar.name = 'Web Admin'
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) = 'super admin'
                      AND ar.name = 'Super Admin'
                    """
                )
            )
            conn.execute(text("ALTER TABLE users DROP COLUMN role"))
            user_columns.discard("role")

        if "admin_role_id" in user_columns:
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND ar.name = 'Web Admin'
                    """
                )
            )

    snap.refresh()

    if snap.has_table("navigation_pages"):
        nav_columns = snap.column_names("navigation_pages")
        with engine.begin() as conn:
            if "icon" not in nav_columns:
                conn.execute(text("ALTER TABLE navigation_pages ADD COLUMN icon VARCHAR(50)"))
            if "sort_order" not in nav_columns:
                conn.execute(
                    text("ALTER TABLE navigation_pages ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
                )
            if "is_active" not in nav_columns:
                conn.execute(
                    text(
                        "ALTER TABLE navigation_pages ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )

    if snap.has_table("role_page_permissions"):
        perm_columns = snap.column_names("role_page_permissions")
        required_perm_columns = {"admin_role_id", "navigation_page_id", "can_access"}
        if not required_perm_columns.issubset(perm_columns):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS role_page_permissions"))
            snap.drop_table("role_page_permissions")

    snap.refresh()
    if not snap.has_table("role_page_permissions"):
        from app.models.role_page_permission import RolePagePermission

        RolePagePermission.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("role_page_permissions")

    snap.refresh()

    if snap.has_table("counselling_bookings"):
        booking_columns = snap.column_names("counselling_bookings")
        with engine.begin() as conn:
            if "scheduled_time" not in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ADD COLUMN scheduled_time TIMESTAMP")
                )
                if "slot_id" in booking_columns and snap.has_table("counselling_slots"):
                    conn.execute(
                        text(
                            """
                            UPDATE counselling_bookings cb
                            SET scheduled_time = cs.start_time
                            FROM counselling_slots cs
                            WHERE cb.slot_id = cs.id
                              AND cb.scheduled_time IS NULL
                            """
                        )
                    )
                conn.execute(
                    text(
                        """
                        UPDATE counselling_bookings
                        SET scheduled_time = COALESCE(updated_at, created_at, NOW())
                        WHERE scheduled_time IS NULL
                        """
                    )
                )
                conn.execute(
                    text("ALTER TABLE counselling_bookings ALTER COLUMN scheduled_time SET NOT NULL")
                )
                booking_columns.add("scheduled_time")

            if "candidate_email" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN candidate_email VARCHAR(255)"))
            if "candidate_phone" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN candidate_phone VARCHAR(50)"))
            if "lead_id" not in booking_columns:
                conn.execute(
                    text(
                        "ALTER TABLE counselling_bookings ADD COLUMN lead_id INTEGER "
                        "REFERENCES leads(id) ON DELETE SET NULL"
                    )
                )

            if "admin_id" in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ALTER COLUMN admin_id DROP NOT NULL")
                )

            if "slot_id" in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings DROP CONSTRAINT IF EXISTS counselling_bookings_slot_id_fkey"))
                conn.execute(text("ALTER TABLE counselling_bookings DROP COLUMN IF EXISTS slot_id"))

            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'PENDING'
                    WHERE admin_id IS NULL
                      AND upper(status) NOT IN ('CANCELLED', 'SCHEDULED')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'SCHEDULED'
                    WHERE admin_id IS NOT NULL
                      AND upper(status) NOT IN ('CANCELLED')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'CANCELLED'
                    WHERE lower(status) = 'cancelled'
                    """
                )
            )

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS counselling_slots CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS counselling_rosters CASCADE"))
    snap.drop_table("counselling_slots")
    snap.drop_table("counselling_rosters")

    snap.refresh()
    if snap.has_table("dynamic_settings"):
        setting_columns = snap.column_names("dynamic_settings")
        with engine.begin() as conn:
            if "updated_by_user_id" not in setting_columns:
                conn.execute(
                    text(
                        "ALTER TABLE dynamic_settings ADD COLUMN updated_by_user_id INTEGER "
                        "REFERENCES users(id) ON DELETE SET NULL"
                    )
                )

    snap.refresh()
    if snap.has_table("notification_logs"):
        log_columns = snap.column_names("notification_logs")
        with engine.begin() as conn:
            if "user_id" not in log_columns:
                conn.execute(
                    text(
                        "ALTER TABLE notification_logs ADD COLUMN user_id INTEGER "
                        "REFERENCES users(id) ON DELETE SET NULL"
                    )
                )
            if "title" not in log_columns:
                conn.execute(text("ALTER TABLE notification_logs ADD COLUMN title VARCHAR(255) DEFAULT ''"))
            if "message" not in log_columns:
                conn.execute(text("ALTER TABLE notification_logs ADD COLUMN message TEXT DEFAULT ''"))
            if "priority" not in log_columns:
                conn.execute(
                    text("ALTER TABLE notification_logs ADD COLUMN priority VARCHAR(20) DEFAULT 'normal'")
                )
            booking_col = snap.columns("notification_logs").get("booking_id")
            if booking_col and not booking_col.get("nullable", True):
                if engine.dialect.name == "postgresql":
                    conn.execute(text("ALTER TABLE notification_logs ALTER COLUMN booking_id DROP NOT NULL"))

    snap.refresh()
    if snap.has_table("users"):
        user_columns = snap.column_names("users")
        with engine.begin() as conn:
            if "fcm_tokens" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN fcm_tokens TEXT"))

    if not snap.has_table("businesses"):
        from app.models.business import Business

        Business.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("businesses")

    snap.refresh()
    if snap.has_table("businesses"):
        business_columns = snap.column_names("businesses")
        address_columns = {
            "address_line1": "VARCHAR(255)",
            "address_line2": "VARCHAR(255)",
            "address_line3": "VARCHAR(255)",
            "city": "VARCHAR(120)",
            "state": "VARCHAR(120)",
            "country": "VARCHAR(120)",
            "zip_code": "VARCHAR(30)",
            "office_phone_number": "VARCHAR(50)",
            "office_mobile_number": "VARCHAR(50)",
            "office_phone_active": "BOOLEAN",
            "office_mobile_active": "BOOLEAN",
            "office_phone_contacts": "JSON",
            "office_email_contacts": "JSON",
            "logo_path": "VARCHAR(500)",
        }
        with engine.begin() as conn:
            for column_name, column_type in address_columns.items():
                if column_name not in business_columns:
                    dialect = engine.dialect.name
                    sql_type = column_type
                    if column_type == "JSON" and dialect == "postgresql":
                        sql_type = "JSONB"
                    conn.execute(
                        text(f"ALTER TABLE businesses ADD COLUMN {column_name} {sql_type}")
                    )
            if "office_phone_active" not in business_columns:
                conn.execute(
                    text(
                        "UPDATE businesses SET office_phone_active = TRUE "
                        "WHERE office_phone_active IS NULL"
                    )
                )
            if "office_mobile_active" not in business_columns:
                conn.execute(
                    text(
                        "UPDATE businesses SET office_mobile_active = TRUE "
                        "WHERE office_mobile_active IS NULL"
                    )
                )
            if "address" in business_columns and "address_line1" in (
                business_columns | set(address_columns.keys())
            ):
                conn.execute(
                    text(
                        "UPDATE businesses SET address_line1 = address "
                        "WHERE address IS NOT NULL AND TRIM(address) <> '' "
                        "AND (address_line1 IS NULL OR TRIM(address_line1) = '')"
                    )
                )

    snap.refresh()
    if snap.has_table("users") and snap.has_table("businesses"):
        user_columns = snap.column_names("users")
        with engine.begin() as conn:
            if "business_id" not in user_columns:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN business_id INTEGER "
                        "REFERENCES businesses(id) DEFAULT 1"
                    )
                )
                conn.execute(text("UPDATE users SET business_id = 1 WHERE business_id IS NULL"))

    migrate_audit_logs_schema()

    snap.refresh()
    if not snap.has_table("security_audit_runs"):
        from app.models.security_audit_run import SecurityAuditRun

        SecurityAuditRun.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("security_audit_runs")

    if not snap.has_table("sync_logs"):
        from app.models.sync_log import SyncLog

        SyncLog.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("sync_logs")
    elif snap.has_table("sync_logs"):
        sync_log_columns = snap.column_names("sync_logs")
        with engine.begin() as conn:
            if "sync_mode" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN sync_mode VARCHAR(20) NOT NULL DEFAULT 'AUTOMATED'"))
            if "triggered_by_user" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN triggered_by_user VARCHAR(255) NOT NULL DEFAULT 'UNKNOWN'"))
            if "triggered_by_user_id" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN triggered_by_user_id INTEGER"))
            if "results_count" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN results_count INTEGER NOT NULL DEFAULT 0"))
            if "message" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN message TEXT"))
            if "attempt_timestamp" not in sync_log_columns:
                if "started_at" in sync_log_columns:
                    conn.execute(text("ALTER TABLE sync_logs ADD COLUMN attempt_timestamp TIMESTAMP"))
                    conn.execute(text("UPDATE sync_logs SET attempt_timestamp = started_at WHERE attempt_timestamp IS NULL"))
                else:
                    conn.execute(text("ALTER TABLE sync_logs ADD COLUMN attempt_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.execute(
                text(
                    "UPDATE sync_logs SET attempt_timestamp = started_at "
                    "WHERE attempt_timestamp IS NULL AND started_at IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET started_at = attempt_timestamp "
                    "WHERE started_at IS NULL AND attempt_timestamp IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET results_count = COALESCE(leads_created, 0) + COALESCE(leads_skipped, 0) "
                    "WHERE results_count = 0 AND (COALESCE(leads_created, 0) + COALESCE(leads_skipped, 0)) > 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET status = UPPER(status) "
                    "WHERE status IN ('success', 'partial', 'failed', 'running')"
                )
            )
            conn.execute(text("UPDATE sync_logs SET status = 'WARNING' WHERE status = 'PARTIAL'"))

    snap.refresh()
    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            if "admission_stage" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN admission_stage VARCHAR(50)"))
            if "admission_stage_entered_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN admission_stage_entered_at TIMESTAMP"))
            if "documents_submitted_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN documents_submitted_at TIMESTAMP"))
            if "source" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN source VARCHAR(50)"))
            if "meta_leadgen_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_leadgen_id VARCHAR(100)"))
            if "meta_campaign_name" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_campaign_name VARCHAR(255)"))
            if "meta_form_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_form_id VARCHAR(100)"))
            if "meta_ad_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_ad_id VARCHAR(100)"))
            if "additional_data" not in lead_columns:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("ALTER TABLE leads ADD COLUMN additional_data JSONB"))
                else:
                    conn.execute(text("ALTER TABLE leads ADD COLUMN additional_data JSON"))
            if engine.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_meta_leadgen_id "
                        "ON leads (meta_leadgen_id) WHERE meta_leadgen_id IS NOT NULL"
                    )
                )
                conn.execute(text("ALTER TYPE leadchannel ADD VALUE IF NOT EXISTS 'FACEBOOK'"))

    if snap.has_table("counselling_bookings"):
        booking_columns = snap.column_names("counselling_bookings")
        with engine.begin() as conn:
            if "outcome_key" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN outcome_key VARCHAR(50)"))
            if "wrap_up_notes" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN wrap_up_notes TEXT"))
            if "completed_at" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN completed_at TIMESTAMP"))
            if "intake_assessment" not in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ADD COLUMN intake_assessment JSONB")
                )

    if not snap.has_table("admission_history"):
        from app.models.admission_history import AdmissionHistory

        AdmissionHistory.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("admission_history")

    if not snap.has_table("candidate_tasks"):
        from app.models.candidate_task import CandidateTask

        CandidateTask.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_tasks")

    if not snap.has_table("conversations"):
        from app.models.conversation import Conversation

        Conversation.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("conversations")

    if not snap.has_table("conversation_participants"):
        from app.models.conversation_participant import ConversationParticipant

        ConversationParticipant.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("conversation_participants")

    if not snap.has_table("internal_messages"):
        from app.models.internal_message import InternalMessage

        InternalMessage.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("internal_messages")

    if not snap.has_table("counselling_notes"):
        from app.models.counselling_note import CounsellingNote

        CounsellingNote.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("counselling_notes")

    if not snap.has_table("candidate_educations"):
        from app.models.candidate_education import CandidateEducation

        CandidateEducation.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_educations")

    if not snap.has_table("non_academic_activities"):
        from app.models.non_academic_activity import NonAcademicActivity

        NonAcademicActivity.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("non_academic_activities")

    if not snap.has_table("digital_presence_links"):
        from app.models.digital_presence_link import DigitalPresenceLink

        DigitalPresenceLink.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("digital_presence_links")

    if not snap.has_table("research_projects"):
        from app.models.research_project import ResearchProject

        ResearchProject.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("research_projects")

    if not snap.has_table("work_experiences"):
        from app.models.work_experience import WorkExperience, WorkProject

        WorkExperience.__table__.create(bind=engine, checkfirst=True)
        WorkProject.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("work_experiences")
        snap.note_table("work_projects")

    if not snap.has_table("candidate_test_scores"):
        from app.models.candidate_test_score import CandidateTestScore

        CandidateTestScore.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_test_scores")

    if snap.has_table("candidate_test_scores"):
        score_columns = snap.column_names("candidate_test_scores")
        if "overall_score" not in score_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE candidate_test_scores ADD COLUMN overall_score NUMERIC(6, 2)")
                )

    if not snap.has_table("students_master"):
        from app.models.students_master import StudentsMaster

        StudentsMaster.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("students_master")

    if snap.has_table("students_master"):
        master_columns = snap.column_names("students_master")
        if "aspirations_data" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN aspirations_data JSON"))
        if "gender" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN gender VARCHAR(20)"))
        if "marital_status" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN marital_status VARCHAR(20)"))
        if "registration_data" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN registration_data JSON"))

    if not snap.has_table("status_definitions"):
        from app.models.status_definition import StatusDefinition

        StatusDefinition.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("status_definitions")

    if not snap.has_table("status_history"):
        from app.models.status_history import StatusHistory

        StatusHistory.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("status_history")

    if not snap.has_table("system_logs"):
        from app.models.system_log import SystemLog

        SystemLog.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("system_logs")

    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            if "status_definition_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_definition_id INTEGER"))
            if "status_entered_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_entered_at TIMESTAMP"))

    if snap.has_table("internal_messages"):
        message_columns = snap.column_names("internal_messages")
        with engine.begin() as conn:
            if "search_vector" not in message_columns:
                conn.execute(text("ALTER TABLE internal_messages ADD COLUMN search_vector TSVECTOR"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_internal_messages_search_vector "
                    "ON internal_messages USING GIN (search_vector)"
                )
            )
            conn.execute(
                text(
                    "UPDATE internal_messages "
                    "SET search_vector = to_tsvector('english', coalesce(content, '')) "
                    "WHERE search_vector IS NULL"
                )
            )
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_internal_messages_content_trgm "
                    "ON internal_messages USING GIN (content gin_trgm_ops)"
                )
            )
            if "reply_to_message_id" not in message_columns:
                conn.execute(
                    text(
                        "ALTER TABLE internal_messages ADD COLUMN reply_to_message_id INTEGER "
                        "REFERENCES internal_messages(id) ON DELETE SET NULL"
                    )
                )

    if snap.has_table("education_majors"):
        major_columns = snap.column_names("education_majors")
        with engine.begin() as conn:
            if "description" in major_columns and "major_description" not in major_columns:
                conn.execute(
                    text(
                        "ALTER TABLE education_majors "
                        "RENAME COLUMN description TO major_description"
                    )
                )
                major_columns.discard("description")
                major_columns.add("major_description")
            if "major_description" not in major_columns:
                conn.execute(
                    text("ALTER TABLE education_majors ADD COLUMN major_description TEXT")
                )
                major_columns.add("major_description")
            if "sub_majors_key_fields" not in major_columns:
                conn.execute(
                    text(
                        "ALTER TABLE education_majors "
                        "ADD COLUMN sub_majors_key_fields TEXT"
                    )
                )

    if snap.has_table("education_sub_majors"):
        sub_major_columns = snap.column_names("education_sub_majors")
        if "sub_major_description" not in sub_major_columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE education_sub_majors "
                        "ADD COLUMN sub_major_description TEXT"
                    )
                )

    if snap.has_table("programs"):
        program_columns = snap.column_names("programs")
        if "program_url" not in program_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE programs ADD COLUMN program_url VARCHAR(2048)")
                )

    _ensure_program_major_mapping_sub_uniqueness()

    if not snap.has_table("message_reactions"):
        from app.models.message_reaction import MessageReaction

        MessageReaction.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("message_reactions")


def _ensure_program_major_mapping_sub_uniqueness() -> None:
    """Replace unique(program, major) with unique(program, major, sub) + one NULL sub."""
    inspector = inspect(engine)
    table = "program_education_major_mappings"
    if not inspector.has_table(table):
        return
    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = :table
                      AND indexname IN (
                          'uq_pem_program_major_sub',
                          'uq_pem_program_major_null_sub'
                      )
                    """
                ),
                {"table": table},
            )
        }
        if existing >= {"uq_pem_program_major_sub", "uq_pem_program_major_null_sub"}:
            return
    old_uq = "uq_program_education_major_mappings_program_major"
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {old_uq}"))
        conn.execute(text(f"DROP INDEX IF EXISTS {old_uq}"))
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pem_program_major_sub
                ON program_education_major_mappings
                    (program_id, education_major_id, education_sub_major_id)
                WHERE education_sub_major_id IS NOT NULL
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pem_program_major_null_sub
                ON program_education_major_mappings
                    (program_id, education_major_id)
                WHERE education_sub_major_id IS NULL
                """
            )
        )


INSTITUTION_TYPE_CATALOG = (
    ("PUBLIC_STATE", "Public / State", 1),
    ("PRIVATE", "Private", 2),
    ("COMMUNITY_COLLEGE", "Community College", 3),
    ("TECHNICAL_INSTITUTE", "Technical Institute", 4),
    ("OTHERS", "Others", 5),
)


def _ensure_institution_types_catalog(db_engine=None) -> None:
    """Insert missing institution_types rows; keep Technical Institute visible.

    On conflict, re-activate catalog rows and refresh sort_order. Custom names
    are preserved unless they only differ by surrounding whitespace.
    """
    db_engine = db_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("institutions"):
        return
    if not inspector.has_table("institution_types"):
        from app.models.academia_institution import InstitutionType

        InstitutionType.__table__.create(bind=db_engine, checkfirst=True)
        inspector = inspect(db_engine)

    inst_columns = {column["name"] for column in inspector.get_columns("institutions")}
    if "institution_type_id" not in inst_columns:
        return

    with db_engine.begin() as conn:
        for code, name, sort_order in INSTITUTION_TYPE_CATALOG:
            conn.execute(
                text(
                    """
                    INSERT INTO institution_types (code, name, is_active, sort_order)
                    VALUES (:code, :name, true, :sort_order)
                    ON CONFLICT (code) DO UPDATE SET
                        is_active = true,
                        sort_order = EXCLUDED.sort_order,
                        name = CASE
                            WHEN trim(institution_types.name) = trim(EXCLUDED.name)
                            THEN EXCLUDED.name
                            ELSE institution_types.name
                        END
                    """
                ),
                {"code": code, "name": name, "sort_order": sort_order},
            )


def migrate_audit_logs_schema() -> None:
    """Bring audit_logs in line with the current AuditLog model (idempotent)."""
    from app.models.audit_log import AuditLog

    inspector = inspect(engine)
    if not inspector.has_table("audit_logs"):
        AuditLog.__table__.create(bind=engine, checkfirst=True)
        return

    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    with engine.begin() as conn:
        if "action" in audit_columns and "action_type" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs RENAME COLUMN action TO action_type"))
            audit_columns.remove("action")
            audit_columns.add("action_type")
        if "resource" in audit_columns and "target_resource" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs RENAME COLUMN resource TO target_resource"))
            audit_columns.remove("resource")
            audit_columns.add("target_resource")
        if "details" not in audit_columns:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN details JSONB"))
            else:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN details JSON"))
            audit_columns.add("details")
            if "detail" in audit_columns and engine.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "UPDATE audit_logs SET details = jsonb_build_object('legacy_detail', detail) "
                        "WHERE detail IS NOT NULL AND detail <> '' AND details IS NULL"
                    )
                )
        if "session_id" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN session_id VARCHAR(128)"))
        if "sync_mode" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN sync_mode VARCHAR(20)"))


def safe_close_session(db: Session) -> None:
    """Close a session without surfacing rollback errors on dead connections."""
    try:
        db.close()
    except (OperationalError, DBAPIError):
        try:
            db.invalidate()
        except Exception:
            pass


def ensure_db_connection(db: Session) -> None:
    """Ping and recover pooled connections after long idle periods (e.g. Meta sync)."""
    try:
        db.execute(text("SELECT 1"))
    except (OperationalError, DBAPIError):
        db.rollback()
        db.invalidate()
        db.execute(text("SELECT 1"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        safe_close_session(db)
