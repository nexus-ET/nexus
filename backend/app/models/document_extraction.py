"""Dynamic document extraction storage (types, documents, extracted JSONB rows).

Complements existing ``scanx_documents`` (CRM upload pipeline) with a UUID-keyed
schema for multi-type storage, flexible field groups, and spatial bounding boxes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base

_JSONB = JSON().with_variant(JSONB, "postgresql")


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_definition: Mapped[dict | None] = mapped_column(_JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="document_type",
    )


class Document(Base):
    """Parent document row (R2 path + status). ``candidate_id`` → ``leads.id``."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    candidate_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    upload_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    uploader_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="UPLOADING",
        server_default="UPLOADING",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document_type: Mapped[DocumentType] = relationship(
        "DocumentType",
        back_populates="documents",
    )
    extracted_rows: Mapped[list["ExtractedDocumentData"]] = relationship(
        "ExtractedDocumentData",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ExtractedDocumentData(Base):
    """Flexible JSONB extraction payload + optional 4-point bounding box."""

    __tablename__ = "extracted_document_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_group: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    structured_data: Mapped[dict] = mapped_column(_JSONB, nullable=False, default=dict)
    bounding_box: Mapped[list | dict | None] = mapped_column(_JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_low_confidence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    reading_order_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(
        "Document",
        back_populates="extracted_rows",
    )
