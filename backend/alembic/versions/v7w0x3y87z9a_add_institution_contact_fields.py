"""Add address and contact fields to institutions.

Revision ID: v7w0x3y87z9a
Revises: u6v9w2x76y8z
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "v7w0x3y87z9a"
down_revision = "u6v9w2x76y8z"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutions", sa.Column("address", sa.String(length=200), nullable=True))
    op.add_column("institutions", sa.Column("phone_numbers", sa.JSON(), nullable=True))
    op.add_column("institutions", sa.Column("fax_number", sa.String(length=50), nullable=True))
    op.add_column("institutions", sa.Column("email_addresses", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE institutions
        SET phone_numbers = '[]'::json,
            email_addresses = '[]'::json
        WHERE phone_numbers IS NULL OR email_addresses IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("institutions", "email_addresses")
    op.drop_column("institutions", "fax_number")
    op.drop_column("institutions", "phone_numbers")
    op.drop_column("institutions", "address")
