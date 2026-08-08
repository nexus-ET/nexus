"""Add FlowX operational tables (pipelines, tracks, tasks, audit, rules).

Revision ID: a1b2c3flowxcore
Revises: y6z9a2bithreadsx
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3flowxcore"
down_revision = "y6z9a2bithreadsx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Skip if v1 pipelines already exist, or if country rebuild already applied.
    if inspector.has_table("flowx_pipelines") or inspector.has_table("flowx_country_workflows"):
        if not inspector.has_table("flowx_workflow_rules"):
            op.create_table(
                "flowx_workflow_rules",
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
                sa.Column("rule_name", sa.String(255), nullable=False),
                sa.Column("trigger_condition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
                sa.Column("action_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            )
        return

    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "flowx_pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("current_macro_stage", sa.String(32), nullable=False, server_default="documentation"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_pipelines_lead", "flowx_pipelines", ["lead_id"])
    op.create_index("idx_flowx_pipelines_status", "flowx_pipelines", ["status"])

    op.create_table(
        "flowx_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "pipeline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("track_name", sa.String(64), nullable=False),
        sa.Column("track_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("pipeline_id", "track_name", name="uq_flowx_tracks_pipeline_name"),
    )
    op.create_index("idx_flowx_tracks_pipeline", "flowx_tracks", ["pipeline_id"])

    op.create_table(
        "flowx_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kanban_status", sa.String(32), nullable=False, server_default="todo"),
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_status", sa.String(32), nullable=False, server_default="on_track"),
        sa.Column("is_auto_added", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_trigger_source", sa.String(128), nullable=True),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_tasks_track_status", "flowx_tasks", ["track_id", "kanban_status"])
    op.create_index("idx_flowx_tasks_sla", "flowx_tasks", ["sla_due_at"])

    op.create_table(
        "flowx_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "pipeline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("target_entity", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_audit_pipeline", "flowx_audit_logs", ["pipeline_id", "created_at"])

    op.create_table(
        "flowx_workflow_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("trigger_condition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("flowx_workflow_rules")
    op.drop_index("idx_flowx_audit_pipeline", table_name="flowx_audit_logs")
    op.drop_table("flowx_audit_logs")
    op.drop_index("idx_flowx_tasks_sla", table_name="flowx_tasks")
    op.drop_index("idx_flowx_tasks_track_status", table_name="flowx_tasks")
    op.drop_table("flowx_tasks")
    op.drop_index("idx_flowx_tracks_pipeline", table_name="flowx_tracks")
    op.drop_table("flowx_tracks")
    op.drop_index("idx_flowx_pipelines_status", table_name="flowx_pipelines")
    op.drop_index("idx_flowx_pipelines_lead", table_name="flowx_pipelines")
    op.drop_table("flowx_pipelines")
