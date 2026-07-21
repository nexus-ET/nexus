"""Add institution publish attempt status.

Revision ID: t5u8v4w7x9y1
Revises: s4t7u3v6w8x0
"""

from alembic import op
import sqlalchemy as sa


revision = "t5u8v4w7x9y1"
down_revision = "s4t7u3v6w8x0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column(
            "publish_status",
            sa.String(length=20),
            nullable=False,
            server_default="failure",
        ),
    )
    op.add_column(
        "institutions",
        sa.Column("last_publish_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "institutions",
        sa.Column("last_publish_error", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE institutions AS i
        SET publish_status = 'success',
            last_publish_attempt_at = published.latest_published_at
        FROM (
            SELECT institution_id, MAX(updated_at) AS latest_published_at
            FROM institution_wizard_drafts
            WHERE status = 'published' AND institution_id IS NOT NULL
            GROUP BY institution_id
        ) AS published
        WHERE i.id = published.institution_id
        """
    )


def downgrade() -> None:
    op.drop_column("institutions", "last_publish_error")
    op.drop_column("institutions", "last_publish_attempt_at")
    op.drop_column("institutions", "publish_status")
