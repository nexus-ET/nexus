from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class NonAcademicActivity(Base):
    __tablename__ = "non_academic_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    booking_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    activity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_or_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
