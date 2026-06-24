from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.database import Base


class RawIncomingLead(Base):
    """Staging table for Meta lead payloads before validation and promotion."""

    __tablename__ = "raw_incoming_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    meta_leadgen_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_by_user: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sync_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    quarantine_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
