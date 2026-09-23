from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

document_requirement_countries = Table(
    "document_requirement_countries",
    Base.metadata,
    Column(
        "requirement_id",
        Integer,
        ForeignKey("document_requirements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "country_id",
        Integer,
        ForeignKey("countries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_name: Mapped[str] = mapped_column(String(150), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )


class DocumentRequirementLevel(Base):
    __tablename__ = "document_requirement_levels"

    requirement_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_requirements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    program_level: Mapped[str] = mapped_column(String(50), primary_key=True)


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("document_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    template = relationship("DocumentTemplate", foreign_keys=[template_id])
    countries = relationship(
        "Country",
        secondary=document_requirement_countries,
        lazy="selectin",
    )
    level_rows = relationship(
        DocumentRequirementLevel,
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by=DocumentRequirementLevel.program_level,
    )
