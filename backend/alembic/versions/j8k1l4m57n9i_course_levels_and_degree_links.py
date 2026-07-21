"""course_levels lookup and education_degrees.course_level_id FK

Revision ID: j8k1l4m57n9i
Revises: i7j0k3l46m8h
Create Date: 2026-07-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j8k1l4m57n9i"
down_revision: Union[str, Sequence[str], None] = "i7j0k3l46m8h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COURSE_LEVEL_SEED = [
    ("ENTRY", "Entry", "Pre-university and foundational pathways.", 1),
    ("UNDERGRAD", "Undergraduate", "Undergraduate and bachelor-level study.", 2),
    ("GRADUATE", "Graduate", "Master's and post-bachelor graduate study.", 3),
    ("DOCTORAL", "Doctoral", "Doctorate and research-intensive doctoral study.", 4),
    ("CERT", "Certificate", "Professional certificates and credential programs.", 5),
]

# education_degrees.id -> course_levels.code
EDUCATION_DEGREE_ID_TO_LEVEL = {
    1: "ENTRY",
    14: "ENTRY",
    15: "ENTRY",
    16: "ENTRY",
    17: "ENTRY",
    2: "UNDERGRAD",
    3: "UNDERGRAD",
    6: "UNDERGRAD",
    7: "UNDERGRAD",
    8: "UNDERGRAD",
    11: "UNDERGRAD",
    4: "GRADUATE",
    9: "GRADUATE",
    10: "GRADUATE",
    5: "DOCTORAL",
    12: "CERT",
    13: "CERT",
}

ACADEMIC_DEGREE_CODE_TO_LEVEL = {
    "BACHELOR": "UNDERGRAD",
    "MASTER": "GRADUATE",
    "PHD": "DOCTORAL",
    "CERTIFICATE": "CERT",
}


def upgrade() -> None:
    op.create_table(
        "course_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("code", name="uq_course_levels_code"),
    )
    op.create_index("ix_course_levels_code", "course_levels", ["code"], unique=True)

    seed_table = sa.table(
        "course_levels",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        seed_table,
        [
            {
                "code": code,
                "name": name,
                "description": description,
                "sort_order": sort_order,
            }
            for code, name, description, sort_order in COURSE_LEVEL_SEED
        ],
    )

    op.add_column("education_degrees", sa.Column("course_level_id", sa.Integer(), nullable=True))
    op.add_column("academic_degrees", sa.Column("course_level_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    for degree_id, level_code in EDUCATION_DEGREE_ID_TO_LEVEL.items():
        bind.execute(
            sa.text(
                """
                UPDATE education_degrees
                SET course_level_id = (SELECT id FROM course_levels WHERE code = :level_code)
                WHERE id = :degree_id
                """
            ),
            {"degree_id": degree_id, "level_code": level_code},
        )

    bind.execute(
        sa.text(
            """
            UPDATE education_degrees
            SET course_level_id = (SELECT id FROM course_levels WHERE code = 'UNDERGRAD')
            WHERE course_level_id IS NULL
            """
        )
    )

    for degree_code, level_code in ACADEMIC_DEGREE_CODE_TO_LEVEL.items():
        bind.execute(
            sa.text(
                """
                UPDATE academic_degrees
                SET course_level_id = (SELECT id FROM course_levels WHERE code = :level_code)
                WHERE code = :degree_code
                """
            ),
            {"degree_code": degree_code, "level_code": level_code},
        )

    bind.execute(
        sa.text(
            """
            UPDATE academic_degrees
            SET course_level_id = (SELECT id FROM course_levels WHERE code = 'UNDERGRAD')
            WHERE course_level_id IS NULL
            """
        )
    )

    op.alter_column("education_degrees", "course_level_id", nullable=False)
    op.alter_column("academic_degrees", "course_level_id", nullable=False)

    op.create_foreign_key(
        "fk_education_degrees_course_level_id",
        "education_degrees",
        "course_levels",
        ["course_level_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_academic_degrees_course_level_id",
        "academic_degrees",
        "course_levels",
        ["course_level_id"],
        ["id"],
    )
    op.create_index("ix_education_degrees_course_level_id", "education_degrees", ["course_level_id"])
    op.create_index("ix_academic_degrees_course_level_id", "academic_degrees", ["course_level_id"])


def downgrade() -> None:
    op.drop_index("ix_academic_degrees_course_level_id", table_name="academic_degrees")
    op.drop_index("ix_education_degrees_course_level_id", table_name="education_degrees")
    op.drop_constraint("fk_academic_degrees_course_level_id", "academic_degrees", type_="foreignkey")
    op.drop_constraint("fk_education_degrees_course_level_id", "education_degrees", type_="foreignkey")
    op.drop_column("academic_degrees", "course_level_id")
    op.drop_column("education_degrees", "course_level_id")
    op.drop_index("ix_course_levels_code", table_name="course_levels")
    op.drop_table("course_levels")
