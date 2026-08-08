"""Rebuild FlowX around country workflows, stages, templates, and enrollments.

Revision ID: b2c3d4flowxcntry
Revises: a1b2c3flowxcore
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4flowxcntry"
down_revision = "a1b2c3flowxcore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Already on country-workflow schema (common when staging was synced from develop).
    if inspector.has_table("flowx_country_workflows"):
        return

    # Drop lead-centric v1 tables (re-anchor to country templates).
    if inspector.has_table("flowx_audit_logs"):
        indexes = {i["name"] for i in inspector.get_indexes("flowx_audit_logs")}
        if "idx_flowx_audit_pipeline" in indexes:
            op.drop_index("idx_flowx_audit_pipeline", table_name="flowx_audit_logs")
        op.drop_table("flowx_audit_logs")
    if inspector.has_table("flowx_tasks"):
        indexes = {i["name"] for i in inspector.get_indexes("flowx_tasks")}
        if "idx_flowx_tasks_sla" in indexes:
            op.drop_index("idx_flowx_tasks_sla", table_name="flowx_tasks")
        if "idx_flowx_tasks_track_status" in indexes:
            op.drop_index("idx_flowx_tasks_track_status", table_name="flowx_tasks")
        op.drop_table("flowx_tasks")
    if inspector.has_table("flowx_tracks"):
        indexes = {i["name"] for i in inspector.get_indexes("flowx_tracks")}
        if "idx_flowx_tracks_pipeline" in indexes:
            op.drop_index("idx_flowx_tracks_pipeline", table_name="flowx_tracks")
        op.drop_table("flowx_tracks")
    if inspector.has_table("flowx_pipelines"):
        indexes = {i["name"] for i in inspector.get_indexes("flowx_pipelines")}
        if "idx_flowx_pipelines_status" in indexes:
            op.drop_index("idx_flowx_pipelines_status", table_name="flowx_pipelines")
        if "idx_flowx_pipelines_lead" in indexes:
            op.drop_index("idx_flowx_pipelines_lead", table_name="flowx_pipelines")
        op.drop_table("flowx_pipelines")
    # Keep flowx_workflow_rules.

    op.create_table(
        "flowx_country_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("country_iso2", sa.String(2), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_workflows_iso2", "flowx_country_workflows", ["country_iso2"])
    op.create_index("idx_flowx_workflows_status", "flowx_country_workflows", ["status"])

    op.create_table(
        "flowx_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_country_workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workflow_id", "stage_key", name="uq_flowx_stages_workflow_key"),
    )
    op.create_index("idx_flowx_stages_workflow", "flowx_stages", ["workflow_id"])

    op.create_table(
        "flowx_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_stages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("track_name", sa.String(64), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("stage_id", "track_name", name="uq_flowx_tracks_stage_name"),
    )
    op.create_index("idx_flowx_tracks_stage", "flowx_tracks", ["stage_id"])

    op.create_table(
        "flowx_task_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sla_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("is_country_specific", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auto_trigger_source", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_task_templates_track", "flowx_task_templates", ["track_id"])

    op.create_table(
        "flowx_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column(
            "country_workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_country_workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_stage_key", sa.String(64), nullable=False, server_default="counselling"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_enrollments_lead", "flowx_enrollments", ["lead_id"])
    op.create_index("idx_flowx_enrollments_workflow", "flowx_enrollments", ["country_workflow_id"])
    op.create_index("idx_flowx_enrollments_status", "flowx_enrollments", ["status"])

    op.create_table(
        "flowx_enrollment_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "enrollment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("track_name", sa.String(64), nullable=False),
        sa.Column("track_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("enrollment_id", "stage_key", "track_name", name="uq_flowx_enroll_track"),
    )
    op.create_index("idx_flowx_enroll_tracks_enrollment", "flowx_enrollment_tracks", ["enrollment_id"])

    op.create_table(
        "flowx_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "enrollment_track_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_enrollment_tracks.id", ondelete="CASCADE"),
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
    op.create_index("idx_flowx_tasks_enroll_track", "flowx_tasks", ["enrollment_track_id", "kanban_status"])
    op.create_index("idx_flowx_tasks_sla", "flowx_tasks", ["sla_due_at"])

    op.create_table(
        "flowx_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "enrollment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flowx_enrollments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("target_entity", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_flowx_audit_enrollment", "flowx_audit_logs", ["enrollment_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_flowx_audit_enrollment", table_name="flowx_audit_logs")
    op.drop_table("flowx_audit_logs")
    op.drop_index("idx_flowx_tasks_sla", table_name="flowx_tasks")
    op.drop_index("idx_flowx_tasks_enroll_track", table_name="flowx_tasks")
    op.drop_table("flowx_tasks")
    op.drop_index("idx_flowx_enroll_tracks_enrollment", table_name="flowx_enrollment_tracks")
    op.drop_table("flowx_enrollment_tracks")
    op.drop_index("idx_flowx_enrollments_status", table_name="flowx_enrollments")
    op.drop_index("idx_flowx_enrollments_workflow", table_name="flowx_enrollments")
    op.drop_index("idx_flowx_enrollments_lead", table_name="flowx_enrollments")
    op.drop_table("flowx_enrollments")
    op.drop_index("idx_flowx_task_templates_track", table_name="flowx_task_templates")
    op.drop_table("flowx_task_templates")
    op.drop_index("idx_flowx_tracks_stage", table_name="flowx_tracks")
    op.drop_table("flowx_tracks")
    op.drop_index("idx_flowx_stages_workflow", table_name="flowx_stages")
    op.drop_table("flowx_stages")
    op.drop_index("idx_flowx_workflows_status", table_name="flowx_country_workflows")
    op.drop_index("idx_flowx_workflows_iso2", table_name="flowx_country_workflows")
    op.drop_table("flowx_country_workflows")
