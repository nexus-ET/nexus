"""Point ISA Japan scraper at final MOJ URL (skip redirect chain).

Revision ID: u2p5r8isafinal
Revises: t1o4q7scrapefix
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "u2p5r8isafinal"
down_revision = "t1o4q7scrapefix"
branch_labels = None
depends_on = None

OLD_URL = "https://www.isa.go.jp/en/"
NEW_URL = "https://www.moj.go.jp/isa/"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{NEW_URL}',
            updated_at = NOW()
        WHERE source_name = 'ISA Japan Immigration'
          AND target_url = '{OLD_URL}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{OLD_URL}',
            updated_at = NOW()
        WHERE source_name = 'ISA Japan Immigration'
          AND target_url = '{NEW_URL}'
        """
    )
