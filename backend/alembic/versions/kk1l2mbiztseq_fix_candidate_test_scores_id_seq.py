"""fix candidate_test_scores id sequence after imported rows

Revision ID: kk1l2mbiztseq
Revises: jj0k1lbizlogo
Create Date: 2026-08-08 17:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "kk1l2mbiztseq"
down_revision: Union[str, Sequence[str], None] = "jj0k1lbizlogo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('candidate_test_scores', 'id'),
            COALESCE((SELECT MAX(id) FROM candidate_test_scores), 1),
            (SELECT EXISTS (SELECT 1 FROM candidate_test_scores))
        )
        """
    )


def downgrade() -> None:
    pass
