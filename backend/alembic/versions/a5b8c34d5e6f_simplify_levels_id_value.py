"""Recreate levels as id + value lookup (rows 1-4 only).

Revision ID: a5b8c34d5e6f
Revises: z4a7b23c4d5e
Create Date: 2026-07-11 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b8c34d5e6f"
down_revision: Union[str, Sequence[str], None] = "z4a7b23c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEVEL_ROWS = [
    (1, "Entry"),
    (2, "Undergraduate"),
    (3, "Graduate"),
    (4, "Doctoral"),
]

REMAP_LEVEL_ID = """
UPDATE {table} AS target
SET level_id = mapped.new_level_id
FROM (
    SELECT
        t.{id_column} AS row_id,
        CASE
            WHEN l.code = 'ENTRY' THEN 1
            WHEN l.code = 'UNDERGRAD' THEN 2
            WHEN l.code = 'GRADUATE' THEN 3
            WHEN l.code = 'DOCTORAL' THEN 4
            WHEN l.code = 'CERT' THEN 4
            WHEN l.sort_order BETWEEN 1 AND 4 THEN l.sort_order
            ELSE 2
        END AS new_level_id
    FROM {table} t
    LEFT JOIN levels l ON l.id = t.level_id
) AS mapped
WHERE target.{id_column} = mapped.row_id
  AND target.level_id IS NOT NULL
"""


def _drop_level_foreign_keys() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("programs", "education_degrees", "education_courses", "education_major_levels"):
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") == "levels":
                op.drop_constraint(fk["name"], table_name, type_="foreignkey")


def _remap_level_ids(connection) -> None:
    for table_name, id_column in (
        ("programs", "id"),
        ("education_degrees", "id"),
        ("education_courses", "id"),
    ):
        connection.execute(
            sa.text(
                REMAP_LEVEL_ID.format(table=table_name, id_column=id_column)
            )
        )

    connection.execute(
        sa.text(
            """
            UPDATE education_major_levels AS eml
            SET level_id = mapped.new_level_id
            FROM (
                SELECT
                    eml.education_major_id,
                    eml.level_id AS old_level_id,
                    CASE
                        WHEN l.code = 'ENTRY' THEN 1
                        WHEN l.code = 'UNDERGRAD' THEN 2
                        WHEN l.code = 'GRADUATE' THEN 3
                        WHEN l.code = 'DOCTORAL' THEN 4
                        WHEN l.code = 'CERT' THEN 4
                        WHEN l.sort_order BETWEEN 1 AND 4 THEN l.sort_order
                        ELSE 2
                    END AS new_level_id
                FROM education_major_levels eml
                LEFT JOIN levels l ON l.id = eml.level_id
            ) AS mapped
            WHERE eml.education_major_id = mapped.education_major_id
              AND eml.level_id = mapped.old_level_id
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM education_major_levels eml
            WHERE eml.ctid NOT IN (
                SELECT MIN(sub.ctid)
                FROM education_major_levels sub
                GROUP BY sub.education_major_id, sub.level_id
            )
            """
        )
    )

    for table_name in ("programs", "education_degrees", "education_courses"):
        connection.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET level_id = 2
                WHERE level_id IS NULL OR level_id NOT BETWEEN 1 AND 4
                """
            )
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM education_major_levels
            WHERE level_id IS NULL OR level_id NOT BETWEEN 1 AND 4
            """
        )
    )


def _create_level_foreign_keys() -> None:
    op.create_foreign_key(
        "fk_programs_level_id",
        "programs",
        "levels",
        ["level_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_education_degrees_level_id",
        "education_degrees",
        "levels",
        ["level_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_education_courses_level_id",
        "education_courses",
        "levels",
        ["level_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_education_major_levels_level_id",
        "education_major_levels",
        "levels",
        ["level_id"],
        ["id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    bind = op.get_bind()
    _drop_level_foreign_keys()
    _remap_level_ids(bind)
    op.drop_index("ix_levels_code", table_name="levels")
    op.drop_table("levels")

    op.create_table(
        "levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("value", sa.String(length=100), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "levels",
            sa.column("id", sa.Integer()),
            sa.column("value", sa.String()),
        ),
        [{"id": level_id, "value": value} for level_id, value in LEVEL_ROWS],
    )
    _create_level_foreign_keys()


def downgrade() -> None:
    _drop_level_foreign_keys()
    op.drop_table("levels")
    op.create_table(
        "levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("code", name="uq_levels_code"),
    )
    op.create_index("ix_levels_code", "levels", ["code"], unique=True)
    op.bulk_insert(
        sa.table(
            "levels",
            sa.column("code", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "ENTRY", "name": "Entry", "description": "Pre-university and foundational pathways.", "sort_order": 1, "is_active": True},
            {"code": "UNDERGRAD", "name": "Undergraduate", "description": "Undergraduate and bachelor-level study.", "sort_order": 2, "is_active": True},
            {"code": "GRADUATE", "name": "Graduate", "description": "Master's and post-bachelor graduate study.", "sort_order": 3, "is_active": True},
            {"code": "DOCTORAL", "name": "Doctoral", "description": "Doctorate and research-intensive doctoral study.", "sort_order": 4, "is_active": True},
            {"code": "CERT", "name": "Certificate", "description": "Professional certificates and credential programs.", "sort_order": 5, "is_active": True},
        ],
    )
    _create_level_foreign_keys()
