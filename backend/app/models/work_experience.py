from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class WorkExperience(Base):
    __tablename__ = "work_experiences"

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
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    projects: Mapped[list["WorkProject"]] = relationship(
        "WorkProject",
        back_populates="work_experience",
        cascade="all, delete-orphan",
        order_by="WorkProject.sort_order",
    )


class WorkProject(Base):
    __tablename__ = "work_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_experience_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("work_experiences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    work_experience: Mapped[WorkExperience] = relationship(
        "WorkExperience",
        back_populates="projects",
    )
