"""Add IntelX Inquiry Hub FAQs and seed process-aligned guidance.

Revision ID: mm3n4oinquiryhub
Revises: ll2m3nregdata
Create Date: 2026-08-14
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.intel_inquiry_seed import INQUIRY_FAQ_SEED, resolve_inquiry_path

revision = "mm3n4oinquiryhub"
down_revision = "ll2m3nregdata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("intel_inquiry_faqs"):
        op.create_table(
            "intel_inquiry_faqs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("process_code", sa.String(16), nullable=False),
            sa.Column("process_name", sa.String(120), nullable=False),
            sa.Column("subprocess_code", sa.String(16), nullable=True),
            sa.Column("subprocess_name", sa.String(160), nullable=True),
            sa.Column("nested_process_code", sa.String(16), nullable=True),
            sa.Column("nested_process_name", sa.String(160), nullable=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("process_code", "subprocess_code", "nested_process_code", "is_active"):
            op.create_index(
                f"ix_intel_inquiry_faqs_{column}",
                "intel_inquiry_faqs",
                [column],
            )

    table = sa.table(
        "intel_inquiry_faqs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("process_code", sa.String),
        sa.column("process_name", sa.String),
        sa.column("subprocess_code", sa.String),
        sa.column("subprocess_name", sa.String),
        sa.column("nested_process_code", sa.String),
        sa.column("nested_process_name", sa.String),
        sa.column("question", sa.Text),
        sa.column("answer", sa.Text),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    rows = []
    path_orders: dict[str, int] = {}
    for item in INQUIRY_FAQ_SEED:
        path_orders[item["path"]] = path_orders.get(item["path"], 0) + 1
        rows.append(
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"nexus:intel:inquiry:{item['question']}"),
                **resolve_inquiry_path(item["path"]),
                "question": item["question"],
                "answer": item["answer"],
                "sort_order": path_orders[item["path"]],
                "is_active": True,
            }
        )
    op.bulk_insert(table, rows)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("intel_inquiry_faqs"):
        op.drop_table("intel_inquiry_faqs")
