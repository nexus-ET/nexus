import enum
from datetime import datetime
from typing import TYPE_CHECKING  # 👈 Added to safely guard cross-model imports
from sqlalchemy import String, Integer, Float, DateTime, Enum, Text, Boolean, func, cast, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session, synonym
from sqlalchemy.types import JSON
from app.db.database import Base 

# 🛡️ THE RELATIONSHIP RESOLVER SHIELD:
# This lets SQLAlchemy see the Message model for typing without triggering 
# a classic "Circular Import Dependency" crash at app boot time.
if TYPE_CHECKING:
    from app.models.message import Message

class LeadStage(str, enum.Enum):
    AI_ACTIVE = "AI_ACTIVE"         
    HANDOFF = "HANDOFF"             
    ARCHIVE = "ARCHIVE"             

class LeadChannel(str, enum.Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    GOOGLE_ADS = "GOOGLE_ADS"
    OFFLINE = "OFFLINE"


class LeadSource(str, enum.Enum):
    FACEBOOK_LEAD = "FACEBOOK_LEAD"
    INSTAGRAM_LEAD = "INSTAGRAM_LEAD"

class Lead(Base):
    __tablename__ = "leads"

    # Core Identifiers
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=True)
    
    # Ingestion Metadata
    channel: Mapped[LeadChannel] = mapped_column(Enum(LeadChannel), default=LeadChannel.WHATSAPP)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # Meta Lead Ads identifier — unique at DB level (partial index on PostgreSQL).
    meta_leadgen_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    # Product-facing alias for meta_leadgen_id (same column, used in webhooks/API payloads).
    leadgen_id = synonym("meta_leadgen_id")
    meta_campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_form_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    additional_data: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    stage: Mapped[LeadStage] = mapped_column(Enum(LeadStage), default=LeadStage.AI_ACTIVE)
    is_human_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_advisor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Extracted Intelligence Profile
    preferred_country: Mapped[str] = mapped_column(String(100), nullable=True)
    budget_tier: Mapped[str] = mapped_column(String(50), nullable=True)
    test_scores: Mapped[str] = mapped_column(String(100), nullable=True)
    academic_summary: Mapped[str] = mapped_column(Text, nullable=True)
    intake_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    english_test_scores: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gre_score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gmat_score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wants_consultation_call: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    consultation_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    intake_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Machine Learning Core Outputs
    ml_conversion_score: Mapped[float] = mapped_column(Float, default=0.0) 
    ai_post_mortem: Mapped[str] = mapped_column(Text, nullable=True) 

    # Operations & Documents
    calendar_booking_id: Mapped[str] = mapped_column(String(255), nullable=True) 
    audit_report_url: Mapped[str] = mapped_column(String(512), nullable=True) 
    resolution_reason: Mapped[str] = mapped_column(String(255), nullable=True) 

    admission_stage: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    admission_stage_entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    documents_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Live Messaging Relationship Engine
    # 🔥 FIXED: Using native lowercase list[...] notation natively supported by 
    # SQLAlchemy 2.0 maps relations flawlessly into object matrices.
    messages: Mapped[list["Message"]] = relationship(
        "Message", 
        back_populates="lead", 
        cascade="all, delete-orphan"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    archived_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


def get_dashboard_metrics(db: Session) -> dict:
    """
    Compute dashboard KPI counts from the Lead schema in a single query.

    Requested logic is mapped to existing columns as follows:
    - pending_consultation  -> stage HANDOFF and not yet human-locked
    - needs_escalation      -> is_human_locked is True
    - consultation_complete + audit_completed=False -> stage HANDOFF and audit_report_url is NULL
    - active session status -> stage AI_ACTIVE and not human-locked
    """
    handoff_stage = cast(Lead.stage, String).ilike("%HANDOFF%")
    ai_active_stage = cast(Lead.stage, String).ilike("%AI_ACTIVE%")

    row = db.query(
        func.count()
        .filter(handoff_stage, Lead.is_human_locked.is_(False))
        .label("awaiting_consultation"),
        func.count()
        .filter(Lead.is_human_locked.is_(True))
        .label("escalation_queue"),
        func.count()
        .filter(handoff_stage, Lead.audit_report_url.is_(None))
        .label("missing_post_audit"),
        func.count()
        .filter(
            ai_active_stage,
            cast(Lead.stage, String).not_ilike("%HANDOFF%"),
            Lead.is_human_locked.is_(False),
        )
        .label("active_ai_chats"),
    ).one()

    return {
        "awaiting_consultation": int(row.awaiting_consultation or 0),
        "escalation_queue": int(row.escalation_queue or 0),
        "missing_post_audit": int(row.missing_post_audit or 0),
        "active_ai_chats": int(row.active_ai_chats or 0),
    }