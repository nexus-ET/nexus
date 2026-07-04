"""Add status_transitions table for forward, express, backward, and relaunch paths

Revision ID: r4n7o2p36q8l
Revises: q3m6n1o25p7k
Create Date: 2026-07-04 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "r4n7o2p36q8l"
down_revision: Union[str, Sequence[str], None] = "q3m6n1o25p7k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUM_NAME = "status_transition_type"
ENUM_VALUES = ("forward", "backward", "express", "relaunch")


def _enum_exists(bind) -> bool:
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
            {"name": ENUM_NAME},
        ).scalar()
        is not None
    )


def _ensure_enum(bind) -> None:
    if _enum_exists(bind):
        return
    values = ", ".join(f"'{value}'" for value in ENUM_VALUES)
    op.execute(sa.text(f"CREATE TYPE {ENUM_NAME} AS ENUM ({values})"))


def _seed_transitions() -> None:
    op.execute(
        """
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
        SELECT id, next_stage_id, 'forward'
        FROM status_definitions
        WHERE next_stage_id IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type) VALUES
        (1, 10, 'express'),
        (3, 16, 'express'),
        (11, 23, 'express')
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type) VALUES
        (38, 39, 'relaunch')
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
        SELECT to_status_id, from_status_id, 'backward'
        FROM status_transitions
        WHERE transition_type = 'forward'
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_enum(bind)

    transition_type_enum = postgresql.ENUM(
        *ENUM_VALUES,
        name=ENUM_NAME,
        create_type=False,
    )

    inspector = inspect(bind)
    if not inspector.has_table("status_transitions"):
        op.create_table(
            "status_transitions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("from_status_id", sa.Integer(), nullable=False),
            sa.Column("to_status_id", sa.Integer(), nullable=False),
            sa.Column("transition_type", transition_type_enum, nullable=False),
            sa.ForeignKeyConstraint(
                ["from_status_id"], ["status_definitions.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["to_status_id"], ["status_definitions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "from_status_id",
                "to_status_id",
                "transition_type",
                name="uq_status_transitions_from_to_type",
            ),
        )
        op.create_index(
            "ix_status_transitions_from_status_id",
            "status_transitions",
            ["from_status_id"],
        )
        op.create_index(
            "ix_status_transitions_to_status_id",
            "status_transitions",
            ["to_status_id"],
        )
        op.create_index(
            "ix_status_transitions_transition_type",
            "status_transitions",
            ["transition_type"],
        )

    _seed_transitions()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("status_transitions"):
        op.drop_index("ix_status_transitions_transition_type", table_name="status_transitions")
        op.drop_index("ix_status_transitions_to_status_id", table_name="status_transitions")
        op.drop_index("ix_status_transitions_from_status_id", table_name="status_transitions")
        op.drop_table("status_transitions")

    if _enum_exists(bind):
        op.execute(sa.text(f"DROP TYPE {ENUM_NAME}"))
