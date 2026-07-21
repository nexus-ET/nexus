"""add institution profile fields for wizard step 1

Revision ID: g5h8i1j24k6f
Revises: f4g7h0i13j5e
Create Date: 2026-07-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g5h8i1j24k6f"
down_revision: Union[str, Sequence[str], None] = "f4g7h0i13j5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("institutions", sa.Column("state_id", sa.Integer(), nullable=True))
    op.add_column("institutions", sa.Column("city_id", sa.Integer(), nullable=True))
    op.add_column("institutions", sa.Column("zipcode", sa.String(length=10), nullable=True))
    op.add_column("institutions", sa.Column("company_affiliated", sa.Boolean(), nullable=True))
    op.add_column("institutions", sa.Column("ranking_tier_global", sa.String(length=120), nullable=True))
    op.add_column("institutions", sa.Column("ad_promotion_flag", sa.Boolean(), nullable=True))
    op.add_column("institutions", sa.Column("institution_web_url", sa.String(length=250), nullable=True))
    op.add_column(
        "institutions",
        sa.Column("currency_type", sa.String(length=10), nullable=False, server_default="USD"),
    )
    op.add_column("institutions", sa.Column("students_count", sa.String(length=250), nullable=True))
    op.add_column("institutions", sa.Column("short_description", sa.String(length=500), nullable=True))
    op.add_column("institutions", sa.Column("long_description", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_institutions_state_id",
        "institutions",
        "geography_states",
        ["state_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_institutions_city_id",
        "institutions",
        "geography_cities",
        ["city_id"],
        ["id"],
    )
    op.create_index("ix_institutions_state_id", "institutions", ["state_id"])
    op.create_index("ix_institutions_city_id", "institutions", ["city_id"])


def downgrade() -> None:
    op.drop_index("ix_institutions_city_id", table_name="institutions")
    op.drop_index("ix_institutions_state_id", table_name="institutions")
    op.drop_constraint("fk_institutions_city_id", "institutions", type_="foreignkey")
    op.drop_constraint("fk_institutions_state_id", "institutions", type_="foreignkey")
    op.drop_column("institutions", "long_description")
    op.drop_column("institutions", "short_description")
    op.drop_column("institutions", "students_count")
    op.drop_column("institutions", "currency_type")
    op.drop_column("institutions", "institution_web_url")
    op.drop_column("institutions", "ad_promotion_flag")
    op.drop_column("institutions", "ranking_tier_global")
    op.drop_column("institutions", "company_affiliated")
    op.drop_column("institutions", "zipcode")
    op.drop_column("institutions", "city_id")
    op.drop_column("institutions", "state_id")
