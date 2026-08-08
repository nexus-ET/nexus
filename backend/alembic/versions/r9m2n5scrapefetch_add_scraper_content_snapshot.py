"""Add content snapshot columns for Nexus Intel real scrapers.

Revision ID: r9m2n5scrapefetch
Revises: q8k1l4eurowintel
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r9m2n5scrapefetch"
down_revision = "q8k1l4eurowintel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("intel_scraper_config"):
        return
    cols = {c["name"] for c in inspector.get_columns("intel_scraper_config")}
    if "last_content_hash" not in cols:
        op.add_column(
            "intel_scraper_config",
            sa.Column("last_content_hash", sa.String(length=64), nullable=True),
        )
    if "last_content_text" not in cols:
        op.add_column(
            "intel_scraper_config",
            sa.Column("last_content_text", sa.Text(), nullable=True),
        )
    if "last_fetched_at" not in cols:
        op.add_column(
            "intel_scraper_config",
            sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "last_http_status" not in cols:
        op.add_column(
            "intel_scraper_config",
            sa.Column("last_http_status", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("intel_scraper_config"):
        return
    cols = {c["name"] for c in inspector.get_columns("intel_scraper_config")}
    for col in ("last_http_status", "last_fetched_at", "last_content_text", "last_content_hash"):
        if col in cols:
            op.drop_column("intel_scraper_config", col)
