"""Retarget Cloudflare-blocked US State Dept scraper to EducationUSA.

Revision ID: s0n3p6scrapehard
Revises: r9m2n5scrapefetch
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "s0n3p6scrapehard"
down_revision = "r9m2n5scrapefetch"
branch_labels = None
depends_on = None

OLD_STATE_URL = "https://travel.state.gov/content/travel/en/us-visas/study/student-visa.html"
NEW_STATE_URL = "https://educationusa.state.gov/"


def upgrade() -> None:
    # travel.state.gov is behind a Cloudflare bot wall that blocks headless clients.
    # EducationUSA is the State Dept's student-facing official site and is fetchable.
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{NEW_STATE_URL}',
            last_error = NULL,
            status = 'IDLE',
            updated_at = NOW()
        WHERE source_name = 'US State Dept Student Visa'
          AND target_url = '{OLD_STATE_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{NEW_STATE_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{OLD_STATE_URL}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{OLD_STATE_URL}',
            updated_at = NOW()
        WHERE source_name = 'US State Dept Student Visa'
          AND target_url = '{NEW_STATE_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{OLD_STATE_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{NEW_STATE_URL}'
        """
    )
