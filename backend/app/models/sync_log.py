from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sync_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_by_user: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    triggered_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="IN_PROGRESS", index=True)
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    forms_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), index=True)
    attempt_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
