"""add students_master registration_data column

Revision ID: ll2m3nregdata
Revises: kk1l2mbiztseq
Create Date: 2026-08-12 20:45:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ll2m3nregdata"
down_revision: Union[str, Sequence[str], None] = "kk1l2mbiztseq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("students_master"):
        return
    cols = {c["name"] for c in inspector.get_columns("students_master")}
    if "registration_data" in cols:
        return
    op.add_column(
        "students_master",
        sa.Column(
            "registration_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("students_master"):
        return
    cols = {c["name"] for c in inspector.get_columns("students_master")}
    if "registration_data" not in cols:
        return
    op.drop_column("students_master", "registration_data")
