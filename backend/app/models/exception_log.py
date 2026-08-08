from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ExceptionLog(Base):
    """Operational errors, exceptions, and omissions for the Insights Exception Report."""

    __tablename__ = "exception_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # EXCEPTION | ERROR | WARNING | OMISSION
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # meta_lead_sync | api_client | backend | scheduler | webhook | other
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="backend", index=True)
    # Free-form category shown like sync "mode" / domain bucket
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="general", index=True)
    # OPEN | ACKNOWLEDGED | RESOLVED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    triggered_by_user: Mapped[str] = mapped_column(String(255), nullable=False, default="SYSTEM", index=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    page_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    related_resource: Mapped[str | None] = mapped_column(String(100), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # How the issue was fixed — required when status is RESOLVED
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
