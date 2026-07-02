from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ChangedByType(str, enum.Enum):
    SYSTEM = "system"
    ADMIN = "admin"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("status_definitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    changed_by_type: Mapped[ChangedByType] = mapped_column(
        Enum(
            ChangedByType,
            values_callable=_enum_values,
            name="status_changed_by_type",
            native_enum=False,
        ),
        nullable=False,
        index=True,
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
