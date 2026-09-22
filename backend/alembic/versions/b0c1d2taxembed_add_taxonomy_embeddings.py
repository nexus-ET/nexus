"""Add education taxonomy embedding tables (super/major/sub).

Stores dense vectors as double-precision arrays so Hostinger Postgres works
without the pgvector extension. Dimension matches the configured embedding model.

Revision ID: b0c1d2taxembed
Revises: a0b1c2aiprompts
Create Date: 2026-09-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b0c1d2taxembed"
down_revision: Union[str, Sequence[str], None] = "a0b1c2aiprompts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_embedding_table(
    table_name: str,
    fk_column: str,
    parent_table: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(fk_column, sa.Integer(), nullable=False),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=False,
        ),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("source_text_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            [fk_column],
            [f"{parent_table}.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(fk_column, name=f"uq_{table_name}_{fk_column}"),
    )
    op.create_index(f"ix_{table_name}_{fk_column}", table_name, [fk_column])
    op.create_index(
        f"ix_{table_name}_source_text_hash",
        table_name,
        ["source_text_hash"],
    )


def upgrade() -> None:
    # Best-effort: enable pgvector when the host ships it (local Docker can).
    # Hostinger Postgres currently lacks the extension; float arrays still work.
    op.execute(
        """
        DO $$
        BEGIN
          CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION
          WHEN undefined_file THEN
            RAISE NOTICE 'pgvector extension files not installed; using float arrays';
          WHEN insufficient_privilege THEN
            RAISE NOTICE 'pgvector install requires superuser; using float arrays';
          WHEN OTHERS THEN
            RAISE NOTICE 'pgvector unavailable (%); using float arrays', SQLERRM;
        END $$;
        """
    )
    _create_embedding_table(
        "education_super_major_embeddings",
        "super_major_id",
        "education_super_majors",
    )
    _create_embedding_table(
        "education_major_embeddings",
        "major_id",
        "education_majors",
    )
    _create_embedding_table(
        "education_sub_major_embeddings",
        "sub_major_id",
        "education_sub_majors",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_education_sub_major_embeddings_source_text_hash",
        table_name="education_sub_major_embeddings",
    )
    op.drop_index(
        "ix_education_sub_major_embeddings_sub_major_id",
        table_name="education_sub_major_embeddings",
    )
    op.drop_table("education_sub_major_embeddings")

    op.drop_index(
        "ix_education_major_embeddings_source_text_hash",
        table_name="education_major_embeddings",
    )
    op.drop_index(
        "ix_education_major_embeddings_major_id",
        table_name="education_major_embeddings",
    )
    op.drop_table("education_major_embeddings")

    op.drop_index(
        "ix_education_super_major_embeddings_source_text_hash",
        table_name="education_super_major_embeddings",
    )
    op.drop_index(
        "ix_education_super_major_embeddings_super_major_id",
        table_name="education_super_major_embeddings",
    )
    op.drop_table("education_super_major_embeddings")
