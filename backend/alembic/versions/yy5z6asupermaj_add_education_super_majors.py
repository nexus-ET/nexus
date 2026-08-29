"""Add education_super_majors and map catalog majors.

Revision ID: yy5z6asupermaj
Revises: xx4y5zmapuniq
Create Date: 2026-08-26 17:20:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "yy5z6asupermaj"
down_revision: Union[str, Sequence[str], None] = "xx4y5zmapuniq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPER_MAJORS: list[tuple[str, str, int]] = [
    ("Accounting, Commerce & Economics", "ACCOUNTING_COMMERCE_ECONOMICS", 1),
    ("Agriculture, Animal & Veterinary Science", "AGRICULTURE_ANIMAL_VETERINARY_SCIENCE", 2),
    ("Allied Health", "ALLIED_HEALTH", 3),
    ("Architecture & Design", "ARCHITECTURE_DESIGN", 4),
    ("Arts, Humanities & Social Sciences", "ARTS_HUMANITIES_SOCIAL_SCIENCES", 5),
    ("Aviation", "AVIATION", 6),
    ("Business, Marketing & Management", "BUSINESS_MARKETING_MANAGEMENT", 7),
    ("Computer Science & Information Technology", "COMPUTER_SCIENCE_INFORMATION_TECHNOLOGY", 8),
    ("Creative, Media & Communication", "CREATIVE_MEDIA_COMMUNICATION", 9),
    ("Engineering", "ENGINEERING", 10),
    ("Health & Biomedical Sciences", "HEALTH_BIOMEDICAL_SCIENCES", 11),
    ("Law & Justice", "LAW_JUSTICE", 12),
    ("Mathematics", "MATHEMATICS", 13),
    ("Medicine, Dentistry & Oral Health", "MEDICINE_DENTISTRY_ORAL_HEALTH", 14),
    ("Music", "MUSIC", 15),
    ("Nursing & Midwifery", "NURSING_MIDWIFERY", 16),
    ("Nutrition & Food Science", "NUTRITION_FOOD_SCIENCE", 17),
    ("Property, Construction & Real Estate", "PROPERTY_CONSTRUCTION_REAL_ESTATE", 18),
    ("Psychology & Social Work", "PSYCHOLOGY_SOCIAL_WORK", 19),
    ("Science, Environment & Sustainability", "SCIENCE_ENVIRONMENT_SUSTAINABILITY", 20),
    ("Teaching & Education", "TEACHING_EDUCATION", 21),
    ("Tourism, Sport & Events", "TOURISM_SPORT_EVENTS", 22),
]

# Catalog major label → super-major marketing name
MAJOR_TO_SUPER: dict[str, str] = {
    "Agriculture & Food Sciences": "Agriculture, Animal & Veterinary Science",
    "Architecture & Planning": "Architecture & Design",
    "Artificial Intelligence": "Computer Science & Information Technology",
    "Arts & Design": "Architecture & Design",
    "Aviation": "Aviation",
    "Beauty and Wellness": "Allied Health",
    "Business & Management": "Business, Marketing & Management",
    "Computer Science": "Computer Science & Information Technology",
    "Cybersecurity": "Computer Science & Information Technology",
    "Data Science": "Computer Science & Information Technology",
    "Education & Training": "Teaching & Education",
    "Engineering": "Engineering",
    "Film & Photography": "Creative, Media & Communication",
    "Fine & Visual Arts": "Creative, Media & Communication",
    "Health Sciences": "Health & Biomedical Sciences",
    "Hospitality & Tourism": "Tourism, Sport & Events",
    "Humanities": "Arts, Humanities & Social Sciences",
    "Information Technology": "Computer Science & Information Technology",
    "Languages & Linguistics": "Arts, Humanities & Social Sciences",
    "Law & Legal": "Law & Justice",
    "Life Sciences": "Science, Environment & Sustainability",
    "Medical Sciences": "Medicine, Dentistry & Oral Health",
    "Pharmacy and Pharmaceutical Sciences": "Health & Biomedical Sciences",
    "Physical Sciences": "Science, Environment & Sustainability",
    "Public Health Informatics": "Health & Biomedical Sciences",
    "Public Policy & Social Work": "Psychology & Social Work",
    "Social Sciences": "Arts, Humanities & Social Sciences",
    "Sport and Exercise Science": "Tourism, Sport & Events",
    "Theology & Religious": "Arts, Humanities & Social Sciences",
    "Trades & Vocational Skills": "Property, Construction & Real Estate",
    "Veterinary Sciences": "Agriculture, Animal & Veterinary Science",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "education_super_majors" not in tables:
        op.create_table(
            "education_super_majors",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.UniqueConstraint("name", name="uq_education_super_majors_name"),
            sa.UniqueConstraint("code", name="uq_education_super_majors_code"),
        )
        op.create_index(
            "ix_education_super_majors_id",
            "education_super_majors",
            ["id"],
        )
        op.create_index(
            "ix_education_super_majors_code",
            "education_super_majors",
            ["code"],
        )

    major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
    if "super_major_id" not in major_cols:
        op.add_column(
            "education_majors",
            sa.Column("super_major_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_education_majors_super_major_id",
            "education_majors",
            "education_super_majors",
            ["super_major_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_education_majors_super_major_id",
            "education_majors",
            ["super_major_id"],
        )

    for name, code, sort_order in SUPER_MAJORS:
        bind.execute(
            sa.text(
                """
                INSERT INTO education_super_majors (name, code, description, sort_order, is_active)
                SELECT CAST(:name AS VARCHAR(255)), CAST(:code AS VARCHAR(80)), NULL, :sort_order, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM education_super_majors
                    WHERE code = CAST(:code AS VARCHAR(80))
                       OR name = CAST(:name AS VARCHAR(255))
                )
                """
            ),
            {"name": name, "code": code, "sort_order": sort_order},
        )

    for major_label, super_name in MAJOR_TO_SUPER.items():
        bind.execute(
            sa.text(
                """
                UPDATE education_majors AS em
                SET super_major_id = sm.id
                FROM education_super_majors AS sm
                WHERE em.program_id IS NULL
                  AND em.label = CAST(:major_label AS VARCHAR(255))
                  AND sm.name = CAST(:super_name AS VARCHAR(255))
                """
            ),
            {"major_label": major_label, "super_name": super_name},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "education_majors" in tables:
        major_cols = {c["name"] for c in inspector.get_columns("education_majors")}
        fks = {fk["name"] for fk in inspector.get_foreign_keys("education_majors")}
        indexes = {ix["name"] for ix in inspector.get_indexes("education_majors")}
        if "fk_education_majors_super_major_id" in fks:
            op.drop_constraint(
                "fk_education_majors_super_major_id",
                "education_majors",
                type_="foreignkey",
            )
        if "ix_education_majors_super_major_id" in indexes:
            op.drop_index(
                "ix_education_majors_super_major_id",
                table_name="education_majors",
            )
        if "super_major_id" in major_cols:
            op.drop_column("education_majors", "super_major_id")

    if "education_super_majors" in tables:
        op.drop_index("ix_education_super_majors_code", table_name="education_super_majors")
        op.drop_index("ix_education_super_majors_id", table_name="education_super_majors")
        op.drop_table("education_super_majors")
