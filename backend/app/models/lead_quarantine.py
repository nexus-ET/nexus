from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.database import Base


class LeadQuarantine(Base):
    """Invalid or rejected leads held for admin review and reprocessing."""

    __tablename__ = "lead_quarantine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_incoming_lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    meta_leadgen_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    original_payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    normalized_payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    error_reason: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_by_user: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reprocessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), index=True
    )
