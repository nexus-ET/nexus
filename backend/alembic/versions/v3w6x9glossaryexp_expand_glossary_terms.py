"""Expand Nexus Intel glossary across all subscribed countries (~100 terms).

Revision ID: v3w6x9glossaryexp
Revises: u2p5r8isafinal
Create Date: 2026-07-28
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.intel_glossary_expansion_v1 import GLOSSARY_EXPANSION_V1

revision = "v3w6x9glossaryexp"
down_revision = "u2p5r8isafinal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    glossary = sa.table(
        "intel_glossary",
        sa.column("id", postgresql.UUID),
        sa.column("term_name", sa.String),
        sa.column("slug", sa.String),
        sa.column("category", sa.String),
        sa.column("country_code", sa.String),
        sa.column("lifecycle_stage", sa.String),
        sa.column("short_definition", sa.Text),
        sa.column("full_explanation", sa.Text),
        sa.column("key_metrics", postgresql.JSONB),
        sa.column("tags", postgresql.JSONB),
        sa.column("official_source_url", sa.Text),
        sa.column("is_student_facing", sa.Boolean),
        sa.column("last_verified_at", sa.DateTime(timezone=True)),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    inserted = 0
    for row in GLOSSARY_EXPANSION_V1:
        exists = conn.execute(
            sa.text("SELECT 1 FROM intel_glossary WHERE slug = :slug LIMIT 1"),
            {"slug": row["slug"]},
        ).scalar()
        if exists:
            continue
        op.bulk_insert(
            glossary,
            [
                {
                    "id": uuid.uuid4(),
                    **row,
                    "status": "ACTIVE",
                    "created_at": now,
                    "updated_at": now,
                    "last_verified_at": now,
                }
            ],
        )
        inserted += 1

    print(f"Nexus Intel glossary expansion inserted {inserted} terms.")


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [row["slug"] for row in GLOSSARY_EXPANSION_V1]
    if not slugs:
        return
    # Delete only expansion pack slugs (safe for environments that added manual terms).
    for slug in slugs:
        conn.execute(
            sa.text("DELETE FROM intel_glossary WHERE slug = :slug"),
            {"slug": slug},
        )
