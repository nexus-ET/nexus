"""Seed framework qualification programs (BEng, BSc, MBA, etc.)

Revision ID: l0m3n6o79p1k
Revises: k9l2m5n68o0j
Create Date: 2026-07-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l0m3n6o79p1k"
down_revision: Union[str, Sequence[str], None] = "k9l2m5n68o0j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACADEMIC_PROGRAM_SEED = [
    ("BENG", "Bachelor of Engineering (BEng)", "UNDERGRAD", "Undergraduate engineering qualification.", 1),
    ("BSC", "Bachelor of Science (BSc)", "UNDERGRAD", "Undergraduate science qualification.", 2),
    ("BBA", "Bachelor of Business Administration (BBA)", "UNDERGRAD", "Undergraduate business administration.", 3),
    ("BA", "Bachelor of Arts (BA)", "UNDERGRAD", "Undergraduate arts and humanities qualification.", 4),
    ("LLB", "Bachelor of Laws (LLB)", "UNDERGRAD", "Undergraduate law qualification.", 5),
    ("MBBS", "Bachelor of Medicine, Bachelor of Surgery (MBBS)", "UNDERGRAD", "Undergraduate medical qualification.", 6),
    ("BDS", "Bachelor of Dental Surgery (BDS)", "UNDERGRAD", "Undergraduate dental qualification.", 7),
    ("BSN", "Bachelor of Science in Nursing (BSN)", "UNDERGRAD", "Undergraduate nursing qualification.", 8),
    ("MBA", "Master of Business Administration (MBA)", "GRADUATE", "Graduate business administration.", 10),
    ("MSC", "Master of Science (MSc)", "GRADUATE", "Graduate science qualification.", 11),
    ("MA", "Master of Arts (MA)", "GRADUATE", "Graduate arts and humanities qualification.", 12),
    ("MENG", "Master of Engineering (MEng)", "GRADUATE", "Graduate engineering qualification.", 13),
    ("LLM", "Master of Laws (LLM)", "GRADUATE", "Graduate law qualification.", 14),
    ("MSN", "Master of Science in Nursing (MSN)", "GRADUATE", "Graduate nursing qualification.", 15),
    ("PHD", "Doctor of Philosophy (PhD)", "DOCTORAL", "Doctoral research qualification.", 20),
    ("MD", "Doctor of Medicine (MD)", "DOCTORAL", "Doctoral medical qualification.", 21),
    ("PGDIP", "Postgraduate Diploma (PGDip)", "CERT", "Postgraduate diploma credential.", 30),
    ("GRAD_CERT", "Graduate Certificate", "CERT", "Graduate-level certificate program.", 31),
]

LEGACY_PROGRAM_CODES = ("BACHELOR", "MASTER", "CERTIFICATE")
LEGACY_PROGRAM_CODE_MAP = {
    "BACHELOR": "BSC",
    "MASTER": "MBA",
    "CERTIFICATE": "GRAD_CERT",
}

MAJOR_DEFAULT_PROGRAM_CODE = {
    "BUSINESS_MANAGEMENT": "BBA",
    "NURSING_MIDWIFERY": "BSN",
    "ALLIED_HEALTH": "BSC",
    "MEDICINE_DENTISTRY": "MBBS",
    "MEDICAL_SCIENCES": "MSC",
    "ENGINEERING_TECHNOLOGY": "BENG",
    "COMPUTER_SCIENCE_IT": "BSC",
    "HUMANITIES_SOCIAL_SCIENCES": "BA",
    "LAW_LEGAL_STUDIES": "LLB",
    "NATURAL_SCIENCES": "BSC",
}


def upgrade() -> None:
    bind = op.get_bind()

    for code, name, level_code, description, sort_order in ACADEMIC_PROGRAM_SEED:
        bind.execute(
            sa.text(
                """
                UPDATE academic_degrees
                SET name = CAST(:name AS VARCHAR),
                    description = CAST(:description AS TEXT),
                    sort_order = :sort_order,
                    course_level_id = (SELECT id FROM course_levels WHERE code = CAST(:level_code AS VARCHAR) LIMIT 1),
                    is_active = true
                WHERE code = CAST(:code AS VARCHAR)
                """
            ),
            {
                "code": code,
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "level_code": level_code,
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO academic_degrees (code, name, description, sort_order, course_level_id, is_active)
                SELECT CAST(:code AS VARCHAR),
                       CAST(:name AS VARCHAR),
                       CAST(:description AS TEXT),
                       :sort_order,
                       (SELECT id FROM course_levels WHERE code = CAST(:level_code AS VARCHAR) LIMIT 1),
                       true
                WHERE NOT EXISTS (SELECT 1 FROM academic_degrees WHERE code = CAST(:code AS VARCHAR))
                """
            ),
            {
                "code": code,
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "level_code": level_code,
            },
        )

    for legacy_code in LEGACY_PROGRAM_CODES:
        replacement_code = LEGACY_PROGRAM_CODE_MAP.get(legacy_code)
        if not replacement_code:
            continue
        bind.execute(
            sa.text(
                """
                UPDATE target_programs
                SET degree_id = (SELECT id FROM academic_degrees WHERE code = :replacement_code LIMIT 1)
                WHERE degree_id = (SELECT id FROM academic_degrees WHERE code = :legacy_code LIMIT 1)
                """
            ),
            {"legacy_code": legacy_code, "replacement_code": replacement_code},
        )
        bind.execute(
            sa.text(
                """
                UPDATE academic_degrees
                SET is_active = false
                WHERE code = :legacy_code
                """
            ),
            {"legacy_code": legacy_code},
        )

    for major_code, program_code in MAJOR_DEFAULT_PROGRAM_CODE.items():
        bind.execute(
            sa.text(
                """
                UPDATE target_programs
                SET degree_id = (SELECT id FROM academic_degrees WHERE code = :program_code LIMIT 1)
                WHERE code = :major_code
                """
            ),
            {"major_code": major_code, "program_code": program_code},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for legacy_code in LEGACY_PROGRAM_CODES:
        bind.execute(
            sa.text(
                """
                UPDATE academic_degrees
                SET is_active = true
                WHERE code = :legacy_code
                """
            ),
            {"legacy_code": legacy_code},
        )
    for code, _, _, _, _ in ACADEMIC_PROGRAM_SEED:
        if code in {"PHD", "MD"}:
            continue
        bind.execute(
            sa.text("DELETE FROM academic_degrees WHERE code = :code"),
            {"code": code},
        )
