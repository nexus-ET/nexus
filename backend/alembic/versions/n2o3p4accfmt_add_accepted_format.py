"""Add nullable accepted_format on document_requirements.

Revision ID: n2o3p4accfmt
Revises: m1n2o3doclvls
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n2o3p4accfmt"
down_revision: Union[str, Sequence[str], None] = "m1n2o3doclvls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "document_requirements" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("document_requirements")}
    if "accepted_format" not in columns:
        op.add_column(
            "document_requirements",
            sa.Column("accepted_format", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "document_requirements" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("document_requirements")}
    if "accepted_format" in columns:
        op.drop_column("document_requirements", "accepted_format")
