"""Reset education_majors to 13 catalog departments and add education_sub_majors.

Clears catalog-link dependents (mappings + nullable FKs), then reseeds majors
ids 1–13 and 65 sub-majors. Does not touch temp_programs_clone /
temp_universities_clone. Student/candidate free-text `major` columns are
unchanged.

Revision ID: oo5p6qsubmajors
Revises: nn4o5pcampus
Create Date: 2026-08-19 12:20:00.000000
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "oo5p6qsubmajors"
down_revision: Union[str, Sequence[str], None] = "nn4o5pcampus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAJOR_COLOR_PALETTE: tuple[str, ...] = (
    "#6366F1",
    "#8B5CF6",
    "#EC4899",
    "#F43F5E",
    "#F97316",
    "#EAB308",
    "#22C55E",
    "#14B8A6",
    "#06B6D4",
    "#3B82F6",
    "#A855F7",
    "#84CC16",
    "#D946EF",
)

EDUCATION_MAJORS: tuple[str, ...] = (
    "Computer Science & IT",
    "Business & Management",
    "Natural Sciences",
    "Engineering & Technology",
    "Humanities & Social Sciences",
    "Performing & Visual Arts",
    "Education",
    "Law & Legal Studies",
    "Architecture & Planning",
    "Design",
    "Social Work & Public Policy",
    "Agriculture & Veterinary Sciences",
    "Pharmacy & Pharmaceutical Sciences",
)

# (major_id, name) in display order; 65 rows.
EDUCATION_SUB_MAJORS: tuple[tuple[int, str], ...] = (
    (1, "Computer Science"),
    (1, "Data Science & AI"),
    (1, "Information Technology & Systems"),
    (1, "Cybersecurity"),
    (2, "MBA & General Management"),
    (2, "Finance, Accounting & Banking"),
    (2, "Marketing & Advertising"),
    (2, "Hospitality, Tourism, Events & Sport Management"),
    (2, "International Business & Trade"),
    (2, "Human Resources"),
    (2, "Supply Chain, Logistics & Operations"),
    (2, "Entrepreneurship & Innovation"),
    (2, "Project, Aviation & Real Estate Management"),
    (3, "Biology & Life Sciences"),
    (3, "Environmental, Earth & Geography"),
    (3, "Mathematics & Statistics"),
    (3, "Chemistry & Biochemistry"),
    (3, "Physics & Astronomy"),
    (3, "Sport, Exercise & Nutrition Science"),
    (3, "Biotechnology & Biomedical Science"),
    (3, "Forensic Science"),
    (3, "Other Natural Sciences"),
    (4, "General Engineering & Technology"),
    (4, "Electrical & Electronic"),
    (4, "Mechanical"),
    (4, "Civil & Structural"),
    (4, "Computer, Software & Robotics Engineering"),
    (4, "Chemical & Process"),
    (4, "Energy, Mining & Environmental"),
    (4, "Biomedical & Bioengineering"),
    (4, "Industrial, Manufacturing & Materials"),
    (4, "Aerospace & Aeronautical"),
    (5, "Languages, Linguistics & Literature"),
    (5, "History, Classics, Archaeology & Heritage"),
    (5, "Politics, IR & International Studies"),
    (5, "Sociology, Anthropology & Gender"),
    (5, "Psychology"),
    (5, "Media, Communication & Journalism"),
    (5, "Philosophy, Theology & Religion"),
    (5, "Economics"),
    (5, "Geography, Area & Development Studies"),
    (5, "Liberal Arts & Interdisciplinary Humanities"),
    (5, "Other HSS"),
    (6, "Music"),
    (6, "Film, TV, Animation & Photography"),
    (6, "Theatre, Drama & Dance"),
    (6, "Fine & Visual Arts"),
    (7, "Teacher Education & Pedagogy"),
    (7, "Early Childhood & Primary Education"),
    (8, "Criminology & Criminal Justice"),
    (8, "Law — qualifying, joint honours & legal studies"),
    (8, "Law"),
    (9, "Architecture"),
    (9, "Urban & Regional Planning"),
    (9, "Construction, Surveying & Built Environment"),
    (10, "Design (general, incl. interior)"),
    (10, "Fashion & Textile Design"),
    (10, "Graphic, Communication & Digital Design"),
    (10, "Industrial, Product & Game Design"),
    (11, "Social Work & Social Care"),
    (11, "Public Policy & Administration"),
    (12, "Agriculture, Food & Animal Sciences"),
    (12, "Veterinary Sciences"),
    (13, "Pharmaceutical Sciences & Pharmacology"),
    (13, "Pharmacy, professional"),
)


def _code_from_name(name: str) -> str:
    slug = name.upper().replace("&", " ").replace("/", " ")
    slug = re.sub(r"[^A-Z0-9]+", "_", slug).strip("_")
    return slug[:50]


def _reset_serial(bind, table: str) -> None:
    bind.execute(
        sa.text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                1,
                false
            )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    bind.execute(sa.text("DELETE FROM program_education_major_mappings"))
    bind.execute(sa.text("DELETE FROM course_education_major_mappings"))
    bind.execute(sa.text("DELETE FROM education_major_levels"))
    bind.execute(
        sa.text(
            "UPDATE education_courses SET education_major_id = NULL "
            "WHERE education_major_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE target_courses SET education_major_id = NULL "
            "WHERE education_major_id IS NOT NULL"
        )
    )
    bind.execute(sa.text("DELETE FROM education_majors"))
    _reset_serial(bind, "education_majors")
    _reset_serial(bind, "program_education_major_mappings")
    _reset_serial(bind, "course_education_major_mappings")

    insert_major = sa.text(
        """
        INSERT INTO education_majors (
            id, code, label, is_other, is_active, sort_order, color
        )
        VALUES (
            :id, :code, :label, false, true, :sort_order, :color
        )
        """
    )
    for index, label in enumerate(EDUCATION_MAJORS, start=1):
        bind.execute(
            insert_major,
            {
                "id": index,
                "code": _code_from_name(label),
                "label": label,
                "sort_order": index,
                "color": MAJOR_COLOR_PALETTE[index - 1],
            },
        )
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('education_majors', 'id'),
                COALESCE((SELECT MAX(id) FROM education_majors), 1),
                true
            )
            """
        )
    )

    if not inspector.has_table("education_sub_majors"):
        op.create_table(
            "education_sub_majors",
            sa.Column(
                "id",
                sa.Integer(),
                sa.Identity(always=False),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("major_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["major_id"],
                ["education_majors.id"],
                name="fk_education_sub_majors_major_id",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "major_id",
                "name",
                name="uq_education_sub_majors_major_id_name",
            ),
        )
        op.create_index(
            "ix_education_sub_majors_id",
            "education_sub_majors",
            ["id"],
        )
        op.create_index(
            "ix_education_sub_majors_major_id",
            "education_sub_majors",
            ["major_id"],
        )

    bind.execute(sa.text("DELETE FROM education_sub_majors"))
    _reset_serial(bind, "education_sub_majors")
    insert_sub = sa.text(
        """
        INSERT INTO education_sub_majors (name, major_id)
        VALUES (:name, :major_id)
        """
    )
    for major_id, name in EDUCATION_SUB_MAJORS:
        bind.execute(insert_sub, {"name": name, "major_id": major_id})
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('education_sub_majors', 'id'),
                COALESCE((SELECT MAX(id) FROM education_sub_majors), 1),
                true
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_education_sub_majors_major_id", table_name="education_sub_majors")
    op.drop_index("ix_education_sub_majors_id", table_name="education_sub_majors")
    op.drop_table("education_sub_majors")
    raise NotImplementedError(
        "Downgrade cannot restore the previous education_majors catalog."
    )
