"""Nexus Intel SQLAlchemy models."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class IntelGlossary(Base):
    __tablename__ = "intel_glossary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_name = Column(String(150), nullable=False, index=True)
    slug = Column(String(150), nullable=False, unique=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    country_code = Column(String(10), nullable=False, index=True)
    lifecycle_stage = Column(String(50), nullable=False, index=True)
    short_definition = Column(Text, nullable=False)
    full_explanation = Column(Text, nullable=True)
    key_metrics = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    official_source_url = Column(Text, nullable=True)
    is_student_facing = Column(Boolean, nullable=False, default=False)
    last_verified_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IntelTrivia(Base):
    __tablename__ = "intel_trivia"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)
    correct_option_index = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=False)
    country_code = Column(String(10), nullable=True)
    active_date = Column(Date, nullable=False, unique=True)


class IntelTriviaAnswer(Base):
    __tablename__ = "intel_trivia_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "trivia_id", name="uq_intel_trivia_answers_user_trivia"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trivia_id = Column(UUID(as_uuid=True), ForeignKey("intel_trivia.id", ondelete="CASCADE"), nullable=False)
    selected_option_index = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    answered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    trivia = relationship("IntelTrivia")


class IntelUserPreferences(Base):
    __tablename__ = "intel_user_preferences"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enable_daily_trivia = Column(Boolean, nullable=False, default=True)
    enable_contextual_tips = Column(Boolean, nullable=False, default=True)
    preferred_countries = Column(
        JSONB,
        nullable=False,
        default=lambda: ["UK", "CA", "AU", "DE", "US", "JP", "FR", "AE", "NZ", "SG", "SE", "CH"],
    )
    trivia_streak = Column(Integer, nullable=False, default=0)
    trivia_correct_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IntelScraperConfig(Base):
    __tablename__ = "intel_scraper_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String(100), nullable=False)
    target_url = Column(Text, nullable=False)
    country_code = Column(String(10), nullable=False)
    scrape_interval_hours = Column(Integer, nullable=False, default=168)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="IDLE")
    last_error = Column(Text, nullable=True)
    last_content_hash = Column(String(64), nullable=True)
    last_content_text = Column(Text, nullable=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    last_http_status = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IntelAcademyModule(Base):
    __tablename__ = "intel_academy_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False, unique=True)
    summary = Column(Text, nullable=False)
    country_code = Column(String(10), nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=5)
    quiz = Column(JSONB, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)


class IntelScrapeReview(Base):
    __tablename__ = "intel_scrape_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scraper_config_id = Column(
        UUID(as_uuid=True), ForeignKey("intel_scraper_config.id", ondelete="CASCADE"), nullable=False
    )
    glossary_id = Column(
        UUID(as_uuid=True), ForeignKey("intel_glossary.id", ondelete="SET NULL"), nullable=True
    )
    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    old_text = Column(Text, nullable=True)
    new_text = Column(Text, nullable=False)
    diff_summary = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="NEEDS_REVIEW")
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    scraper_config = relationship("IntelScraperConfig")
    glossary = relationship("IntelGlossary")


class IntelAiChatLog(Base):
    """Audit trail for Nexus Intel AI Assistant prompts and grounded answers."""

    __tablename__ = "intel_ai_chat_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)
    retrieved_sources = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
