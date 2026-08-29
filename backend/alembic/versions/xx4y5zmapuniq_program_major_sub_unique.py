"""Allow multiple sub-majors per program+major mapping.

Revision ID: xx4y5zmapuniq
Revises: ww3x4yprogurl
Create Date: 2026-08-23 18:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "xx4y5zmapuniq"
down_revision: Union[str, Sequence[str], None] = "ww3x4yprogurl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "program_education_major_mappings"
_OLD_UQ = "uq_program_education_major_mappings_program_major"
_UQ_SUB = "uq_pem_program_major_sub"
_UQ_NULL = "uq_pem_program_major_null_sub"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_OLD_UQ}")
    op.execute(f"DROP INDEX IF EXISTS {_OLD_UQ}")
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_UQ_SUB}
        ON {_TABLE} (program_id, education_major_id, education_sub_major_id)
        WHERE education_sub_major_id IS NOT NULL
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_UQ_NULL}
        ON {_TABLE} (program_id, education_major_id)
        WHERE education_sub_major_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_UQ_SUB}")
    op.execute(f"DROP INDEX IF EXISTS {_UQ_NULL}")
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_OLD_UQ}
        ON {_TABLE} (program_id, education_major_id)
        """
    )
