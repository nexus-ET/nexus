"""Make education_majors.code and education_courses.code nullable.

Revision ID: y3z6a22b3c4d
Revises: x2y5z21a2b3c
Create Date: 2026-07-10 08:35:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y3z6a22b3c4d"
down_revision: Union[str, Sequence[str], None] = "x2y5z21a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "education_majors",
        "code",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "education_courses",
        "code",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE education_majors SET code = 'MAJOR_' || id::text WHERE code IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE education_courses SET code = 'COURSE_' || id::text WHERE code IS NULL"
        )
    )
    op.alter_column(
        "education_courses",
        "code",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.alter_column(
        "education_majors",
        "code",
        existing_type=sa.String(length=50),
        nullable=False,
    )
