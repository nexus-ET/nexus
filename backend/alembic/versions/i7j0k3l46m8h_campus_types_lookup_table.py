"""campus_types lookup table and campuses.campus_type_id FK

Revision ID: i7j0k3l46m8h
Revises: h6i9j2k35l7g
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i7j0k3l46m8h"
down_revision: Union[str, Sequence[str], None] = "h6i9j2k35l7g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAMPUS_TYPE_SEED = [
    (
        "MAIN",
        "Main",
        "The primary, flagship location housing central administration.",
    ),
    (
        "SATELLITE",
        "Satellite",
        "A secondary location serving specific regions or demographics.",
    ),
    (
        "SPECIALIZED",
        "Specialized",
        "A location dedicated to a specific academic niche (e.g., Medicine, Engineering).",
    ),
    (
        "INTERNATIONAL",
        "International",
        "A branch campus located outside the home country.",
    ),
    (
        "VIRTUAL",
        "Virtual",
        "An online-only platform for digital course delivery.",
    ),
]


def upgrade() -> None:
    op.create_table(
        "campus_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("code", name="uq_campus_types_code"),
    )
    op.create_index("ix_campus_types_code", "campus_types", ["code"], unique=True)

    seed_table = sa.table(
        "campus_types",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        seed_table,
        [
            {"code": code, "name": name, "description": description}
            for code, name, description in CAMPUS_TYPE_SEED
        ],
    )

    op.add_column("campuses", sa.Column("campus_type_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_campuses_campus_type_id",
        "campuses",
        "campus_types",
        ["campus_type_id"],
        ["id"],
    )
    op.create_index("ix_campuses_campus_type_id", "campuses", ["campus_type_id"])

    bind = op.get_bind()
    for code, _, _ in CAMPUS_TYPE_SEED:
        bind.execute(
            sa.text(
                """
                UPDATE campuses
                SET campus_type_id = (
                    SELECT id FROM campus_types WHERE code = :code
                )
                WHERE campus_type::text = :code
                """
            ),
            {"code": code},
        )

    op.drop_column("campuses", "type_description")
    op.drop_column("campuses", "campus_type")
    op.execute("DROP TYPE IF EXISTS campus_type_enum")


def downgrade() -> None:
    campus_type_enum = sa.Enum(
        "MAIN",
        "SATELLITE",
        "SPECIALIZED",
        "INTERNATIONAL",
        "VIRTUAL",
        name="campus_type_enum",
    )
    campus_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("campuses", sa.Column("campus_type", campus_type_enum, nullable=True))
    op.add_column("campuses", sa.Column("type_description", sa.Text(), nullable=True))

    bind = op.get_bind()
    for code, _, description in CAMPUS_TYPE_SEED:
        bind.execute(
            sa.text(
                """
                UPDATE campuses
                SET campus_type = CAST(:code AS campus_type_enum),
                    type_description = :description
                WHERE campus_type_id = (
                    SELECT id FROM campus_types WHERE code = :code
                )
                """
            ),
            {"code": code, "description": description},
        )

    op.drop_index("ix_campuses_campus_type_id", table_name="campuses")
    op.drop_constraint("fk_campuses_campus_type_id", "campuses", type_="foreignkey")
    op.drop_column("campuses", "campus_type_id")
    op.drop_index("ix_campus_types_code", table_name="campus_types")
    op.drop_table("campus_types")
