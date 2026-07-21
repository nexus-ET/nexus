"""Expand institution accreditation and short description limits.

Revision ID: s4t7u3v6w8x0
Revises: r3s6t2u5v7w9
"""

from alembic import op
import sqlalchemy as sa


revision = "s4t7u3v6w8x0"
down_revision = "r3s6t2u5v7w9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "institutions",
        "short_description",
        existing_type=sa.String(length=500),
        type_=sa.String(length=2500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "institutions",
        "short_description",
        existing_type=sa.String(length=2500),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
