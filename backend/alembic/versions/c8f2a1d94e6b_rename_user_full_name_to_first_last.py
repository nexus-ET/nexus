"""rename user full_name to first_name and last_name

Revision ID: c8f2a1d94e6b
Revises: b7d070216c32
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f2a1d94e6b"
down_revision: Union[str, Sequence[str], None] = "b7d070216c32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE users
        SET first_name = CASE
                WHEN full_name IS NULL OR btrim(full_name) = '' THEN NULL
                WHEN strpos(btrim(full_name), ' ') > 0 THEN split_part(btrim(full_name), ' ', 1)
                ELSE btrim(full_name)
            END,
            last_name = CASE
                WHEN full_name IS NULL OR btrim(full_name) = '' THEN NULL
                WHEN strpos(btrim(full_name), ' ') > 0 THEN btrim(substring(btrim(full_name) from strpos(btrim(full_name), ' ') + 1))
                ELSE NULL
            END
        """
    )

    op.drop_column("users", "full_name")


def downgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE users
        SET full_name = NULLIF(btrim(concat_ws(' ', first_name, last_name)), '')
        """
    )

    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
