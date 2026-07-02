"""add status_history table (replaces lead_status_history)

Revision ID: o1k4l9m03n5i
Revises: n0j3k8l92m4h
Create Date: 2026-06-13 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1k4l9m03n5i"
down_revision: Union[str, Sequence[str], None] = "n0j3k8l92m4h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(name)


def upgrade() -> None:
    if _has_table("lead_status_history") and not _has_table("status_history"):
        op.rename_table("lead_status_history", "status_history")
        op.alter_column("status_history", "lead_id", new_column_name="student_id")
        op.alter_column("status_history", "status_definition_id", new_column_name="status_id")
        op.alter_column("status_history", "counsellor_id", new_column_name="changed_by_user_id")
        op.alter_column("status_history", "notes", new_column_name="comments")
        op.add_column(
            "status_history",
            sa.Column(
                "changed_by_type",
                sa.Enum("system", "admin", name="status_changed_by_type", native_enum=False),
                nullable=True,
            ),
        )
        op.execute(
            """
            UPDATE status_history
            SET changed_by_type = CASE
                WHEN changed_by_user_id IS NOT NULL THEN 'admin'
                ELSE 'system'
            END
            """
        )
        op.alter_column("status_history", "changed_by_type", nullable=False)
        return

    if not _has_table("status_history"):
        op.create_table(
            "status_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("status_id", sa.Integer(), nullable=False),
            sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
            sa.Column(
                "changed_by_type",
                sa.Enum("system", "admin", name="status_changed_by_type", native_enum=False),
                nullable=False,
            ),
            sa.Column("comments", sa.Text(), nullable=True),
            sa.Column("booking_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["booking_id"], ["counselling_bookings.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["status_id"], ["status_definitions.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["student_id"], ["leads.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_status_history_id", "status_history", ["id"])
        op.create_index("ix_status_history_student_id", "status_history", ["student_id"])
        op.create_index("ix_status_history_status_id", "status_history", ["status_id"])
        op.create_index("ix_status_history_changed_by_user_id", "status_history", ["changed_by_user_id"])
        op.create_index("ix_status_history_changed_by_type", "status_history", ["changed_by_type"])
        op.create_index("ix_status_history_booking_id", "status_history", ["booking_id"])
        op.create_index("ix_status_history_created_at", "status_history", ["created_at"])


def downgrade() -> None:
    if _has_table("status_history") and not _has_table("lead_status_history"):
        op.alter_column("status_history", "comments", new_column_name="notes")
        op.alter_column("status_history", "changed_by_user_id", new_column_name="counsellor_id")
        op.alter_column("status_history", "status_id", new_column_name="status_definition_id")
        op.alter_column("status_history", "student_id", new_column_name="lead_id")
        op.drop_column("status_history", "changed_by_type")
        op.rename_table("status_history", "lead_status_history")
