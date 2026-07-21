"""Allow colleges to remain unlinked from a campus.

Revision ID: g2h5i1j4k5l6
Revises: f1g4h0i3j4k5
Create Date: 2026-07-12 11:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g2h5i1j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f1g4h0i3j4k5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "colleges",
        "campus_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    unlinked_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM colleges WHERE campus_id IS NULL")
    ).scalar_one()
    if unlinked_count:
        raise RuntimeError(
            "Cannot make colleges.campus_id non-nullable while unlinked colleges exist."
        )
    op.alter_column(
        "colleges",
        "campus_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
