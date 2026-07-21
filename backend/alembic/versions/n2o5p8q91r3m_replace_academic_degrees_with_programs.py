"""replace academic_degrees with programs table (UUID)

Revision ID: n2o5p8q91r3m
Revises: m1n4o7p80q2l
Create Date: 2026-07-08 20:00:00.000000

Safety:
  - Backs up academic_degrees to academic_degrees_backup before any destructive step.
  - Validates target_programs FK coverage before dropping academic_degrees.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "n2o5p8q91r3m"
down_revision: Union[str, Sequence[str], None] = "m1n4o7p80q2l"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Legacy academic_degrees.code -> (programs.code, programs.name)
LEGACY_PROGRAM_MAPPINGS: dict[str, tuple[str, str]] = {
    "BACHELOR": ("BACHELORS_DEGREE", "Bachelor's Degree"),
    "MASTER": ("MASTERS_DEGREE", "Master's Degree"),
    "PHD": ("DOCTORAL_DEGREE", "Doctoral Degree"),
    "CERTIFICATE": ("PROFESSIONAL_CERTIFICATE", "Professional Certificate"),
    "GRAD_CERT": ("PROFESSIONAL_CERTIFICATE", "Professional Certificate"),
}


def _resolve_program_identity(code: str, name: str) -> tuple[str, str]:
    normalized = (code or "").strip().upper()
    trimmed_name = (name or "").strip()
    if normalized in {"BACHELOR", "MASTER", "CERTIFICATE"}:
        return LEGACY_PROGRAM_MAPPINGS[normalized]
    if normalized in {"GRAD_CERT"}:
        return LEGACY_PROGRAM_MAPPINGS["GRAD_CERT"]
    if normalized == "PHD" and trimmed_name.upper() == "PHD":
        return LEGACY_PROGRAM_MAPPINGS["PHD"]
    return normalized, trimmed_name


def _migrate_degree_rows(connection) -> None:
    rows = connection.execute(
        sa.text(
            """
            SELECT id, code, name, description, course_level_id, is_active, sort_order
            FROM academic_degrees
            ORDER BY sort_order ASC, id ASC
            """
        )
    ).mappings().all()

    program_id_by_code: dict[str, uuid.UUID] = {}

    for row in rows:
        target_code, target_name = _resolve_program_identity(row["code"], row["name"])
        program_id = program_id_by_code.get(target_code)

        if program_id is None:
            program_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    """
                    INSERT INTO programs (
                        id, name, code, level_id, description, is_active, sort_order
                    )
                    VALUES (
                        :id,
                        CAST(:name AS VARCHAR),
                        CAST(:code AS VARCHAR),
                        :level_id,
                        CAST(:description AS TEXT),
                        :is_active,
                        :sort_order
                    )
                    """
                ),
                {
                    "id": program_id,
                    "name": target_name,
                    "code": target_code,
                    "level_id": row["course_level_id"],
                    "description": row["description"],
                    "is_active": row["is_active"],
                    "sort_order": row["sort_order"],
                },
            )
            program_id_by_code[target_code] = program_id

        connection.execute(
            sa.text(
                """
                INSERT INTO academic_degree_program_map (academic_degree_id, program_id)
                VALUES (:academic_degree_id, :program_id)
                ON CONFLICT (academic_degree_id) DO UPDATE
                SET program_id = EXCLUDED.program_id
                """
            ),
            {"academic_degree_id": row["id"], "program_id": program_id},
        )


def _validate_migration(connection) -> None:
    orphan_majors = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM target_programs
            WHERE program_id IS NULL
            """
        )
    ).scalar_one()
    if orphan_majors:
        raise RuntimeError(
            f"Migration validation failed: {orphan_majors} target_programs rows lack program_id."
        )

    broken_fk = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM target_programs tp
            LEFT JOIN programs p ON p.id = tp.program_id
            WHERE tp.program_id IS NOT NULL AND p.id IS NULL
            """
        )
    ).scalar_one()
    if broken_fk:
        raise RuntimeError(
            f"Migration validation failed: {broken_fk} target_programs rows reference missing programs."
        )

    unmapped_degrees = connection.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM academic_degrees ad
            LEFT JOIN academic_degree_program_map m ON m.academic_degree_id = ad.id
            WHERE m.program_id IS NULL
            """
        )
    ).scalar_one()
    if unmapped_degrees:
        raise RuntimeError(
            f"Migration validation failed: {unmapped_degrees} academic_degrees rows were not mapped."
        )

    backup_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM academic_degrees_backup")
    ).scalar_one()
    source_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM academic_degrees")
    ).scalar_one()
    if backup_count != source_count:
        raise RuntimeError(
            "Migration validation failed: academic_degrees_backup row count mismatch."
        )


def upgrade() -> None:
    op.execute("CREATE TABLE academic_degrees_backup AS TABLE academic_degrees")

    op.create_table(
        "programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("course_levels.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code", name="uq_programs_code"),
    )
    op.create_index("ix_programs_code", "programs", ["code"], unique=True)
    op.create_index("ix_programs_level_id", "programs", ["level_id"])
    op.create_index("ix_programs_name", "programs", ["name"])

    op.create_table(
        "academic_degree_program_map",
        sa.Column("academic_degree_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "program_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )

    bind = op.get_bind()
    _migrate_degree_rows(bind)

    op.add_column(
        "target_programs",
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    bind.execute(
        sa.text(
            """
            UPDATE target_programs tp
            SET program_id = m.program_id
            FROM academic_degree_program_map m
            WHERE tp.degree_id = m.academic_degree_id
            """
        )
    )

    _validate_migration(bind)

    op.drop_constraint(
        "target_programs_degree_id_fkey",
        "target_programs",
        type_="foreignkey",
    )
    op.drop_index("ix_target_programs_degree_id", table_name="target_programs")
    op.drop_column("target_programs", "degree_id")

    op.alter_column("target_programs", "program_id", nullable=False)
    op.create_foreign_key(
        "fk_target_programs_program_id",
        "target_programs",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_target_programs_program_id", "target_programs", ["program_id"])

    op.drop_table("academic_degrees")
    op.drop_table("academic_degree_program_map")

    program_count = bind.execute(sa.text("SELECT COUNT(*) FROM programs")).scalar_one()
    if program_count == 0:
        raise RuntimeError("Migration validation failed: programs table is empty after migration.")


def downgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "academic_degrees",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("course_level_id", sa.Integer(), sa.ForeignKey("course_levels.id"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code", name="academic_degrees_code_key"),
    )
    op.create_index("ix_academic_degrees_code", "academic_degrees", ["code"], unique=True)
    op.create_index("ix_academic_degrees_name", "academic_degrees", ["name"])
    op.create_index("ix_academic_degrees_course_level_id", "academic_degrees", ["course_level_id"])

    bind.execute(
        sa.text(
            """
            INSERT INTO academic_degrees (id, course_level_id, code, name, description, is_active, sort_order)
            SELECT id, course_level_id, code, name, description, is_active, sort_order
            FROM academic_degrees_backup
            ORDER BY id
            """
        )
    )

    op.add_column("target_programs", sa.Column("degree_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text(
            """
            UPDATE target_programs tp
            SET degree_id = ad.id
            FROM programs p
            JOIN academic_degrees_backup ad ON ad.code = p.code
            WHERE tp.program_id = p.id
            """
        )
    )

    op.drop_constraint("fk_target_programs_program_id", "target_programs", type_="foreignkey")
    op.drop_index("ix_target_programs_program_id", table_name="target_programs")
    op.drop_column("target_programs", "program_id")

    op.create_foreign_key(
        "target_programs_degree_id_fkey",
        "target_programs",
        "academic_degrees",
        ["degree_id"],
        ["id"],
    )
    op.create_index("ix_target_programs_degree_id", "target_programs", ["degree_id"])

    op.drop_table("programs")
