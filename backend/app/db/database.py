from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from app.config import settings


def _engine_pool_recycle(database_url: str) -> int:
    if database_url.startswith("sqlite"):
        return 1800
    # Neon/serverless Postgres terminates idle connections; recycle before that.
    return 300


engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=_engine_pool_recycle(settings.DATABASE_URL),
    pool_pre_ping=True,
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


def sync_schema_columns() -> None:
    """Add or rename columns that create_all() cannot backfill on existing tables."""
    inspector = inspect(engine)

    if inspector.has_table("leads"):
        lead_columns = {column["name"] for column in inspector.get_columns("leads")}
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
        lead_columns = {column["name"] for column in inspector.get_columns("leads")}
        with engine.begin() as conn:
            for column_name, column_type in intake_columns.items():
                if column_name not in lead_columns:
                    conn.execute(
                        text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
                    )

    if not inspector.has_table("users"):
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}

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
            _column_type_name(inspector, "users", "deactivation_reason")
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
            _column_type_name(inspector, "users", "role")
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

    inspector = inspect(engine)

    if inspector.has_table("navigation_pages"):
        nav_columns = {column["name"] for column in inspector.get_columns("navigation_pages")}
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

    if inspector.has_table("role_page_permissions"):
        perm_columns = {column["name"] for column in inspector.get_columns("role_page_permissions")}
        required_perm_columns = {"admin_role_id", "navigation_page_id", "can_access"}
        if not required_perm_columns.issubset(perm_columns):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS role_page_permissions"))

    inspector = inspect(engine)
    if not inspector.has_table("role_page_permissions"):
        from app.models.role_page_permission import RolePagePermission

        RolePagePermission.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)

    if inspector.has_table("counselling_bookings"):
        booking_columns = {column["name"] for column in inspector.get_columns("counselling_bookings")}
        with engine.begin() as conn:
            if "scheduled_time" not in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ADD COLUMN scheduled_time TIMESTAMP")
                )
                if "slot_id" in booking_columns and inspector.has_table("counselling_slots"):
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

    inspector = inspect(engine)
    if inspector.has_table("dynamic_settings"):
        setting_columns = {column["name"] for column in inspector.get_columns("dynamic_settings")}
        with engine.begin() as conn:
            if "updated_by_user_id" not in setting_columns:
                conn.execute(
                    text(
                        "ALTER TABLE dynamic_settings ADD COLUMN updated_by_user_id INTEGER "
                        "REFERENCES users(id) ON DELETE SET NULL"
                    )
                )

    inspector = inspect(engine)
    if inspector.has_table("notification_logs"):
        log_columns = {column["name"] for column in inspector.get_columns("notification_logs")}
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
            booking_col = next(
                (column for column in inspector.get_columns("notification_logs") if column["name"] == "booking_id"),
                None,
            )
            if booking_col and not booking_col.get("nullable", True):
                if engine.dialect.name == "postgresql":
                    conn.execute(text("ALTER TABLE notification_logs ALTER COLUMN booking_id DROP NOT NULL"))

    inspector = inspect(engine)
    if inspector.has_table("users"):
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "fcm_tokens" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN fcm_tokens TEXT"))

    if not inspector.has_table("businesses"):
        from app.models.business import Business

        Business.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    if inspector.has_table("businesses"):
        business_columns = {column["name"] for column in inspector.get_columns("businesses")}
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
        }
        with engine.begin() as conn:
            for column_name, column_type in address_columns.items():
                if column_name not in business_columns:
                    conn.execute(
                        text(f"ALTER TABLE businesses ADD COLUMN {column_name} {column_type}")
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

    inspector = inspect(engine)
    if inspector.has_table("users") and inspector.has_table("businesses"):
        user_columns = {column["name"] for column in inspector.get_columns("users")}
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

    inspector = inspect(engine)
    if not inspector.has_table("security_audit_runs"):
        from app.models.security_audit_run import SecurityAuditRun

        SecurityAuditRun.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("sync_logs"):
        from app.models.sync_log import SyncLog

        SyncLog.__table__.create(bind=engine, checkfirst=True)
    elif inspector.has_table("sync_logs"):
        sync_log_columns = {column["name"] for column in inspector.get_columns("sync_logs")}
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

    inspector = inspect(engine)
    if inspector.has_table("leads"):
        lead_columns = {column["name"] for column in inspector.get_columns("leads")}
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

    if inspector.has_table("counselling_bookings"):
        booking_columns = {column["name"] for column in inspector.get_columns("counselling_bookings")}
        with engine.begin() as conn:
            if "outcome_key" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN outcome_key VARCHAR(50)"))
            if "wrap_up_notes" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN wrap_up_notes TEXT"))
            if "completed_at" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN completed_at TIMESTAMP"))

    if not inspector.has_table("admission_history"):
        from app.models.admission_history import AdmissionHistory

        AdmissionHistory.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("candidate_tasks"):
        from app.models.candidate_task import CandidateTask

        CandidateTask.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("conversations"):
        from app.models.conversation import Conversation

        Conversation.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("conversation_participants"):
        from app.models.conversation_participant import ConversationParticipant

        ConversationParticipant.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("internal_messages"):
        from app.models.internal_message import InternalMessage

        InternalMessage.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("counselling_notes"):
        from app.models.counselling_note import CounsellingNote

        CounsellingNote.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("status_definitions"):
        from app.models.status_definition import StatusDefinition

        StatusDefinition.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("status_history"):
        from app.models.status_history import StatusHistory

        StatusHistory.__table__.create(bind=engine, checkfirst=True)

    if not inspector.has_table("system_logs"):
        from app.models.system_log import SystemLog

        SystemLog.__table__.create(bind=engine, checkfirst=True)

    if inspector.has_table("leads"):
        lead_columns = {column["name"] for column in inspector.get_columns("leads")}
        with engine.begin() as conn:
            if "status_definition_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_definition_id INTEGER"))
            if "status_entered_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_entered_at TIMESTAMP"))

    if inspector.has_table("internal_messages"):
        message_columns = {column["name"] for column in inspector.get_columns("internal_messages")}
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

    if not inspector.has_table("message_reactions"):
        from app.models.message_reaction import MessageReaction

        MessageReaction.__table__.create(bind=engine, checkfirst=True)


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
