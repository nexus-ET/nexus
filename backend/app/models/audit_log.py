from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.database import Base

# JSONB on Postgres; generic JSON elsewhere (dev SQLite).
DetailsColumn = JSON().with_variant(JSONB, "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_resource: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(DetailsColumn, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),  # fallback only; write_audit_log sets business-local time explicitly
        index=True,
        name="created_at",
    )
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sync_mode: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success", index=True)
    # Legacy text detail retained for rows migrated from older schema.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
