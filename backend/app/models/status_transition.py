from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TransitionType(str, enum.Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    EXPRESS = "express"
    RELAUNCH = "relaunch"


class StatusTransition(Base):
    __tablename__ = "status_transitions"
    __table_args__ = (
        UniqueConstraint(
            "from_status_id",
            "to_status_id",
            "transition_type",
            name="uq_status_transitions_from_to_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_status_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("status_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_status_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("status_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transition_type: Mapped[TransitionType] = mapped_column(
        Enum(
            TransitionType,
            name="status_transition_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        index=True,
    )
