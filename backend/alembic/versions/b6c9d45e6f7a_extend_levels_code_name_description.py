"""Add code, name, description to levels and set canonical values.

Revision ID: b6c9d45e6f7a
Revises: a5b8c34d5e6f
Create Date: 2026-07-11 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6c9d45e6f7a"
down_revision: Union[str, Sequence[str], None] = "a5b8c34d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEVEL_ROWS = [
    (
        1,
        "FOUNDATIONAL",
        "Foundational",
        "Secondary, Pre-university and foundational pathways.",
    ),
    (
        2,
        "UNDERGRAD",
        "Undergraduate",
        "Undergraduate and bachelor-level study.",
    ),
    (
        3,
        "GRADUATE",
        "Graduate",
        "Master's and post-bachelor graduate study.",
    ),
    (
        4,
        "DOCTORAL",
        "Doctoral",
        "Doctorate and research-intensive doctoral study.",
    ),
]


def upgrade() -> None:
    op.add_column("levels", sa.Column("code", sa.String(length=50), nullable=True))
    op.add_column("levels", sa.Column("name", sa.String(length=100), nullable=True))
    op.add_column("levels", sa.Column("description", sa.Text(), nullable=True))

    bind = op.get_bind()
    for level_id, code, name, description in LEVEL_ROWS:
        bind.execute(
            sa.text(
                """
                UPDATE levels
                SET code = :code, name = :name, description = :description
                WHERE id = :level_id
                """
            ),
            {
                "level_id": level_id,
                "code": code,
                "name": name,
                "description": description,
            },
        )

    bind.execute(
        sa.text(
            """
            UPDATE levels
            SET
                code = COALESCE(code, 'LEVEL_' || id::text),
                name = COALESCE(name, value, 'Level ' || id::text),
                description = COALESCE(description, '')
            """
        )
    )

    op.alter_column("levels", "code", nullable=False)
    op.alter_column("levels", "name", nullable=False)
    op.create_index("ix_levels_code", "levels", ["code"], unique=True)
    op.create_unique_constraint("uq_levels_code", "levels", ["code"])
    op.drop_column("levels", "value")


def downgrade() -> None:
    op.add_column("levels", sa.Column("value", sa.String(length=100), nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE levels SET value = name"))
    op.alter_column("levels", "value", nullable=False)
    op.drop_constraint("uq_levels_code", "levels", type_="unique")
    op.drop_index("ix_levels_code", table_name="levels")
    op.drop_column("levels", "description")
    op.drop_column("levels", "name")
    op.drop_column("levels", "code")
