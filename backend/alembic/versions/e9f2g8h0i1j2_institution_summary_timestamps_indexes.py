"""Add institution timestamps and summary search indexes.

Revision ID: e9f2g8h0i1j2
Revises: d8e1f67g8h9i
Create Date: 2026-07-11 12:40:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e9f2g8h0i1j2"
down_revision: Union[str, Sequence[str], None] = "d8e1f67g8h9i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "institutions",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.execute(
        """
        UPDATE institutions AS i
        SET created_at = COALESCE(
            (
                SELECT MIN(a.created_at)
                FROM academia_audit_logs AS a
                WHERE a.entity_type = 'institution'
                  AND a.entity_id = i.id
            ),
            NOW()
        ),
        updated_at = COALESCE(
            (
                SELECT MAX(a.created_at)
                FROM academia_audit_logs AS a
                WHERE a.entity_type = 'institution'
                  AND a.entity_id = i.id
            ),
            NOW()
        )
        """
    )

    op.create_index("ix_institutions_created_at", "institutions", ["created_at"])
    op.create_index("ix_institutions_institution_type", "institutions", ["institution_type"])
    op.create_index("ix_institutions_is_active", "institutions", ["is_active"])
    op.create_index(
        "ix_institutions_country_state",
        "institutions",
        ["country_id", "state_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_institutions_country_state", table_name="institutions")
    op.drop_index("ix_institutions_is_active", table_name="institutions")
    op.drop_index("ix_institutions_institution_type", table_name="institutions")
    op.drop_index("ix_institutions_created_at", table_name="institutions")
    op.drop_column("institutions", "updated_at")
    op.drop_column("institutions", "created_at")
