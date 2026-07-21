"""Replace single fax_number with typed fax_numbers lists.

Revision ID: x9y2z5a09b1c
Revises: w8x1y4z98a0b
Create Date: 2026-07-18
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "x9y2z5a09b1c"
down_revision = "w8x1y4z98a0b"
branch_labels = None
depends_on = None


def _migrate_table(table_name: str) -> None:
    op.add_column(table_name, sa.Column("fax_numbers", sa.JSON(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, fax_number FROM {table_name}")).mappings().all()
    for row in rows:
        legacy = (row["fax_number"] or "").strip() if row["fax_number"] else ""
        payload = [{"type": "Main", "value": legacy}] if legacy else []
        bind.execute(
            sa.text(f"UPDATE {table_name} SET fax_numbers = :fax_numbers WHERE id = :id"),
            {"id": row["id"], "fax_numbers": json.dumps(payload)},
        )
    op.execute(
        f"""
        UPDATE {table_name}
        SET fax_numbers = '[]'::json
        WHERE fax_numbers IS NULL
        """
    )
    op.drop_column(table_name, "fax_number")


def _downgrade_table(table_name: str) -> None:
    op.add_column(table_name, sa.Column("fax_number", sa.String(length=50), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, fax_numbers FROM {table_name}")).mappings().all()
    for row in rows:
        raw = row["fax_numbers"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        first = ""
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and str(item.get("value") or "").strip():
                    first = str(item.get("value")).strip()[:50]
                    break
                if isinstance(item, str) and item.strip():
                    first = item.strip()[:50]
                    break
        bind.execute(
            sa.text(f"UPDATE {table_name} SET fax_number = :fax_number WHERE id = :id"),
            {"id": row["id"], "fax_number": first or None},
        )
    op.drop_column(table_name, "fax_numbers")


def upgrade() -> None:
    _migrate_table("institutions")
    _migrate_table("campuses")


def downgrade() -> None:
    _downgrade_table("campuses")
    _downgrade_table("institutions")
