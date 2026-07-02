from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class StatusDefinition(Base):
    __tablename__ = "status_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stage_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_stage_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("status_definitions.id", ondelete="SET NULL"),
        nullable=True,
    )

    next_stage = relationship(
        "StatusDefinition",
        remote_side="StatusDefinition.id",
        foreign_keys=[next_stage_id],
    )
