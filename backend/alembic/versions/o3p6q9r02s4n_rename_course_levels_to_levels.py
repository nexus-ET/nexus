"""rename course_levels table to levels

Revision ID: o3p6q9r02s4n
Revises: n2o5p8q91r3m
Create Date: 2026-07-08 21:00:00.000000

Transactional: Alembic runs this upgrade in a single DB transaction.
If any FK step fails, the entire migration rolls back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o3p6q9r02s4n"
down_revision: Union[str, Sequence[str], None] = "n2o5p8q91r3m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_orphan_fks(connection) -> None:
    orphan_education = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM education_degrees ed
            LEFT JOIN levels l ON l.id = ed.level_id
            WHERE l.id IS NULL
            """
        )
    ).scalar_one()
    if orphan_education:
        raise RuntimeError(
            f"Migration validation failed: {orphan_education} education_degrees rows lack a valid level_id."
        )

    orphan_programs = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM programs p
            LEFT JOIN levels l ON l.id = p.level_id
            WHERE l.id IS NULL
            """
        )
    ).scalar_one()
    if orphan_programs:
        raise RuntimeError(
            f"Migration validation failed: {orphan_programs} programs rows lack a valid level_id."
        )


def upgrade() -> None:
    bind = op.get_bind()

    op.rename_table("course_levels", "levels")

    op.execute(sa.text("ALTER INDEX IF EXISTS ix_course_levels_code RENAME TO ix_levels_code"))
    op.execute(sa.text("ALTER INDEX IF EXISTS uq_course_levels_code RENAME TO uq_levels_code"))

    op.drop_constraint(
        "fk_education_degrees_course_level_id",
        "education_degrees",
        type_="foreignkey",
    )
    op.alter_column(
        "education_degrees",
        "course_level_id",
        new_column_name="level_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "ALTER INDEX IF EXISTS ix_education_degrees_course_level_id "
            "RENAME TO ix_education_degrees_level_id"
        )
    )
    op.create_foreign_key(
        "fk_education_degrees_level_id",
        "education_degrees",
        "levels",
        ["level_id"],
        ["id"],
    )

    op.drop_constraint("programs_level_id_fkey", "programs", type_="foreignkey")
    op.create_foreign_key(
        "fk_programs_level_id",
        "programs",
        "levels",
        ["level_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _assert_no_orphan_fks(bind)

    level_count = bind.execute(sa.text("SELECT COUNT(*) FROM levels")).scalar_one()
    if level_count == 0:
        raise RuntimeError("Migration validation failed: levels table is empty after rename.")


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_constraint("fk_programs_level_id", "programs", type_="foreignkey")
    op.create_foreign_key(
        "programs_level_id_fkey",
        "programs",
        "course_levels",
        ["level_id"],
        ["id"],
    )

    op.drop_constraint("fk_education_degrees_level_id", "education_degrees", type_="foreignkey")
    op.alter_column(
        "education_degrees",
        "level_id",
        new_column_name="course_level_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "ALTER INDEX IF EXISTS ix_education_degrees_level_id "
            "RENAME TO ix_education_degrees_course_level_id"
        )
    )
    op.create_foreign_key(
        "fk_education_degrees_course_level_id",
        "education_degrees",
        "course_levels",
        ["course_level_id"],
        ["id"],
    )

    op.rename_table("levels", "course_levels")
    op.execute(sa.text("ALTER INDEX IF EXISTS ix_levels_code RENAME TO ix_course_levels_code"))
    op.execute(sa.text("ALTER INDEX IF EXISTS uq_levels_code RENAME TO uq_course_levels_code"))

    _ = bind
