"""Dense embedding rows for education taxonomy entities (one table per level)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.db.database import Base


class EducationSuperMajorEmbedding(Base):
    __tablename__ = "education_super_major_embeddings"
    __table_args__ = (
        UniqueConstraint("super_major_id", name="uq_education_super_major_embeddings_super_major_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    super_major_id = Column(
        Integer,
        ForeignKey("education_super_majors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = Column(ARRAY(Float), nullable=False)
    embedding_dimensions = Column(Integer, nullable=False)
    embedding_model = Column(String(120), nullable=False)
    source_text_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    super_major = relationship("EducationSuperMajor")


class EducationMajorEmbedding(Base):
    __tablename__ = "education_major_embeddings"
    __table_args__ = (
        UniqueConstraint("major_id", name="uq_education_major_embeddings_major_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    major_id = Column(
        Integer,
        ForeignKey("education_majors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = Column(ARRAY(Float), nullable=False)
    embedding_dimensions = Column(Integer, nullable=False)
    embedding_model = Column(String(120), nullable=False)
    source_text_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    major = relationship("EducationMajor")


class EducationSubMajorEmbedding(Base):
    __tablename__ = "education_sub_major_embeddings"
    __table_args__ = (
        UniqueConstraint("sub_major_id", name="uq_education_sub_major_embeddings_sub_major_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sub_major_id = Column(
        Integer,
        ForeignKey("education_sub_majors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = Column(ARRAY(Float), nullable=False)
    embedding_dimensions = Column(Integer, nullable=False)
    embedding_model = Column(String(120), nullable=False)
    source_text_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sub_major = relationship("EducationSubMajor")
