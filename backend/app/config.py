from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "NEXUS"
    PROJECT_TAGLINE: str = "AI-Powered Client Growth Tool"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Database connection string
    DATABASE_URL: str = "sqlite:///./nexus.db"

    # WARNING: In production, these should be loaded from environment variables
    SECRET_KEY: str = "YOUR_SUPER_SECRET_KEY_CHANGE_ME"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True

    WHATSAPP_ACCESS_TOKEN: str | None = None
    # Optional explicit override; otherwise chosen from test/business IDs below.
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: str | None = None
    # Meta test sandbox line (+1 555-665-6397) — local development only
    WHATSAPP_TEST_PHONE_NUMBER: str | None = None
    WHATSAPP_TEST_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_TEST_WABA_ID: str | None = None
    # Edutrust business line (+91 74119 52525) — staging / nexus-dev server
    WHATSAPP_BUSINESS_PHONE_NUMBER: str | None = None
    WHATSAPP_BUSINESS_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_BUSINESS_WABA_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: str | None = None
    # Meta template sent before business-initiated outreach (opens the 24h window). Leave unset to skip.
    WHATSAPP_OUTREACH_TEMPLATE: str | None = "et_student_welcome"
    # Must match the language shown in Meta Business Manager for that template (English = en, English US = en_US).
    WHATSAPP_OUTREACH_TEMPLATE_LANGUAGE: str = "en"
    # {{1}} student name and {{2}} company name for Utility outreach templates such as et_student_welcome.
    WHATSAPP_OUTREACH_COMPANY_NAME: str = "Edutrust"
    # Brief pause after template delivery if webhook status is unavailable.
    WHATSAPP_OUTREACH_FOLLOWUP_DELAY_SECONDS: float = 12.0
    # Max seconds to wait for Meta sent/delivered webhook before fallback delay.
    WHATSAPP_OUTREACH_DELIVERY_WAIT_SECONDS: float = 15.0
    # Pause after template delivery webhook before sending session follow-up text.
    WHATSAPP_OUTREACH_POST_TEMPLATE_DELAY_SECONDS: float = 5.0
    # Pause when template delivery webhook never arrives (needs longer for Meta window).
    WHATSAPP_OUTREACH_UNCONFIRMED_TEMPLATE_DELAY_SECONDS: float = 18.0
    # Max seconds to wait for follow-up message delivery webhook before retry.
    WHATSAPP_OUTREACH_FOLLOWUP_DELIVERY_WAIT_SECONDS: float = 20.0
    # Second Meta template for the intake prompt (recommended — session text often does not deliver).
    WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE: str | None = None
    WHATSAPP_OUTREACH_FOLLOWUP_TEMPLATE_LANGUAGE: str | None = None
    # When true, skip any second WhatsApp send after the welcome template.
    # Default true: welcome only; student hi/hello starts intake questions.
    WHATSAPP_OUTREACH_SKIP_INTAKE_FOLLOWUP: bool = True
    # When true, refuse session-text fallback — require follow-up template or skip flag above.
    WHATSAPP_OUTREACH_REQUIRE_FOLLOWUP_TEMPLATE: bool = False
    # Comma-separated body placeholders to send: student, company. Empty = no parameters (static template).
    WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS: str = "student,company"
    # named = Meta {{student_name}} style (requires parameter_name in API); positional = {{1}}, {{2}}.
    WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_FORMAT: str = "positional"
    # Meta parameter names matching WHATSAPP_OUTREACH_TEMPLATE_PARAMETERS order (Student Name, Company Name).
    WHATSAPP_OUTREACH_TEMPLATE_PARAMETER_NAMES: str = "student_name,company_name"
    WEBHOOK_VERIFY_TOKEN: str | None = None
    # Public base URL for this deployment (local quick tunnel or https://nexus-dev.edutrust.in)
    PUBLIC_TUNNEL_BASE: str | None = None
    # Instance label: development | nexus-dev | production
    NEXUS_INSTANCE: str | None = None
    ENVIRONMENT: str | None = None
    # Auto-register Meta WABA webhook to PUBLIC_TUNNEL_BASE on dev start / deploy
    NEXUS_WHATSAPP_AUTO_SYNC: bool = True
    # When local dev stops, hand webhook back to this base URL (e.g. nexus-dev server)
    NEXUS_WHATSAPP_HANDOFF_URL: str | None = None
    # Meta Graph API token for Lead Ads retrieval (falls back to WHATSAPP_ACCESS_TOKEN)
    META_GRAPH_ACCESS_TOKEN: str | None = None
    # Facebook Page ID for historical Meta Lead Ads backfill (Page Access Token required)
    META_PAGE_ID: str | None = None
    # Automated Meta lead sync scheduler (interval from Settings, not .env)
    META_LEAD_SYNC_ENABLED: bool = True
    # Outbound/inbound messaging provider: TWILIO (default) or WHATSAPP (Meta Cloud API)
    PROVIDER: str = "TWILIO"
    OPENAI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    OLLAMA_TIMEOUT_SECONDS: int = 120
    # When true: WhatsApp AI Active uses fixed intake templates + appointment booking only (no LLM/Ollama/API keys).
    NEXUS_APPOINTMENTS_ONLY: bool = True

    WHATSAPP_FLOW_ID: str | None = None
    WHATSAPP_FLOW_PRIVATE_KEY: str | None = None
    WHATSAPP_FLOW_PRIVATE_KEY_PATH: str | None = None
    FRONTEND_URL: str | None = None

    REDIS_URL: str | None = None
    RATE_LIMIT_GLOBAL: str = "60/minute"
    RATE_LIMIT_STRICT: str = "5/minute"

    FIREBASE_CREDENTIALS_PATH: str | None = None
    FIREBASE_CREDENTIALS_JSON: str | None = None
    FIREBASE_PROJECT_ID: str | None = None

    APP_TIMEZONE: str = "UTC"

    SECURITY_AUDIT_ENABLED: bool = True
    SECURITY_AUDIT_CRON_HOUR: int = 2
    # Outbound red-flag alerts (WhatsApp/email/push to super admins). Audit runs still log failures.
    SECURITY_AUDIT_RED_ALERTS_ENABLED: bool = True
    SECURITY_AUDIT_ALERT_WHATSAPP_ENABLED: bool = True
    # When true, scheduled failures are logged only — manual "Run audit" still sends alerts.
    SECURITY_AUDIT_ALERT_MANUAL_ONLY: bool = False

    # Process-level kill switch for the uptime monitoring scheduler (DB MONITORING_STATUS still gates each run).
    MONITORING_CHECK_ENABLED: bool = True
    MONITORING_CHECK_INTERVAL_MINUTES: int = 5

    # Max pending + scheduled counselling appointments allowed at the same time slot
    MAX_COUNSELLING_BOOKINGS_PER_SLOT: int = 5

    # Max characters per chat message (team chat + internal messaging)
    CHAT_MAX_CHARS: int = 500

    # Cloudflare R2 (S3-compatible) for institution logos, banners, and gallery images
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str | None = None
    # Public CDN/custom domain base, e.g. https://assets.example.com (no trailing slash)
    R2_PUBLIC_BASE_URL: str | None = None
    R2_ENDPOINT_URL: str | None = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()