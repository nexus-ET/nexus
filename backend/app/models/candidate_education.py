from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CandidateEducation(Base):
    __tablename__ = "candidate_educations"

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
    degree_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    degree_other: Mapped[str | None] = mapped_column(String(255), nullable=True)
    major: Mapped[str | None] = mapped_column(String(255), nullable=True)
    university_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    university_affiliation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    graduation_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpa_cgpa_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gpa_cgpa_other: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
