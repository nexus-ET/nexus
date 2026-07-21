"""Add program-to-catalog-major mappings table and dedupe cloned majors.

Revision ID: j5k8l4m7n9o0
Revises: i4j7k3l6m8n9
Create Date: 2026-07-13 20:40:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "j5k8l4m7n9o0"
down_revision: Union[str, Sequence[str], None] = "i4j7k3l6m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "program_education_major_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("education_major_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["education_major_id"], ["education_majors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", name="uq_program_education_major_mappings_program_id"),
    )
    op.create_index(
        "ix_program_education_major_mappings_program_id",
        "program_education_major_mappings",
        ["program_id"],
    )
    op.create_index(
        "ix_program_education_major_mappings_education_major_id",
        "program_education_major_mappings",
        ["education_major_id"],
    )

    bind = op.get_bind()
    linked_rows = bind.execute(
        sa.text(
            """
            SELECT id, program_id, label
            FROM education_majors
            WHERE program_id IS NOT NULL
            ORDER BY id ASC
            """
        )
    ).fetchall()

    for row in linked_rows:
        catalog = bind.execute(
            sa.text(
                """
                SELECT id
                FROM education_majors
                WHERE program_id IS NULL
                  AND lower(trim(label)) = lower(trim(:label))
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"label": row.label},
        ).fetchone()

        catalog_id = catalog.id if catalog else row.id
        if catalog is None:
            bind.execute(
                sa.text("UPDATE education_majors SET program_id = NULL WHERE id = :major_id"),
                {"major_id": row.id},
            )
        elif catalog.id != row.id:
            bind.execute(
                sa.text(
                    """
                    UPDATE education_courses
                    SET education_major_id = :catalog_id
                    WHERE education_major_id = :duplicate_id
                    """
                ),
                {"catalog_id": catalog_id, "duplicate_id": row.id},
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE target_courses
                    SET education_major_id = :catalog_id
                    WHERE education_major_id = :duplicate_id
                    """
                ),
                {"catalog_id": catalog_id, "duplicate_id": row.id},
            )
            bind.execute(
                sa.text(
                    "DELETE FROM education_major_levels WHERE education_major_id = :duplicate_id"
                ),
                {"duplicate_id": row.id},
            )
            bind.execute(
                sa.text("DELETE FROM education_majors WHERE id = :duplicate_id"),
                {"duplicate_id": row.id},
            )

        bind.execute(
            sa.text(
                """
                INSERT INTO program_education_major_mappings (program_id, education_major_id)
                VALUES (:program_id, :major_id)
                ON CONFLICT (program_id)
                DO UPDATE SET education_major_id = EXCLUDED.education_major_id
                """
            ),
            {"program_id": row.program_id, "major_id": catalog_id},
        )


def downgrade() -> None:
    op.drop_index(
        "ix_program_education_major_mappings_education_major_id",
        table_name="program_education_major_mappings",
    )
    op.drop_index(
        "ix_program_education_major_mappings_program_id",
        table_name="program_education_major_mappings",
    )
    op.drop_table("program_education_major_mappings")
