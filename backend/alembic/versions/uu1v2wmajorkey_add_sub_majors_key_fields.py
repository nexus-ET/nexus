"""Add education_majors.sub_majors_key_fields.

Revision ID: uu1v2wmajorkey
Revises: tt0u1vmajordesc
Create Date: 2026-08-21 22:05:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "uu1v2wmajorkey"
down_revision: Union[str, Sequence[str], None] = "tt0u1vmajordesc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
    if "sub_majors_key_fields" not in major_cols:
        op.add_column(
            "education_majors",
            sa.Column("sub_majors_key_fields", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
    if "sub_majors_key_fields" in major_cols:
        op.drop_column("education_majors", "sub_majors_key_fields")
