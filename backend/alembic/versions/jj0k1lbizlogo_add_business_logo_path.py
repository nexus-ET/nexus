"""Add logo_path on businesses for local company logo uploads.

Revision ID: jj0k1lbizlogo
Revises: ii9j0kintakeass
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "jj0k1lbizlogo"
down_revision: Union[str, Sequence[str], None] = "ii9j0kintakeass"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("businesses")}
    if "logo_path" in cols:
        return
    op.add_column("businesses", sa.Column("logo_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("businesses", "logo_path")
