"""Cascade-delete nested FlowX bricks when their parent is deleted.

Revision ID: gg7h8iparentcasc
Revises: ff6g7hmaster
Create Date: 2026-08-03

parent_template_id previously used ON DELETE SET NULL, which left nested
children behind as top-level orphans when a parent sub-process was deleted.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "gg7h8iparentcasc"
down_revision: Union[str, Sequence[str], None] = "ff6g7hmaster"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("flowx_task_templates"):
        return
    fks = {fk["name"]: fk for fk in inspector.get_foreign_keys("flowx_task_templates")}
    parent_fk = fks.get("fk_flowx_task_templates_parent")
    if parent_fk is not None and (parent_fk.get("options") or {}).get("ondelete") == "CASCADE":
        return
    if parent_fk is not None:
        op.drop_constraint(
            "fk_flowx_task_templates_parent",
            "flowx_task_templates",
            type_="foreignkey",
        )
    op.create_foreign_key(
        "fk_flowx_task_templates_parent",
        "flowx_task_templates",
        "flowx_task_templates",
        ["parent_template_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_flowx_task_templates_parent",
        "flowx_task_templates",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_flowx_task_templates_parent",
        "flowx_task_templates",
        "flowx_task_templates",
        ["parent_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
