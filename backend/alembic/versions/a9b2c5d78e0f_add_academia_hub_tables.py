"""add academia hub geography and institution tables

Revision ID: a9b2c5d78e0f
Revises: f8g1h4i69j9k
Create Date: 2026-07-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b2c5d78e0f"
down_revision: Union[str, Sequence[str], None] = "f8g1h4i69j9k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geography_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_geography_states_id", "geography_states", ["id"])
    op.create_index("ix_geography_states_country_id", "geography_states", ["country_id"])
    op.create_index("ix_geography_states_name", "geography_states", ["name"])

    op.create_table(
        "geography_cities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=False),
        sa.Column("state_id", sa.Integer(), sa.ForeignKey("geography_states.id"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_geography_cities_id", "geography_cities", ["id"])
    op.create_index("ix_geography_cities_country_id", "geography_cities", ["country_id"])
    op.create_index("ix_geography_cities_state_id", "geography_cities", ["state_id"])
    op.create_index("ix_geography_cities_name", "geography_cities", ["name"])

    op.create_table(
        "institutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("institution_type", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_institutions_id", "institutions", ["id"])
    op.create_index("ix_institutions_country_id", "institutions", ["country_id"])
    op.create_index("ix_institutions_name", "institutions", ["name"])
    op.create_index("ix_institutions_code", "institutions", ["code"])

    op.create_table(
        "campuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_campuses_id", "campuses", ["id"])
    op.create_index("ix_campuses_institution_id", "campuses", ["institution_id"])
    op.create_index("ix_campuses_name", "campuses", ["name"])

    op.create_table(
        "colleges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_colleges_id", "colleges", ["id"])
    op.create_index("ix_colleges_institution_id", "colleges", ["institution_id"])
    op.create_index("ix_colleges_campus_id", "colleges", ["campus_id"])
    op.create_index("ix_colleges_name", "colleges", ["name"])


def downgrade() -> None:
    op.drop_index("ix_colleges_name", table_name="colleges")
    op.drop_index("ix_colleges_campus_id", table_name="colleges")
    op.drop_index("ix_colleges_institution_id", table_name="colleges")
    op.drop_index("ix_colleges_id", table_name="colleges")
    op.drop_table("colleges")

    op.drop_index("ix_campuses_name", table_name="campuses")
    op.drop_index("ix_campuses_institution_id", table_name="campuses")
    op.drop_index("ix_campuses_id", table_name="campuses")
    op.drop_table("campuses")

    op.drop_index("ix_institutions_code", table_name="institutions")
    op.drop_index("ix_institutions_name", table_name="institutions")
    op.drop_index("ix_institutions_country_id", table_name="institutions")
    op.drop_index("ix_institutions_id", table_name="institutions")
    op.drop_table("institutions")

    op.drop_index("ix_geography_cities_name", table_name="geography_cities")
    op.drop_index("ix_geography_cities_state_id", table_name="geography_cities")
    op.drop_index("ix_geography_cities_country_id", table_name="geography_cities")
    op.drop_index("ix_geography_cities_id", table_name="geography_cities")
    op.drop_table("geography_cities")

    op.drop_index("ix_geography_states_name", table_name="geography_states")
    op.drop_index("ix_geography_states_country_id", table_name="geography_states")
    op.drop_index("ix_geography_states_id", table_name="geography_states")
    op.drop_table("geography_states")
