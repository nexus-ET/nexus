"""Add extracted_fields_json to scanx_documents for OCR category panels.

Revision ID: d2e3f4scanxcat
Revises: c1d2e3scanxv1
Create Date: 2026-09-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2e3f4scanxcat"
down_revision: Union[str, Sequence[str], None] = "c1d2e3scanxv1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scanx_documents",
        sa.Column(
            "extracted_fields_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scanx_documents", "extracted_fields_json")
