"""Add FlowX brick dashboard fields: links, unlink, template overrides.

Revision ID: c3d4e5flowxbrick
Revises: b2c3d4flowxcntry
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3d4e5flowxbrick"
down_revision = "b2c3d4flowxcntry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "flowx_task_templates",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("override_action", sa.String(32), nullable=True),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("override_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("overridden_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "flowx_subprocess_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_country_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_task_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_task_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(32), nullable=False, server_default="depends_on"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("from_template_id", "to_template_id", "link_type", name="uq_flowx_subprocess_link"),
    )
    op.create_index("idx_flowx_subprocess_links_workflow", "flowx_subprocess_links", ["workflow_id"])


def downgrade() -> None:
    op.drop_index("idx_flowx_subprocess_links_workflow", table_name="flowx_subprocess_links")
    op.drop_table("flowx_subprocess_links")
    op.drop_column("flowx_task_templates", "overridden_by")
    op.drop_column("flowx_task_templates", "overridden_at")
    op.drop_column("flowx_task_templates", "override_reason")
    op.drop_column("flowx_task_templates", "override_action")
    op.drop_column("flowx_task_templates", "is_optional")
    op.drop_column("flowx_task_templates", "is_active")
