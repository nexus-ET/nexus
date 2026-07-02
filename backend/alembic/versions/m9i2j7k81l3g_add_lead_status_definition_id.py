"""add lead status_definition_id (idempotent follow-up)

Revision ID: m9i2j7k81l3g
Revises: l8h1i6j70k2f
Create Date: 2026-06-12 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "m9i2j7k81l3g"
down_revision: Union[str, Sequence[str], None] = "l8h1i6j70k2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("leads"):
        return

    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "status_definition_id" not in columns:
        op.add_column("leads", sa.Column("status_definition_id", sa.Integer(), nullable=True))
    if "status_entered_at" not in columns:
        op.add_column("leads", sa.Column("status_entered_at", sa.DateTime(), nullable=True))

    if not inspector.has_table("status_definitions"):
        return

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("leads")}
    if "fk_leads_status_definition_id" not in foreign_keys and "status_definition_id" in (
        columns | {"status_definition_id"}
    ):
        op.create_foreign_key(
            "fk_leads_status_definition_id",
            "leads",
            "status_definitions",
            ["status_definition_id"],
            ["id"],
            ondelete="SET NULL",
        )

    indexes = {index["name"] for index in inspector.get_indexes("leads")}
    if "ix_leads_status_definition_id" not in indexes:
        op.create_index("ix_leads_status_definition_id", "leads", ["status_definition_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("leads"):
        return

    indexes = {index["name"] for index in inspector.get_indexes("leads")}
    if "ix_leads_status_definition_id" in indexes:
        op.drop_index("ix_leads_status_definition_id", table_name="leads")

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("leads")}
    if "fk_leads_status_definition_id" in foreign_keys:
        op.drop_constraint("fk_leads_status_definition_id", "leads", type_="foreignkey")

    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "status_entered_at" in columns:
        op.drop_column("leads", "status_entered_at")
    if "status_definition_id" in columns:
        op.drop_column("leads", "status_definition_id")
