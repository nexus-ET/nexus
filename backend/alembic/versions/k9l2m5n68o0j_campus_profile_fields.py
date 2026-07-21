"""campus profile fields for wizard step 2

Revision ID: k9l2m5n68o0j
Revises: j8k1l4m57n9i
Create Date: 2026-07-08 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k9l2m5n68o0j"
down_revision: Union[str, Sequence[str], None] = "j8k1l4m57n9i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("campuses", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("campuses", sa.Column("address", sa.String(length=200), nullable=True))
    op.add_column("campuses", sa.Column("country_id", sa.Integer(), nullable=True))
    op.add_column("campuses", sa.Column("state_id", sa.Integer(), nullable=True))
    op.add_column("campuses", sa.Column("zipcode", sa.String(length=10), nullable=True))
    op.add_column("campuses", sa.Column("phone_numbers", sa.JSON(), nullable=True))
    op.add_column("campuses", sa.Column("fax_number", sa.String(length=50), nullable=True))
    op.add_column("campuses", sa.Column("email_addresses", sa.JSON(), nullable=True))

    op.create_foreign_key(
        "fk_campuses_country_id",
        "campuses",
        "countries",
        ["country_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_campuses_state_id",
        "campuses",
        "geography_states",
        ["state_id"],
        ["id"],
    )
    op.create_index("ix_campuses_country_id", "campuses", ["country_id"])
    op.create_index("ix_campuses_state_id", "campuses", ["state_id"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE campuses
            SET phone_numbers = '[]'::json,
                email_addresses = '[]'::json
            WHERE phone_numbers IS NULL OR email_addresses IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_campuses_state_id", table_name="campuses")
    op.drop_index("ix_campuses_country_id", table_name="campuses")
    op.drop_constraint("fk_campuses_state_id", "campuses", type_="foreignkey")
    op.drop_constraint("fk_campuses_country_id", "campuses", type_="foreignkey")
    op.drop_column("campuses", "email_addresses")
    op.drop_column("campuses", "fax_number")
    op.drop_column("campuses", "phone_numbers")
    op.drop_column("campuses", "zipcode")
    op.drop_column("campuses", "state_id")
    op.drop_column("campuses", "country_id")
    op.drop_column("campuses", "address")
    op.drop_column("campuses", "description")
