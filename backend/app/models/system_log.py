from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SystemLogLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    level: Mapped[SystemLogLevel] = mapped_column(
        Enum(
            SystemLogLevel,
            values_callable=_enum_values,
            name="system_log_level",
            native_enum=False,
        ),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
