"""Allow multi-country and multi-college FlowX enrollments per lead.

Revision ID: z9a2b5flowxapps
Revises: y6z9a2bithreadsx
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z9a2b5flowxapps"
down_revision: Union[str, Sequence[str], None] = ("u2p5r8frvisas", "y6z9a2bithreadsx")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uniques = {u["name"] for u in inspector.get_unique_constraints("flowx_enrollments")}
    indexes = {i["name"]: i for i in inspector.get_indexes("flowx_enrollments")}

    if "flowx_enrollments_lead_id_key" in uniques:
        op.drop_constraint("flowx_enrollments_lead_id_key", "flowx_enrollments", type_="unique")

    lead_idx = indexes.get("idx_flowx_enrollments_lead")
    if lead_idx is not None:
        op.drop_index("idx_flowx_enrollments_lead", table_name="flowx_enrollments")

    cols = {c["name"] for c in inspector.get_columns("flowx_enrollments")}
    if "institution_id" not in cols:
        op.add_column(
            "flowx_enrollments",
            sa.Column(
                "institution_id",
                sa.Integer(),
                sa.ForeignKey("institutions.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "college_id" not in cols:
        op.add_column(
            "flowx_enrollments",
            sa.Column(
                "college_id",
                sa.Integer(),
                sa.ForeignKey("colleges.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("flowx_enrollments")}
    if "idx_flowx_enrollments_lead" not in indexes:
        op.create_index("idx_flowx_enrollments_lead", "flowx_enrollments", ["lead_id"])
    if "idx_flowx_enrollments_institution" not in indexes:
        op.create_index("idx_flowx_enrollments_institution", "flowx_enrollments", ["institution_id"])
    if "idx_flowx_enrollments_college" not in indexes:
        op.create_index("idx_flowx_enrollments_college", "flowx_enrollments", ["college_id"])

    # One application per lead × country × college (NULL college treated as 0).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_flowx_enrollment_application
        ON flowx_enrollments (lead_id, country_workflow_id, (COALESCE(college_id, 0)))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_flowx_enrollment_application")
    op.drop_index("idx_flowx_enrollments_college", table_name="flowx_enrollments")
    op.drop_index("idx_flowx_enrollments_institution", table_name="flowx_enrollments")
    op.drop_index("idx_flowx_enrollments_lead", table_name="flowx_enrollments")
    op.drop_column("flowx_enrollments", "college_id")
    op.drop_column("flowx_enrollments", "institution_id")
    op.create_index("idx_flowx_enrollments_lead", "flowx_enrollments", ["lead_id"], unique=True)
