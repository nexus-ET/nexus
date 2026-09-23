"""Add document requirements and templates tables.

Revision ID: l0m1n2docreq
Revises: k9l0m1spousen
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l0m1n2docreq"
down_revision: Union[str, Sequence[str], None] = "k9l0m1spousen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_templates" not in tables:
        op.create_table(
            "document_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_name", sa.String(length=150), nullable=False),
            sa.Column("file_url", sa.Text(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("uploaded_by", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["uploaded_by"],
                ["users.id"],
                name="fk_document_templates_uploaded_by_users",
                ondelete="SET NULL",
            ),
        )

    if "document_requirements" not in tables:
        op.create_table(
            "document_requirements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("program_level", sa.String(length=50), nullable=False),
            sa.Column(
                "is_global",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("document_name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_mandatory",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["template_id"],
                ["document_templates.id"],
                name="fk_document_requirements_template_id",
                ondelete="SET NULL",
            ),
        )

    if "document_requirement_countries" not in tables:
        op.create_table(
            "document_requirement_countries",
            sa.Column("requirement_id", sa.Integer(), nullable=False),
            sa.Column("country_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["requirement_id"],
                ["document_requirements.id"],
                name="fk_doc_req_countries_requirement_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["country_id"],
                ["countries.id"],
                name="fk_doc_req_countries_country_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint(
                "requirement_id",
                "country_id",
                name="pk_document_requirement_countries",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "document_requirement_countries" in tables:
        op.drop_table("document_requirement_countries")
    if "document_requirements" in tables:
        op.drop_table("document_requirements")
    if "document_templates" in tables:
        op.drop_table("document_templates")
