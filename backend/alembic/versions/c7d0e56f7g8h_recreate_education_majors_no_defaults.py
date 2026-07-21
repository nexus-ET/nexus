"""Drop and recreate education_majors without default seed rows.

Keeps only majors created via Academia Hub (rows with program_id set).
Removes orphaned catalog defaults (Computer Science, Engineering, Other, etc.).

Revision ID: c7d0e56f7g8h
Revises: b6c9d45e6f7a
Create Date: 2026-07-11 11:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7d0e56f7g8h"
down_revision: Union[str, Sequence[str], None] = "b6c9d45e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_education_major_foreign_keys() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("education_courses", "target_courses", "education_major_levels"):
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") == "education_majors":
                op.drop_constraint(fk["name"], table_name, type_="foreignkey")


def _create_education_major_foreign_keys() -> None:
    op.create_foreign_key(
        "fk_education_courses_education_major_id",
        "education_courses",
        "education_majors",
        ["education_major_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_target_courses_education_major_id",
        "target_courses",
        "education_majors",
        ["education_major_id"],
        ["id"],
    )


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            CREATE TEMP TABLE _education_majors_keep AS
            SELECT
                id,
                code,
                label,
                program_id,
                is_other,
                is_active,
                sort_order
            FROM education_majors
            WHERE program_id IS NOT NULL
            """
        )
    )

    bind.execute(
        sa.text(
            """
            CREATE TEMP TABLE _education_major_levels_keep AS
            SELECT eml.education_major_id, eml.level_id
            FROM education_major_levels eml
            JOIN education_majors em ON em.id = eml.education_major_id
            WHERE em.program_id IS NOT NULL
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE target_courses
            SET education_major_id = NULL
            WHERE education_major_id IN (
                SELECT id FROM education_majors WHERE program_id IS NULL
            )
            """
        )
    )

    _drop_education_major_foreign_keys()
    op.drop_table("education_major_levels")
    op.drop_index("ix_education_majors_program_id", table_name="education_majors")
    op.drop_index("ix_education_majors_code", table_name="education_majors")
    op.drop_index("ix_education_majors_id", table_name="education_majors")
    op.drop_table("education_majors")

    op.create_table(
        "education_majors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_education_majors_program_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_education_majors_id", "education_majors", ["id"])
    op.create_index("ix_education_majors_code", "education_majors", ["code"], unique=True)
    op.create_index("ix_education_majors_program_id", "education_majors", ["program_id"])

    bind.execute(
        sa.text(
            """
            INSERT INTO education_majors (
                id, code, label, program_id, is_other, is_active, sort_order
            )
            SELECT id, code, label, program_id, is_other, is_active, sort_order
            FROM _education_majors_keep
            ORDER BY id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('education_majors', 'id'),
                COALESCE((SELECT MAX(id) FROM education_majors), 0),
                COALESCE((SELECT MAX(id) FROM education_majors), 0) > 0
            )
            """
        )
    )

    op.create_table(
        "education_major_levels",
        sa.Column("education_major_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["education_major_id"],
            ["education_majors.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["level_id"],
            ["levels.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("education_major_id", "level_id"),
    )
    op.create_index(
        "ix_education_major_levels_level_id",
        "education_major_levels",
        ["level_id"],
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO education_major_levels (education_major_id, level_id)
            SELECT education_major_id, level_id
            FROM _education_major_levels_keep
            """
        )
    )

    _create_education_major_foreign_keys()


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade not supported for education_majors recreate migration."
    )
