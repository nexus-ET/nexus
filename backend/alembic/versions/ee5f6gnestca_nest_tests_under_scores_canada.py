"""Add stage hide + nested sub-process parent for FlowX country boards.

Revision ID: ee5f6gnestca
Revises: dd4e5fbricksteps
Create Date: 2026-08-01

- flowx_stages.is_hidden: hide a process column (Canada Tests)
- flowx_task_templates.parent_template_id: nest bricks under a parent sub-process
- Canada-only data: move exam bricks under Standardized Test Scores as 3.2.1–3.2.3
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "ee5f6gnestca"
down_revision: Union[str, Sequence[str], None] = "dd4e5fbricksteps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flowx_stages",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "flowx_task_templates",
        sa.Column("parent_template_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_flowx_task_templates_parent",
        "flowx_task_templates",
        "flowx_task_templates",
        ["parent_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_flowx_task_templates_parent_template_id",
        "flowx_task_templates",
        ["parent_template_id"],
    )

    conn = op.get_bind()

    wf = conn.execute(
        sa.text(
            "SELECT id FROM flowx_country_workflows WHERE upper(country_iso2) = 'CA' LIMIT 1"
        )
    ).fetchone()
    if not wf:
        return
    wf_id = wf[0]

    parent = conn.execute(
        sa.text(
            """
            SELECT t.id, t.track_id
            FROM flowx_task_templates t
            JOIN flowx_tracks tr ON tr.id = t.track_id
            JOIN flowx_stages s ON s.id = tr.stage_id
            WHERE s.workflow_id = :wf
              AND s.stage_key = 'document_submission'
              AND lower(t.title) = lower('Standardized Test Scores')
            LIMIT 1
            """
        ),
        {"wf": wf_id},
    ).fetchone()
    if not parent:
        return
    parent_id, doc_track_id = parent[0], parent[1]

    children = conn.execute(
        sa.text(
            """
            SELECT t.id, t.title, t.position_index
            FROM flowx_task_templates t
            JOIN flowx_tracks tr ON tr.id = t.track_id
            JOIN flowx_stages s ON s.id = tr.stage_id
            WHERE s.workflow_id = :wf
              AND s.stage_key = 'tests'
              AND t.is_active IS TRUE
            ORDER BY t.position_index, t.title
            """
        ),
        {"wf": wf_id},
    ).fetchall()

    docs = conn.execute(
        sa.text(
            """
            SELECT t.id, t.title, t.position_index
            FROM flowx_task_templates t
            WHERE t.track_id = :track
            ORDER BY t.position_index, t.title
            """
        ),
        {"track": doc_track_id},
    ).fetchall()

    # Temporarily shift existing doc positions out of the way
    for row in docs:
        conn.execute(
            sa.text(
                "UPDATE flowx_task_templates SET position_index = :pos WHERE id = :id"
            ),
            {"pos": int(row[2]) + 100, "id": row[0]},
        )

    before_parent = [r for r in docs if r[0] != parent_id and int(r[2]) < 1]
    after_parent = [r for r in docs if r[0] != parent_id and int(r[2]) > 1]
    extras = [r for r in docs if r[0] != parent_id and int(r[2]) == 1]
    after_parent = extras + after_parent

    pos = 0
    for row in before_parent:
        conn.execute(
            sa.text(
                "UPDATE flowx_task_templates SET position_index = :pos, parent_template_id = NULL WHERE id = :id"
            ),
            {"pos": pos, "id": row[0]},
        )
        pos += 1

    conn.execute(
        sa.text(
            "UPDATE flowx_task_templates SET position_index = :pos, parent_template_id = NULL WHERE id = :id"
        ),
        {"pos": pos, "id": parent_id},
    )
    pos += 1

    preferred = [
        "confirm required tests",
        "book exam slot",
        "upload score report",
    ]

    def child_sort_key(row):
        title = (row[1] or "").strip().lower()
        try:
            return preferred.index(title)
        except ValueError:
            return 100 + int(row[2])

    child_ids = []
    for row in sorted(children, key=child_sort_key):
        child_ids.append(row[0])
        conn.execute(
            sa.text(
                """
                UPDATE flowx_task_templates
                SET track_id = :track,
                    parent_template_id = :parent,
                    position_index = :pos,
                    is_country_specific = TRUE
                WHERE id = :id
                """
            ),
            {"track": doc_track_id, "parent": parent_id, "pos": pos, "id": row[0]},
        )
        pos += 1

    for row in after_parent:
        conn.execute(
            sa.text(
                "UPDATE flowx_task_templates SET position_index = :pos, parent_template_id = NULL WHERE id = :id"
            ),
            {"pos": pos, "id": row[0]},
        )
        pos += 1

    conn.execute(
        sa.text(
            """
            UPDATE flowx_stages
            SET is_hidden = TRUE
            WHERE workflow_id = :wf AND stage_key = 'tests'
            """
        ),
        {"wf": wf_id},
    )

    if child_ids:
        for cid in child_ids:
            conn.execute(
                sa.text(
                    """
                    DELETE FROM flowx_subprocess_links
                    WHERE workflow_id = :wf
                      AND from_template_id = :parent
                      AND to_template_id = :kid
                    """
                ),
                {"wf": wf_id, "parent": parent_id, "kid": cid},
            )


def downgrade() -> None:
    op.drop_index("ix_flowx_task_templates_parent_template_id", table_name="flowx_task_templates")
    op.drop_constraint("fk_flowx_task_templates_parent", "flowx_task_templates", type_="foreignkey")
    op.drop_column("flowx_task_templates", "parent_template_id")
    op.drop_column("flowx_stages", "is_hidden")
