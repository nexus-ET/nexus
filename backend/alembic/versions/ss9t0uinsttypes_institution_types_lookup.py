"""institution_types lookup table and institutions.institution_type_id FK

Revision ID: ss9t0uinsttypes
Revises: rr8s9tsubmap
Create Date: 2026-08-20 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ss9t0uinsttypes"
down_revision: Union[str, Sequence[str], None] = "rr8s9tsubmap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INSTITUTION_TYPE_SEED = [
    ("PUBLIC_STATE", "Public / State", 1),
    ("PRIVATE", "Private", 2),
    ("COMMUNITY_COLLEGE", "Community College / Technical Institute", 3),
    ("OTHERS", "Others", 4),
]

OLD_TEXT_TO_CODE = {
    "Public / State University": "PUBLIC_STATE",
    "Public / State": "PUBLIC_STATE",
    "Private University": "PRIVATE",
    "Private": "PRIVATE",
    "Community College / Technical Institute": "COMMUNITY_COLLEGE",
    "Others": "OTHERS",
}


def upgrade() -> None:
    op.create_table(
        "institution_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code", name="uq_institution_types_code"),
    )
    op.create_index("ix_institution_types_code", "institution_types", ["code"], unique=True)

    seed_table = sa.table(
        "institution_types",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        seed_table,
        [
            {"code": code, "name": name, "is_active": True, "sort_order": sort_order}
            for code, name, sort_order in INSTITUTION_TYPE_SEED
        ],
    )

    op.add_column("institutions", sa.Column("institution_type_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_institutions_institution_type_id",
        "institutions",
        "institution_types",
        ["institution_type_id"],
        ["id"],
    )
    op.create_index(
        "ix_institutions_institution_type_id",
        "institutions",
        ["institution_type_id"],
    )

    bind = op.get_bind()
    for old_text, code in OLD_TEXT_TO_CODE.items():
        bind.execute(
            sa.text(
                """
                UPDATE institutions
                SET institution_type_id = (
                    SELECT id FROM institution_types WHERE code = :code
                )
                WHERE btrim(coalesce(institution_type, '')) = :old_text
                """
            ),
            {"code": code, "old_text": old_text},
        )

    # Index may be missing on fresh/bootstrapped DBs that never ran e9f2g8h0i1j2.
    op.drop_index(
        "ix_institutions_institution_type",
        table_name="institutions",
        if_exists=True,
    )
    op.drop_column("institutions", "institution_type", if_exists=True)


def downgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column("institution_type", sa.String(length=80), nullable=True),
    )
    op.create_index("ix_institutions_institution_type", "institutions", ["institution_type"])

    bind = op.get_bind()
    for code, name, _ in INSTITUTION_TYPE_SEED:
        bind.execute(
            sa.text(
                """
                UPDATE institutions
                SET institution_type = :name
                WHERE institution_type_id = (
                    SELECT id FROM institution_types WHERE code = :code
                )
                """
            ),
            {"code": code, "name": name},
        )

    op.drop_index(
        "ix_institutions_institution_type_id",
        table_name="institutions",
        if_exists=True,
    )
    op.drop_constraint("fk_institutions_institution_type_id", "institutions", type_="foreignkey")
    op.drop_column("institutions", "institution_type_id", if_exists=True)
    op.drop_index(
        "ix_institution_types_code",
        table_name="institution_types",
        if_exists=True,
    )
    op.drop_table("institution_types")
