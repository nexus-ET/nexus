"""update education_degrees catalog with secondary school levels

Revision ID: d6e9f2g47h7i
Revises: c5d8e1f36g6h
Create Date: 2026-07-06 25:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6e9f2g47h7i"
down_revision: Union[str, Sequence[str], None] = "c5d8e1f36g6h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EDUCATION_DEGREES: list[tuple[str, str, int, bool]] = [
    ("SECONDARY_SCHOOL", "Secondary (Grade 9–10)", 1, False),
    ("SENIOR_SECONDARY", "Senior Secondary (Grade 11–12)", 2, False),
    ("HIGH_SCHOOL_DIPLOMA_GED", "High School Diploma / GED", 3, False),
    ("SOME_COLLEGE_NO_DEGREE", "Some College (No Degree)", 4, False),
    ("ASSOCIATE_DEGREE", "Associate Degree (AA/AS)", 5, False),
    ("BACHELORS_3Y_INTERNATIONAL", "Bachelor's (3-Year International)", 6, False),
    ("BACHELORS_4Y_INTERNATIONAL", "Bachelor's (4-Year International)", 7, False),
    ("BACHELORS_DEGREE", "Bachelor's Degree (BA/BS/B.Tech)", 8, False),
    ("INTEGRATED_MASTERS", "Integrated Master's", 9, False),
    ("MASTERS_DEGREE", "Master's Degree (MA/MS/MBA/M.Tech)", 10, False),
    ("POST_GRADUATE_DIPLOMA", "Post-Graduate Diploma (PGD)", 11, False),
    ("PROFESSIONAL_DEGREE", "Professional Degree (JD/MD)", 12, False),
    ("DOCTORATE", "Doctorate (PhD/EdD)", 13, False),
    ("STEM_DESIGNATED", "STEM-Designated Degree", 14, False),
    ("BOOTCAMP_GRADUATE", "Bootcamp Graduate", 15, False),
    ("PROFESSIONAL_CERTIFICATION_ONLY", "Professional Certification Only", 16, False),
    ("OTHER", "Other", 99, True),
]

_PREVIOUS_EDUCATION_DEGREES: list[tuple[str, str, int, bool]] = [
    ("HIGH_SCHOOL_DIPLOMA_GED", "High School Diploma / GED", 1, False),
    ("ASSOCIATE_DEGREE", "Associate Degree (AA/AS)", 2, False),
    ("BACHELORS_DEGREE", "Bachelor's Degree (BA/BS/B.Tech)", 3, False),
    ("MASTERS_DEGREE", "Master's Degree (MA/MS/MBA/M.Tech)", 4, False),
    ("DOCTORATE", "Doctorate (PhD/EdD)", 5, False),
    ("PROFESSIONAL_DEGREE", "Professional Degree (JD/MD)", 6, False),
    ("BACHELORS_3Y_INTERNATIONAL", "Bachelor's (3-Year International)", 7, False),
    ("BACHELORS_4Y_INTERNATIONAL", "Bachelor's (4-Year International)", 8, False),
    ("POST_GRADUATE_DIPLOMA", "Post-Graduate Diploma (PGD)", 9, False),
    ("INTEGRATED_MASTERS", "Integrated Master's", 10, False),
    ("STEM_DESIGNATED", "STEM-Designated Degree", 11, False),
    ("BOOTCAMP_GRADUATE", "Bootcamp Graduate", 12, False),
    ("PROFESSIONAL_CERTIFICATION_ONLY", "Professional Certification Only", 13, False),
    ("SOME_COLLEGE_NO_DEGREE", "Some College (No Degree)", 14, False),
    ("OTHER", "Other", 99, True),
]

_NEW_CODES = {"SECONDARY_SCHOOL", "SENIOR_SECONDARY"}


def _upsert_degrees(degrees: list[tuple[str, str, int, bool]]) -> None:
    connection = op.get_bind()
    for code, label, sort_order, is_other in degrees:
        connection.execute(
            sa.text(
                """
                INSERT INTO education_degrees (code, label, sort_order, is_other, is_active)
                VALUES (:code, :label, :sort_order, :is_other, true)
                ON CONFLICT (code) DO UPDATE SET
                    label = EXCLUDED.label,
                    sort_order = EXCLUDED.sort_order,
                    is_other = EXCLUDED.is_other,
                    is_active = true
                """
            ),
            {
                "code": code,
                "label": label,
                "sort_order": sort_order,
                "is_other": is_other,
            },
        )


def upgrade() -> None:
    _upsert_degrees(_EDUCATION_DEGREES)


def downgrade() -> None:
    _upsert_degrees(_PREVIOUS_EDUCATION_DEGREES)
    connection = op.get_bind()
    for code in _NEW_CODES:
        connection.execute(
            sa.text(
                """
                UPDATE education_degrees
                SET is_active = false
                WHERE code = :code
                """
            ),
            {"code": code},
        )
