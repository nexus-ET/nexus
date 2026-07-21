"""fix countries ids 16-19 qatar netherlands russia hong kong

Revision ID: a3b6c9d02e4f
Revises: z2a5b8c13d4e
Create Date: 2026-07-06 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b6c9d02e4f"
down_revision: Union[str, Sequence[str], None] = "z2a5b8c13d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COUNTRY_UPDATES: list[tuple[int, str, str, str]] = [
    (16, "QA", "Qatar", "974"),
    (17, "NL", "Netherlands", "31"),
    (18, "RU", "Russia", "7"),
    (19, "HK", "Hong Kong", "852"),
]

_PREVIOUS_VALUES: list[tuple[int, str, str, str]] = [
    (16, "SA", "Saudi Arabia", "966"),
    (17, "PK", "Pakistan", "92"),
    (18, "BD", "Bangladesh", "880"),
    (19, "LK", "Sri Lanka", "94"),
]


def _apply_updates(values: list[tuple[int, str, str, str]]) -> None:
    connection = op.get_bind()
    for country_id, iso2, name, dial_code in values:
        connection.execute(
            sa.text(
                """
                UPDATE countries
                SET iso2 = :iso2, name = :name, dial_code = :dial_code
                WHERE id = :country_id
                """
            ),
            {"iso2": iso2, "name": name, "dial_code": dial_code, "country_id": country_id},
        )


def upgrade() -> None:
    _apply_updates(_COUNTRY_UPDATES)


def downgrade() -> None:
    _apply_updates(_PREVIOUS_VALUES)
