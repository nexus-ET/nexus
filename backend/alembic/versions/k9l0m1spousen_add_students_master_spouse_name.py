"""Add spouse_name to students_master for passport OCR sync.

Revision ID: k9l0m1spousen
Revises: j8k9l0scxfix
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k9l0m1spousen"
down_revision: Union[str, Sequence[str], None] = "j8k9l0scxfix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "students_master" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("students_master")}
    if "spouse_name" not in cols:
        op.add_column(
            "students_master",
            sa.Column("spouse_name", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "students_master" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("students_master")}
    if "spouse_name" in cols:
        op.drop_column("students_master", "spouse_name")
