"""add campus classification fields

Revision ID: h6i9j2k35l7g
Revises: g5h8i1j24k6f
Create Date: 2026-07-08 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h6i9j2k35l7g"
down_revision: Union[str, Sequence[str], None] = "g5h8i1j24k6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAMPUS_TYPE_ENUM = sa.Enum(
    "MAIN",
    "SATELLITE",
    "SPECIALIZED",
    "INTERNATIONAL",
    "VIRTUAL",
    name="campus_type_enum",
)


def upgrade() -> None:
    CAMPUS_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column("campuses", sa.Column("campus_type", CAMPUS_TYPE_ENUM, nullable=True))
    op.add_column("campuses", sa.Column("type_description", sa.Text(), nullable=True))
    op.add_column("campuses", sa.Column("is_residential", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("campuses", "is_residential")
    op.drop_column("campuses", "type_description")
    op.drop_column("campuses", "campus_type")
    CAMPUS_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
