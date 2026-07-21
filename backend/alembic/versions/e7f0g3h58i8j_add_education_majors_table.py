"""add education_majors table

Revision ID: e7f0g3h58i8j
Revises: d6e9f2g47h7i
Create Date: 2026-07-06 26:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f0g3h58i8j"
down_revision: Union[str, Sequence[str], None] = "d6e9f2g47h7i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EDUCATION_MAJORS: list[tuple[str, str, int, bool]] = [
    ("COMPUTER_SCIENCE", "Computer Science", 1, False),
    ("BUSINESS_ADMINISTRATION", "Business Administration", 2, False),
    ("ENGINEERING", "Engineering", 3, False),
    ("MEDICINE", "Medicine", 4, False),
    ("DATA_SCIENCE", "Data Science", 5, False),
    ("FINANCE", "Finance", 6, False),
    ("LAW", "Law", 7, False),
    ("ARCHITECTURE", "Architecture", 8, False),
    ("PSYCHOLOGY", "Psychology", 9, False),
    ("BIOTECHNOLOGY", "Biotechnology", 10, False),
    ("OTHER", "Other", 99, True),
]


def _upsert_majors(majors: list[tuple[str, str, int, bool]]) -> None:
    connection = op.get_bind()
    for code, label, sort_order, is_other in majors:
        connection.execute(
            sa.text(
                """
                INSERT INTO education_majors (code, label, sort_order, is_other, is_active)
                VALUES (:code, :label, :sort_order, :is_other, true)
                ON CONFLICT (code) DO UPDATE SET
                    label = EXCLUDED.label,
                    sort_order = EXCLUDED.sort_order,
                    is_other = EXCLUDED.is_other,
                    is_active = true
                """
            ),
            {
                "code": code,
                "label": label,
                "sort_order": sort_order,
                "is_other": is_other,
            },
        )


def upgrade() -> None:
    op.create_table(
        "education_majors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_education_majors_id", "education_majors", ["id"])
    op.create_index("ix_education_majors_code", "education_majors", ["code"], unique=True)
    _upsert_majors(_EDUCATION_MAJORS)


def downgrade() -> None:
    op.drop_index("ix_education_majors_code", table_name="education_majors")
    op.drop_index("ix_education_majors_id", table_name="education_majors")
    op.drop_table("education_majors")
