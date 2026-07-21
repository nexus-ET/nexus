"""add institution and college web_links

Revision ID: a2b5c8d31e4f
Revises: z1a4b7c20d3e
Create Date: 2026-07-19 21:30:00.000000

"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a2b5c8d31e4f"
down_revision: Union[str, Sequence[str], None] = "z1a4b7c20d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("institutions", sa.Column("web_links", sa.JSON(), nullable=True))
    op.add_column("colleges", sa.Column("web_links", sa.JSON(), nullable=True))

    institutions = (
        bind.execute(sa.text("SELECT id, institution_web_url, web_links FROM institutions"))
        .mappings()
        .all()
    )
    for row in institutions:
        existing = row["web_links"]
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except json.JSONDecodeError:
                existing = None
        if isinstance(existing, list) and existing:
            continue
        legacy = str(row["institution_web_url"] or "").strip()
        if not legacy:
            continue
        bind.execute(
            sa.text("UPDATE institutions SET web_links = :web_links WHERE id = :id"),
            {
                "id": row["id"],
                "web_links": json.dumps([{"type": "Website", "value": legacy}]),
            },
        )

    colleges = (
        bind.execute(sa.text("SELECT id, web_url, web_links FROM colleges")).mappings().all()
    )
    for row in colleges:
        existing = row["web_links"]
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except json.JSONDecodeError:
                existing = None
        if isinstance(existing, list) and existing:
            continue
        legacy = str(row["web_url"] or "").strip()
        if not legacy:
            continue
        bind.execute(
            sa.text("UPDATE colleges SET web_links = :web_links WHERE id = :id"),
            {
                "id": row["id"],
                "web_links": json.dumps([{"type": "Website", "value": legacy}]),
            },
        )


def downgrade() -> None:
    op.drop_column("colleges", "web_links")
    op.drop_column("institutions", "web_links")
