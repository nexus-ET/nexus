"""Add college_id and storage_key to institution_pictures for shared assets.

Revision ID: u6v9w2x76y8z
Revises: t5u8v4w7x9y1
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u6v9w2x76y8z"
down_revision = "t5u8v4w7x9y1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "institution_pictures",
        sa.Column("college_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_pictures",
        sa.Column("storage_key", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_institution_pictures_college_id",
        "institution_pictures",
        ["college_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_pictures_storage_key",
        "institution_pictures",
        ["storage_key"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_institution_pictures_college_id",
        "institution_pictures",
        "colleges",
        ["college_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_institution_pictures_college_id",
        "institution_pictures",
        type_="foreignkey",
    )
    op.drop_index("ix_institution_pictures_storage_key", table_name="institution_pictures")
    op.drop_index("ix_institution_pictures_college_id", table_name="institution_pictures")
    op.drop_column("institution_pictures", "storage_key")
    op.drop_column("institution_pictures", "college_id")
