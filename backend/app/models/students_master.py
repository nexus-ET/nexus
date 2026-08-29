from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.database import Base


class StudentsMaster(Base):
    __tablename__ = "students_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    booking_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    phone_country_iso2: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone_local: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_country_iso2_secondary: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone_local_secondary: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_number_secondary: Mapped[str | None] = mapped_column(String(50), nullable=True)

    address1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_iso2: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zipcode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    degree_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    degree_other: Mapped[str | None] = mapped_column(String(255), nullable=True)
    major: Mapped[str | None] = mapped_column(String(255), nullable=True)
    university: Mapped[str | None] = mapped_column(String(255), nullable=True)
    graduation_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpa_cgpa_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gpa_cgpa_other: Mapped[str | None] = mapped_column(String(255), nullable=True)

    target_destination_iso2: Mapped[str | None] = mapped_column(String(2), nullable=True)
    target_program_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_course_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    english_test_scores: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gre_score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gmat_score: Mapped[str | None] = mapped_column(String(50), nullable=True)

    aspirations_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    registration_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
