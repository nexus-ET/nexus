"""ScanX CRM document models (v1)."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.db.database import Base


class ScanxDocument(Base):
    __tablename__ = "scanx_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    lead_id = Column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploader_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    booking_id = Column(Integer, nullable=True, index=True)
    source = Column(String(32), nullable=False, default="crm", index=True)
    document_type_id = Column(String(64), nullable=False, index=True)
    subfolder = Column(String(64), nullable=False)
    original_filename = Column(String(512), nullable=False)
    r2_key = Column(String(1024), nullable=True)
    content_sha256 = Column(String(64), nullable=True, index=True)
    content_type = Column(String(128), nullable=True)
    byte_size = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="uploading", index=True)
    extracted_text = Column(Text, nullable=True)
    # Heuristic category panels (identity, contact, academic, …) from OCR/text.
    extracted_fields_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    metrics_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    upload_id = Column(String(64), nullable=True, index=True)
    # Shared id when multiple image files form one logical document (e.g. passport p1+p2).
    document_group_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Ordered member assets: [{page_index, r2_key, original_filename, content_type, byte_size}, …]
    source_pages = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error_code = Column(String(16), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    chunks = relationship(
        "ScanxDocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ScanxDocumentChunk(Base):
    """Chunk + embedding for a ScanX document (not taxonomy tables)."""

    __tablename__ = "scanx_document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_scanx_document_chunks_document_chunk",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer,
        ForeignKey("scanx_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(ARRAY(Float), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    embedding_model = Column(String(120), nullable=True)
    source_text_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("ScanxDocument", back_populates="chunks")
