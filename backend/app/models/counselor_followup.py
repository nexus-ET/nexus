from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

JsonColumn = JSON().with_variant(JSONB, "postgresql")


class CounselorStatusMaster(Base):
    """Lookup of counselor follow-up status options and default note templates."""

    __tablename__ = "counselor_status_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    status_heading: Mapped[str] = mapped_column(String(160), nullable=False)
    default_description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    followups: Mapped[list["CounselorFollowupLog"]] = relationship(
        "CounselorFollowupLog",
        back_populates="status",
    )


class CounselorFollowupLog(Base):
    """Chronological counselor interaction notes for a lead."""

    __tablename__ = "counselor_followup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    counselor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("counselor_status_master.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    points_discussed: Mapped[str] = mapped_column(Text, nullable=False)
    action_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    checklist_email_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checklist_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    checklist_sent_documents: Mapped[list | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    status: Mapped[CounselorStatusMaster] = relationship(
        "CounselorStatusMaster",
        back_populates="followups",
    )
