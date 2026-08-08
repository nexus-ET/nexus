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
    op.add_column(
        "intel_scraper_config",
        sa.Column("last_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "intel_scraper_config",
        sa.Column("last_content_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "intel_scraper_config",
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "intel_scraper_config",
        sa.Column("last_http_status", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("intel_scraper_config", "last_http_status")
    op.drop_column("intel_scraper_config", "last_fetched_at")
    op.drop_column("intel_scraper_config", "last_content_text")
    op.drop_column("intel_scraper_config", "last_content_hash")
