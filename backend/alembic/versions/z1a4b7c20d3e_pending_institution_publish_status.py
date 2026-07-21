"""Default institution publish status to pending until first attempt.

Revision ID: z1a4b7c20d3e
Revises: y0z3a6b10c2d
"""

from alembic import op
import sqlalchemy as sa


revision = "z1a4b7c20d3e"
down_revision = "y0z3a6b10c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "institutions",
        "publish_status",
        existing_type=sa.String(length=20),
        server_default="pending",
        existing_nullable=False,
    )
    # Never-attempted publishes were stored as failure; treat those as pending.
    op.execute(
        """
        UPDATE institutions
        SET publish_status = 'pending'
        WHERE last_publish_attempt_at IS NULL
          AND publish_status = 'failure'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE institutions
        SET publish_status = 'failure'
        WHERE last_publish_attempt_at IS NULL
          AND publish_status = 'pending'
        """
    )
    op.alter_column(
        "institutions",
        "publish_status",
        existing_type=sa.String(length=20),
        server_default="failure",
        existing_nullable=False,
    )
