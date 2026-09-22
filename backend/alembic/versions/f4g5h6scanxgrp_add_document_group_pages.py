"""Add ScanX document_group_id + source_pages for multi-image groups.

Revision ID: f4g5h6scanxgrp
Revises: e3f4g5scanxdyn
Create Date: 2026-09-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4g5h6scanxgrp"
down_revision: Union[str, Sequence[str], None] = "e3f4g5scanxdyn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scanx_documents",
        sa.Column("document_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_scanx_documents_document_group_id",
        "scanx_documents",
        ["document_group_id"],
    )
    op.add_column(
        "scanx_documents",
        sa.Column(
            "source_pages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scanx_documents", "source_pages")
    op.drop_index("ix_scanx_documents_document_group_id", table_name="scanx_documents")
    op.drop_column("scanx_documents", "document_group_id")
