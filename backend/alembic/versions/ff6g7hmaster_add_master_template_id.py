"""Link country FlowX bricks to Master Workflow templates.

Revision ID: ff6g7hmaster
Revises: ee5f6gnestca
Create Date: 2026-08-02

Adds flowx_task_templates.master_template_id so Master Workflow edits can
propagate to every country copy without relying on position matching alone.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "ff6g7hmaster"
down_revision: Union[str, Sequence[str], None] = "ee5f6gnestca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flowx_task_templates",
        sa.Column("master_template_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_flowx_task_templates_master_template_id",
        "flowx_task_templates",
        ["master_template_id"],
    )
    op.create_foreign_key(
        "fk_flowx_task_templates_master_template_id",
        "flowx_task_templates",
        "flowx_task_templates",
        ["master_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_flowx_task_templates_master_template_id",
        "flowx_task_templates",
        type_="foreignkey",
    )
    op.drop_index("ix_flowx_task_templates_master_template_id", table_name="flowx_task_templates")
    op.drop_column("flowx_task_templates", "master_template_id")
