from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CandidateTestScore(Base):
    __tablename__ = "candidate_test_scores"

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
    test_name: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    section_name: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    score_report_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
