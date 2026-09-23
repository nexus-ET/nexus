"""Add document_requirement_levels junction; migrate program_level.

Revision ID: m1n2o3doclvls
Revises: l0m1n2docreq
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m1n2o3doclvls"
down_revision: Union[str, Sequence[str], None] = "l0m1n2docreq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_requirement_levels" not in tables:
        op.create_table(
            "document_requirement_levels",
            sa.Column("requirement_id", sa.Integer(), nullable=False),
            sa.Column("program_level", sa.String(length=50), nullable=False),
            sa.ForeignKeyConstraint(
                ["requirement_id"],
                ["document_requirements.id"],
                name="fk_doc_req_levels_requirement_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint(
                "requirement_id",
                "program_level",
                name="pk_document_requirement_levels",
            ),
        )

    if "document_requirements" in tables:
        columns = {c["name"] for c in inspector.get_columns("document_requirements")}
        if "program_level" in columns:
            op.execute(
                sa.text(
                    """
                    INSERT INTO document_requirement_levels (requirement_id, program_level)
                    SELECT id, program_level
                    FROM document_requirements
                    WHERE program_level IS NOT NULL
                      AND BTRIM(program_level) <> ''
                      AND NOT EXISTS (
                        SELECT 1
                        FROM document_requirement_levels l
                        WHERE l.requirement_id = document_requirements.id
                          AND l.program_level = document_requirements.program_level
                      )
                    """
                )
            )
            op.drop_column("document_requirements", "program_level")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_requirements" in tables:
        columns = {c["name"] for c in inspector.get_columns("document_requirements")}
        if "program_level" not in columns:
            op.add_column(
                "document_requirements",
                sa.Column("program_level", sa.String(length=50), nullable=True),
            )
            if "document_requirement_levels" in tables:
                op.execute(
                    sa.text(
                        """
                        UPDATE document_requirements dr
                        SET program_level = sub.program_level
                        FROM (
                            SELECT DISTINCT ON (requirement_id)
                                requirement_id,
                                program_level
                            FROM document_requirement_levels
                            ORDER BY requirement_id, program_level
                        ) AS sub
                        WHERE dr.id = sub.requirement_id
                        """
                    )
                )
            op.execute(
                sa.text(
                    """
                    UPDATE document_requirements
                    SET program_level = 'Undergraduate'
                    WHERE program_level IS NULL OR BTRIM(program_level) = ''
                    """
                )
            )
            op.alter_column(
                "document_requirements",
                "program_level",
                existing_type=sa.String(length=50),
                nullable=False,
            )

    if "document_requirement_levels" in tables:
        op.drop_table("document_requirement_levels")
