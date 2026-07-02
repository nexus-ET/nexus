from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CounsellingNote(Base):
    __tablename__ = "counselling_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    booking_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("counselling_bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_universities: Mapped[str | None] = mapped_column(Text, nullable=True)
    scholarship_interests: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    officer_recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_follow_up: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
