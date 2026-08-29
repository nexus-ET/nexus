"""Add ranking, brochure, and expense text fields on institutions.

Revision ID: pp6q7rinstfields
Revises: oo5p6qsubmajors
Create Date: 2026-08-19 17:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "pp6q7rinstfields"
down_revision: Union[str, Sequence[str], None] = "oo5p6qsubmajors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS: tuple[str, ...] = (
    "year_established",
    "global_ranking",
    "national_ranking",
    "brochure_url",
    "tuition_fees",
    "hostel_expenses",
    "food_expense",
    "books_expense",
    "commutation_expense",
    "insurance_expense",
    "medical_expense",
    "other_expense",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("institutions", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("institutions", name)
