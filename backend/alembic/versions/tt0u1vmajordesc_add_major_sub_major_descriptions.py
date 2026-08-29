"""Rename education_majors.description → major_description; add sub_major_description.

Revision ID: tt0u1vmajordesc
Revises: ss9t0uinsttypes
Create Date: 2026-08-21 20:50:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "tt0u1vmajordesc"
down_revision: Union[str, Sequence[str], None] = "ss9t0uinsttypes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
    if "description" in major_cols and "major_description" not in major_cols:
        op.alter_column(
            "education_majors",
            "description",
            new_column_name="major_description",
            existing_type=sa.Text(),
            existing_nullable=True,
        )
    elif "major_description" not in major_cols:
        op.add_column(
            "education_majors",
            sa.Column("major_description", sa.Text(), nullable=True),
        )

    sub_cols = {c["name"] for c in inspector.get_columns("education_sub_majors")}
    if "sub_major_description" not in sub_cols:
        op.add_column(
            "education_sub_majors",
            sa.Column("sub_major_description", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    sub_cols = {c["name"] for c in inspector.get_columns("education_sub_majors")}
    if "sub_major_description" in sub_cols:
        op.drop_column("education_sub_majors", "sub_major_description")

    major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
    if "major_description" in major_cols and "description" not in major_cols:
        op.alter_column(
            "education_majors",
            "major_description",
            new_column_name="description",
            existing_type=sa.Text(),
            existing_nullable=True,
        )
    elif "major_description" in major_cols:
        op.drop_column("education_majors", "major_description")
