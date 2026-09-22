"""Repair missing ScanX document_types / documents tables.

Alembic was stamped past e3f4g5scanxdyn while the tables were absent
(causing UndefinedTable on document_types). Recreate idempotently.

Revision ID: j8k9l0scxfix
Revises: i7j8k9followdt
Create Date: 2026-09-20 12:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j8k9l0scxfix"
down_revision: Union[str, Sequence[str], None] = "i7j8k9followdt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOCUMENT_TYPE_SEEDS: tuple[tuple[str, str], ...] = (
    ("PASSPORT", "Student Passport"),
    ("SEMESTER_MARKSHEET", "Semester Marksheet"),
    ("GRADE_SHEET", "Grade sheet"),
    ("TR_TRANSCRIPT", "Academic transcript"),
    ("DIPLOMA", "Diploma / degree certificate"),
    ("ACADEMIC_CERTIFICATE", "Academic certificate"),
    ("SOP", "Statement of purpose"),
    ("LOR", "Letter of recommendation"),
    ("CV_RESUME", "CV / resume"),
    ("OFFER_LETTER", "Offer letter"),
    ("APPLICATION_FORM", "Application form"),
    ("PHOTO", "Photo"),
    ("PERSONAL_PARTICULARS", "Personal particulars"),
    ("IELTS", "IELTS score"),
    ("TOEFL", "TOEFL score"),
    ("GRE", "GRE score"),
    ("GMAT", "GMAT score"),
    ("OTHER_TEST_SCORE", "Other test score"),
    ("EMPLOYMENT_LETTER", "Employment letter"),
    ("INTERNSHIP", "Internship letter"),
    ("PORTFOLIO", "Portfolio"),
    ("PROJECT_REPORT", "Project report"),
    ("RESEARCH_PAPER", "Research paper"),
    ("PUBLICATION", "Publication"),
    ("EXTRACURRICULAR", "Extracurricular"),
    ("VOLUNTEERING", "Volunteering"),
    ("AWARD", "Award / recognition"),
    ("SOCIAL_PROFILE", "Social / digital profile"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "document_types" not in existing:
        op.create_table(
            "document_types",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column(
                "schema_definition",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint("code", name="uq_document_types_code"),
        )
        op.create_index("ix_document_types_code", "document_types", ["code"])

    if "documents" not in existing:
        op.create_table(
            "documents",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("document_type_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("upload_source", sa.String(length=32), nullable=False),
            sa.Column("uploader_user_id", sa.Integer(), nullable=True),
            sa.Column("storage_path", sa.String(length=1024), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=True),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="UPLOADING",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["leads.id"],
                name="fk_documents_candidate_id_leads",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["document_type_id"],
                ["document_types.id"],
                name="fk_documents_document_type_id",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["uploader_user_id"],
                ["users.id"],
                name="fk_documents_uploader_user_id_users",
                ondelete="SET NULL",
            ),
        )
        op.create_index("ix_documents_candidate_id", "documents", ["candidate_id"])
        op.create_index("ix_documents_status", "documents", ["status"])
        op.create_index("ix_documents_document_type_id", "documents", ["document_type_id"])
        op.create_index("ix_documents_upload_source", "documents", ["upload_source"])
        op.create_index("ix_documents_uploader_user_id", "documents", ["uploader_user_id"])

    if "extracted_document_data" not in existing:
        op.create_table(
            "extracted_document_data",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("field_group", sa.String(length=64), nullable=False),
            sa.Column(
                "structured_data",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "bounding_box",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column(
                "is_low_confidence",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "reading_order_index",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["documents.id"],
                name="fk_extracted_document_data_document_id",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_extracted_document_data_document_id",
            "extracted_document_data",
            ["document_id"],
        )
        op.create_index(
            "ix_extracted_document_data_field_group",
            "extracted_document_data",
            ["field_group"],
        )
        op.create_index(
            "ix_extracted_document_data_is_low_confidence",
            "extracted_document_data",
            ["is_low_confidence"],
        )
        op.create_index(
            "ix_extracted_document_data_structured_data_gin",
            "extracted_document_data",
            ["structured_data"],
            postgresql_using="gin",
        )
        op.create_index(
            "ix_extracted_document_data_bounding_box_gin",
            "extracted_document_data",
            ["bounding_box"],
            postgresql_using="gin",
        )

    # Seed lookup rows (idempotent).
    for code, name in _DOCUMENT_TYPE_SEEDS:
        bind.execute(
            sa.text(
                """
                INSERT INTO document_types (code, name, schema_definition)
                VALUES (:code, :name, NULL)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "name": name},
        )


def downgrade() -> None:
    # Intentionally no-op: do not drop tables that may already hold production data.
    pass
