from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Business(Base):
    """Tenant/business profile for multi-customer deployments."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Default Business")
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    office_phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    office_mobile_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Independent flags — both office numbers may be active contacts at once.
    office_phone_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    office_mobile_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Typed contact lists: [{ "type": "Main Line", "value": "+91..." }, ...]
    office_phone_contacts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    office_email_contacts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    web_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
