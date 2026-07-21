"""Recreate programs table with education_major_id mapping.

Revision ID: s7t0u16v8w9x
Revises: r6s9t15u7v8w
Create Date: 2026-07-09 19:45:00.000000
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "s7t0u16v8w9x"
down_revision: Union[str, Sequence[str], None] = "r6s9t15u7v8w"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# level_code, education_major_code, program_code, name, description, sort_order
PROGRAM_MAJOR_SEED: list[tuple[str, str, str, str, str, int]] = [
    ("UNDERGRAD", "COMPUTER_SCIENCE", "BSC_CS", "BSc Computer Science", "Undergraduate computer science qualification.", 1),
    ("UNDERGRAD", "ENGINEERING", "BENG", "Bachelor of Engineering (BEng)", "Undergraduate engineering qualification.", 2),
    ("UNDERGRAD", "BUSINESS_ADMINISTRATION", "BBA", "Bachelor of Business Administration (BBA)", "Undergraduate business administration.", 3),
    ("UNDERGRAD", "MEDICINE", "MBBS", "Bachelor of Medicine, Bachelor of Surgery (MBBS)", "Undergraduate medical qualification.", 4),
    ("UNDERGRAD", "DATA_SCIENCE", "BSC_DS", "BSc Data Science", "Undergraduate data science qualification.", 5),
    ("UNDERGRAD", "FINANCE", "BSC_FIN", "BSc Finance", "Undergraduate finance qualification.", 6),
    ("UNDERGRAD", "LAW", "LLB", "Bachelor of Laws (LLB)", "Undergraduate law qualification.", 7),
    ("UNDERGRAD", "ARCHITECTURE", "BARCH", "Bachelor of Architecture", "Undergraduate architecture qualification.", 8),
    ("UNDERGRAD", "PSYCHOLOGY", "BA_PSYCH", "BA Psychology", "Undergraduate psychology qualification.", 9),
    ("UNDERGRAD", "BIOTECHNOLOGY", "BSC_BIO", "BSc Biotechnology", "Undergraduate biotechnology qualification.", 10),
    ("GRADUATE", "COMPUTER_SCIENCE", "MSC_CS", "MSc Computer Science", "Graduate computer science qualification.", 20),
    ("GRADUATE", "ENGINEERING", "MENG", "Master of Engineering (MEng)", "Graduate engineering qualification.", 21),
    ("GRADUATE", "BUSINESS_ADMINISTRATION", "MBA", "Master of Business Administration (MBA)", "Graduate business administration.", 22),
    ("GRADUATE", "DATA_SCIENCE", "MSC_DS", "MSc Data Science", "Graduate data science qualification.", 23),
    ("GRADUATE", "FINANCE", "MSC_FIN", "MSc Finance", "Graduate finance qualification.", 24),
    ("GRADUATE", "LAW", "LLM", "Master of Laws (LLM)", "Graduate law qualification.", 25),
    ("GRADUATE", "MEDICINE", "MSN", "Master of Science in Nursing (MSN)", "Graduate nursing qualification.", 26),
    ("GRADUATE", "PSYCHOLOGY", "MA_PSYCH", "MA Psychology", "Graduate psychology qualification.", 27),
    ("GRADUATE", "BIOTECHNOLOGY", "MSC_BIO", "MSc Biotechnology", "Graduate biotechnology qualification.", 28),
    ("GRADUATE", "ARCHITECTURE", "MARCH", "Master of Architecture", "Graduate architecture qualification.", 29),
    ("DOCTORAL", "COMPUTER_SCIENCE", "PHD_CS", "PhD Computer Science", "Doctoral computer science qualification.", 30),
    ("DOCTORAL", "ENGINEERING", "PHD_ENG", "PhD Engineering", "Doctoral engineering qualification.", 31),
    ("DOCTORAL", "MEDICINE", "MD", "Doctor of Medicine (MD)", "Doctoral medical qualification.", 32),
    ("DOCTORAL", "PSYCHOLOGY", "PHD_PSYCH", "PhD Psychology", "Doctoral psychology qualification.", 33),
    ("DOCTORAL", "BIOTECHNOLOGY", "PHD_BIO", "PhD Biotechnology", "Doctoral biotechnology qualification.", 34),
    ("CERT", "BUSINESS_ADMINISTRATION", "PGDIP_BA", "PG Diploma Business Administration", "Postgraduate business diploma.", 40),
    ("CERT", "FINANCE", "GRAD_CERT_FIN", "Graduate Certificate Finance", "Graduate finance certificate.", 41),
]


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("DELETE FROM institution_course_offerings"))
    bind.execute(sa.text("DELETE FROM target_courses"))
    bind.execute(sa.text("DELETE FROM target_programs"))

    op.execute("ALTER TABLE target_courses DROP CONSTRAINT IF EXISTS fk_target_courses_qualification_program_id")
    op.execute("ALTER TABLE target_programs DROP CONSTRAINT IF EXISTS fk_target_programs_program_id")

    op.drop_index("ix_programs_code", table_name="programs")
    op.drop_index("ix_programs_level_id", table_name="programs")
    op.drop_index("ix_programs_name", table_name="programs")
    op.drop_table("programs")

    op.create_table(
        "programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("levels.id"), nullable=False),
        sa.Column(
            "education_major_id",
            sa.Integer(),
            sa.ForeignKey("education_majors.id"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code", name="uq_programs_code"),
        sa.UniqueConstraint(
            "level_id",
            "education_major_id",
            name="uq_programs_level_education_major",
        ),
    )
    op.create_index("ix_programs_code", "programs", ["code"], unique=True)
    op.create_index("ix_programs_level_id", "programs", ["level_id"])
    op.create_index("ix_programs_education_major_id", "programs", ["education_major_id"])
    op.create_index("ix_programs_name", "programs", ["name"])

    op.create_foreign_key(
        "fk_target_programs_program_id",
        "target_programs",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_target_courses_qualification_program_id",
        "target_courses",
        "programs",
        ["qualification_program_id"],
        ["id"],
    )

    for level_code, major_code, program_code, name, description, sort_order in PROGRAM_MAJOR_SEED:
        bind.execute(
            sa.text(
                """
                INSERT INTO programs (
                    id, name, code, level_id, education_major_id, description, is_active, sort_order
                )
                SELECT
                    :id,
                    CAST(:name AS VARCHAR),
                    CAST(:program_code AS VARCHAR),
                    l.id,
                    em.id,
                    CAST(:description AS TEXT),
                    true,
                    :sort_order
                FROM levels l
                JOIN education_majors em ON em.code = CAST(:major_code AS VARCHAR)
                WHERE l.code = CAST(:level_code AS VARCHAR)
                  AND em.is_active = true
                """
            ),
            {
                "id": uuid.uuid4(),
                "level_code": level_code,
                "major_code": major_code,
                "program_code": program_code,
                "name": name,
                "description": description,
                "sort_order": sort_order,
            },
        )


def downgrade() -> None:
  raise NotImplementedError("Downgrade not supported for programs recreation.")
