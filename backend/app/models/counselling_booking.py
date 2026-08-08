from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CounsellingBooking(Base):
    __tablename__ = "counselling_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lead_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    admin_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_key: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    wrap_up_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sub-process 1.1 counselor workspace (academic / english / gap / goals / financial).
    intake_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
