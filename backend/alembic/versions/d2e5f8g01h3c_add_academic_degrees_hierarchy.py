"""add academic degrees and link programs to degrees

Revision ID: d2e5f8g01h3c
Revises: c1d4e7f90g2b
Create Date: 2026-07-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e5f8g01h3c"
down_revision: Union[str, Sequence[str], None] = "c1d4e7f90g2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "academic_degrees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_academic_degrees_id", "academic_degrees", ["id"])
    op.create_index("ix_academic_degrees_code", "academic_degrees", ["code"], unique=True)
    op.create_index("ix_academic_degrees_name", "academic_degrees", ["name"])

    op.add_column(
        "target_programs",
        sa.Column("degree_id", sa.Integer(), sa.ForeignKey("academic_degrees.id"), nullable=True),
    )
    op.create_index("ix_target_programs_degree_id", "target_programs", ["degree_id"])

    degrees = sa.table(
        "academic_degrees",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        degrees,
        [
            {"code": "BACHELOR", "name": "Bachelor", "sort_order": 1},
            {"code": "MASTER", "name": "Master", "sort_order": 2},
            {"code": "PHD", "name": "PhD", "sort_order": 3},
            {"code": "CERTIFICATE", "name": "Certificate", "sort_order": 4},
        ],
    )

    op.execute(
        """
        UPDATE target_programs
        SET degree_id = (SELECT id FROM academic_degrees WHERE code = 'MASTER' LIMIT 1)
        WHERE degree_id IS NULL
        """
    )
    op.alter_column("target_programs", "degree_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_target_programs_degree_id", table_name="target_programs")
    op.drop_column("target_programs", "degree_id")
    op.drop_index("ix_academic_degrees_name", table_name="academic_degrees")
    op.drop_index("ix_academic_degrees_code", table_name="academic_degrees")
    op.drop_index("ix_academic_degrees_id", table_name="academic_degrees")
    op.drop_table("academic_degrees")
