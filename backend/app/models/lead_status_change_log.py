from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.database import Base

ReasonsColumn = JSON().with_variant(JSONB, "postgresql")


class LeadStatusChangeLog(Base):
    """Audit trail for All Leads active ↔ inactive toggles."""

    __tablename__ = "lead_status_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(ReasonsColumn, nullable=False, default=list)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
