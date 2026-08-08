"""Retarget France-Visas scraper off Cloudflare-blocked france-visas.gouv.fr.

Revision ID: u2p5r8frvisas
Revises: c3d4e5flowxbrick
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "u2p5r8frvisas"
down_revision = "c3d4e5flowxbrick"
branch_labels = None
depends_on = None

# france-visas.gouv.fr returns Cloudflare 403 ("Just a moment...") to httpx and
# headless Chromium. service-public.gouv.fr F16162 is the official long-stay
# visa guidance page and remains fetchable.
OLD_FRANCE_VISAS_URL = "https://france-visas.gouv.fr/"
NEW_FRANCE_VISAS_URL = (
    "https://www.service-public.gouv.fr/particuliers/vosdroits/F16162"
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{NEW_FRANCE_VISAS_URL}',
            last_error = NULL,
            status = 'IDLE',
            updated_at = NOW()
        WHERE source_name = 'France-Visas'
          AND target_url = '{OLD_FRANCE_VISAS_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{NEW_FRANCE_VISAS_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{OLD_FRANCE_VISAS_URL}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE intel_scraper_config
        SET target_url = '{OLD_FRANCE_VISAS_URL}',
            updated_at = NOW()
        WHERE source_name = 'France-Visas'
          AND target_url = '{NEW_FRANCE_VISAS_URL}'
        """
    )
    op.execute(
        f"""
        UPDATE intel_glossary
        SET official_source_url = '{OLD_FRANCE_VISAS_URL}',
            updated_at = NOW()
        WHERE official_source_url = '{NEW_FRANCE_VISAS_URL}'
        """
    )
