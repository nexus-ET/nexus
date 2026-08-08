"""Harden Nexus Intel scraper fetch resilience and retarget blocked DAAD URL.

Revision ID: t1o4q7scrapefix
Revises: s0n3p6scrapehard
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "t1o4q7scrapefix"
down_revision = "s0n3p6scrapehard"
branch_labels = None
depends_on = None

OLD_DAAD_URL = "https://www.daad.de/en/"
NEW_DAAD_URL = "https://www.hochschulkompass.de/en/study-in-germany.html"


def upgrade() -> None:
    # daad.de currently returns bot-wall 403 / timeouts from datacenter and headless clients.
    # Hochschulkompass (HRK) is an official DE study portal that remains fetchable.
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{NEW_DAAD_URL}',
            last_error = NULL,
            status = 'IDLE',
            updated_at = NOW()
        WHERE source_name = 'DAAD Study in Germany'
          AND target_url = '{OLD_DAAD_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{NEW_DAAD_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{OLD_DAAD_URL}'
        """
    )
    # Clear stale ERROR rows for scrapers that failed only because Playwright was missing.
    op.execute(
        """
        UPDATE intel_scraper_config
        SET last_error = NULL,
            status = 'IDLE',
            updated_at = NOW()
        WHERE status = 'ERROR'
          AND (
            last_error ILIKE '%Playwright is not installed%'
            OR last_error ILIKE '%StreamReset%'
            OR last_error ILIKE '%status=403%'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{OLD_DAAD_URL}',
            updated_at = NOW()
        WHERE source_name = 'DAAD Study in Germany'
          AND target_url = '{NEW_DAAD_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{OLD_DAAD_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{NEW_DAAD_URL}'
        """
    )
