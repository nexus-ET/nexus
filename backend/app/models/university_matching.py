"""Phase 1 university shortlisting persistence (heuristic fit, not admit probability)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base

JsonColumn = JSON().with_variant(JSONB, "postgresql")


class MatchingWeightProfile(Base):
    __tablename__ = "matching_weight_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_academic: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_profile: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_aspirations: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    weight_safety: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MatchingShortlistRun(Base):
    __tablename__ = "matching_shortlist_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    booking_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    students_master_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("students_master.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    weight_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("matching_weight_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="phase1-v1", index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed", index=True)
    classification_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, default="heuristic_fit"
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    input_snapshot: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    weight_profile = relationship("MatchingWeightProfile")
    items = relationship(
        "MatchingShortlistItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="MatchingShortlistItem.rank",
    )


class MatchingShortlistItem(Base):
    __tablename__ = "matching_shortlist_items"
    __table_args__ = (
        UniqueConstraint("run_id", "institution_id", "offering_id", name="uq_shortlist_run_inst_offering"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matching_shortlist_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    institution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offering_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("institution_course_offerings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    consolidated_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    s_academic: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    s_profile: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    s_aspirations: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    s_safety: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    fit_band: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    explanation: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    run = relationship("MatchingShortlistRun", back_populates="items")
    institution = relationship("Institution")
    offering = relationship("InstitutionCourseOffering")
