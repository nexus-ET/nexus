"""Add labeled office contact fields on businesses.

Revision ID: zz6a7bbizctc
Revises: yy5z6asupermaj
Create Date: 2026-08-29 07:55:00.000000

Columns were present on the Business model and in database.py bootstrap,
but never shipped as an Alembic revision — Hostinger DBs that only run
`alembic upgrade` were missing them (seed/SELECT failures).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "zz6a7bbizctc"
down_revision: Union[str, Sequence[str], None] = "yy5z6asupermaj"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("businesses")}

    if "office_phone_active" not in cols:
        op.add_column(
            "businesses",
            sa.Column(
                "office_phone_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    if "office_mobile_active" not in cols:
        op.add_column(
            "businesses",
            sa.Column(
                "office_mobile_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
    if "office_phone_contacts" not in cols:
        op.add_column(
            "businesses",
            sa.Column("office_phone_contacts", _JSON, nullable=True),
        )
    if "office_email_contacts" not in cols:
        op.add_column(
            "businesses",
            sa.Column("office_email_contacts", _JSON, nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("businesses")}

    for name in (
        "office_email_contacts",
        "office_phone_contacts",
        "office_mobile_active",
        "office_phone_active",
    ):
        if name in cols:
            op.drop_column("businesses", name)
