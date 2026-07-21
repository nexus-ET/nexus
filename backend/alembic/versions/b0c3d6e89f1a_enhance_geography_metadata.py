"""enhance geography hierarchy with metadata fields

Revision ID: b0c3d6e89f1a
Revises: a9b2c5d78e0f
Create Date: 2026-07-07 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b0c3d6e89f1a"
down_revision: Union[str, Sequence[str], None] = "a9b2c5d78e0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("geography_states", "code", new_column_name="region_code")

    op.add_column(
        "geography_cities",
        sa.Column("time_zone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "geography_cities",
        sa.Column("postal_code_prefix", sa.String(length=20), nullable=True),
    )

    op.execute(
        """
        UPDATE geography_cities
        SET state_id = (
            SELECT gs.id
            FROM geography_states gs
            WHERE gs.country_id = geography_cities.country_id
            ORDER BY gs.id
            LIMIT 1
        )
        WHERE state_id IS NULL
        """
    )
    op.alter_column("geography_cities", "state_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("geography_cities", "state_id", existing_type=sa.Integer(), nullable=True)
    op.drop_column("geography_cities", "postal_code_prefix")
    op.drop_column("geography_cities", "time_zone")
    op.alter_column("geography_states", "region_code", new_column_name="code")
