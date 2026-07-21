"""enhance institutional hierarchy with accreditation, location, dean

Revision ID: e3f6g9h02i4d
Revises: d2e5f8g01h3c
Create Date: 2026-07-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f6g9h02i4d"
down_revision: Union[str, Sequence[str], None] = "d2e5f8g01h3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column("accreditation_details", sa.Text(), nullable=True),
    )

    op.add_column(
        "campuses",
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("geography_cities.id"), nullable=True),
    )
    op.create_index("ix_campuses_location_id", "campuses", ["location_id"])

    op.add_column(
        "colleges",
        sa.Column("dean_name", sa.String(length=255), nullable=True),
    )

    op.execute(
        """
        UPDATE colleges AS col
        SET institution_id = cam.institution_id
        FROM campuses AS cam
        WHERE col.campus_id = cam.id
          AND (col.institution_id IS NULL OR col.institution_id != cam.institution_id)
        """
    )
    op.execute("DELETE FROM colleges WHERE campus_id IS NULL")

    op.alter_column("colleges", "institution_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("colleges", "campus_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("colleges", "campus_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("colleges", "institution_id", existing_type=sa.Integer(), nullable=True)
    op.drop_column("colleges", "dean_name")

    op.drop_index("ix_campuses_location_id", table_name="campuses")
    op.drop_column("campuses", "location_id")

    op.drop_column("institutions", "accreditation_details")
