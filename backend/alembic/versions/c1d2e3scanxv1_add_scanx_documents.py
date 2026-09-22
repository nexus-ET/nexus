"""Add ScanX CRM document + chunk embedding tables.

Revision ID: c1d2e3scanxv1
Revises: b0c1d2taxembed
Create Date: 2026-09-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3scanxv1"
down_revision: Union[str, Sequence[str], None] = "b0c1d2taxembed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scanx_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("uploader_user_id", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="crm"),
        sa.Column("document_type_id", sa.String(length=64), nullable=False),
        sa.Column("subfolder", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("r2_key", sa.String(length=1024), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "metrics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("upload_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("doc_uuid", name="uq_scanx_documents_doc_uuid"),
    )
    op.create_index("ix_scanx_documents_doc_uuid", "scanx_documents", ["doc_uuid"])
    op.create_index("ix_scanx_documents_lead_id", "scanx_documents", ["lead_id"])
    op.create_index(
        "ix_scanx_documents_uploader_user_id",
        "scanx_documents",
        ["uploader_user_id"],
    )
    op.create_index("ix_scanx_documents_booking_id", "scanx_documents", ["booking_id"])
    op.create_index("ix_scanx_documents_source", "scanx_documents", ["source"])
    op.create_index(
        "ix_scanx_documents_document_type_id",
        "scanx_documents",
        ["document_type_id"],
    )
    op.create_index("ix_scanx_documents_status", "scanx_documents", ["status"])
    op.create_index(
        "ix_scanx_documents_content_sha256",
        "scanx_documents",
        ["content_sha256"],
    )
    op.create_index("ix_scanx_documents_upload_id", "scanx_documents", ["upload_id"])

    op.create_table(
        "scanx_document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("source_text_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["scanx_documents.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_scanx_document_chunks_document_chunk",
        ),
    )
    op.create_index(
        "ix_scanx_document_chunks_document_id",
        "scanx_document_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_scanx_document_chunks_source_text_hash",
        "scanx_document_chunks",
        ["source_text_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scanx_document_chunks_source_text_hash",
        table_name="scanx_document_chunks",
    )
    op.drop_index(
        "ix_scanx_document_chunks_document_id",
        table_name="scanx_document_chunks",
    )
    op.drop_table("scanx_document_chunks")
    op.drop_index("ix_scanx_documents_upload_id", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_content_sha256", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_status", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_document_type_id", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_source", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_booking_id", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_uploader_user_id", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_lead_id", table_name="scanx_documents")
    op.drop_index("ix_scanx_documents_doc_uuid", table_name="scanx_documents")
    op.drop_table("scanx_documents")
