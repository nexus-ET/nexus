"""Add Nexus Intel knowledge, trivia, preferences, and scraper tables.

Revision ID: o6h9i2nexusintel
Revises: n5g8h1ftint1718
Create Date: 2026-07-28 11:00:00.000000

"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o6h9i2nexusintel"
down_revision: Union[str, Sequence[str], None] = "n5g8h1ftint1718"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Staging may already have Intel tables (schema sync) while alembic_version lags.
    if inspector.has_table("intel_glossary"):
        return

    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "intel_glossary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("term_name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=50), nullable=False),
        sa.Column("short_definition", sa.Text(), nullable=False),
        sa.Column("full_explanation", sa.Text(), nullable=True),
        sa.Column("key_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("official_source_url", sa.Text(), nullable=True),
        sa.Column("is_student_facing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("slug", name="uq_intel_glossary_slug"),
    )
    op.create_index("ix_intel_glossary_term_name", "intel_glossary", ["term_name"])
    op.create_index("ix_intel_glossary_category", "intel_glossary", ["category"])
    op.create_index("ix_intel_glossary_country_code", "intel_glossary", ["country_code"])
    op.create_index("ix_intel_glossary_lifecycle_stage", "intel_glossary", ["lifecycle_stage"])
    op.create_index("ix_intel_glossary_status", "intel_glossary", ["status"])

    op.create_table(
        "intel_trivia",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_option_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("active_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("active_date", name="uq_intel_trivia_active_date"),
    )

    op.create_table(
        "intel_trivia_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trivia_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intel_trivia.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_option_index", sa.Integer(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "trivia_id", name="uq_intel_trivia_answers_user_trivia"),
    )
    op.create_index("ix_intel_trivia_answers_user_id", "intel_trivia_answers", ["user_id"])

    op.create_table(
        "intel_user_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enable_daily_trivia", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("enable_contextual_tips", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "preferred_countries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"UK\", \"CA\", \"AU\", \"DE\", \"US\"]'::jsonb"),
        ),
        sa.Column("trivia_streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trivia_correct_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "intel_scraper_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=False),
        sa.Column("scrape_interval_hours", sa.Integer(), nullable=False, server_default=sa.text("168")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'IDLE'")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "intel_academy_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("quiz", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("slug", name="uq_intel_academy_modules_slug"),
    )

    op.create_table(
        "intel_scrape_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scraper_config_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intel_scraper_config.id", ondelete="CASCADE"), nullable=False),
        sa.Column("glossary_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intel_glossary.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("old_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'NEEDS_REVIEW'")),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    glossary = sa.table(
        "intel_glossary",
        sa.column("id", postgresql.UUID),
        sa.column("term_name", sa.String),
        sa.column("slug", sa.String),
        sa.column("category", sa.String),
        sa.column("country_code", sa.String),
        sa.column("lifecycle_stage", sa.String),
        sa.column("short_definition", sa.Text),
        sa.column("full_explanation", sa.Text),
        sa.column("key_metrics", postgresql.JSONB),
        sa.column("tags", postgresql.JSONB),
        sa.column("official_source_url", sa.Text),
        sa.column("is_student_facing", sa.Boolean),
        sa.column("status", sa.String),
    )

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        glossary,
        [
            {
                "id": uuid.uuid4(),
                "term_name": "CAS",
                "slug": "cas",
                "category": "Admissions",
                "country_code": "UK",
                "lifecycle_stage": "3_Offer",
                "short_definition": "Confirmation of Acceptance for Studies — UK visa sponsorship document issued by a licensed sponsor.",
                "full_explanation": "A CAS is a unique electronic reference issued by a UK university after an unconditional offer. Students need it to apply for a Student visa.",
                "key_metrics": {"validity_months": 6},
                "tags": ["visa", "uk", "admissions"],
                "official_source_url": "https://www.gov.uk/student-visa",
                "is_student_facing": True,
                "status": "ACTIVE",
            },
            {
                "id": uuid.uuid4(),
                "term_name": "GIC",
                "slug": "gic",
                "category": "Financial",
                "country_code": "CA",
                "lifecycle_stage": "4_Finance",
                "short_definition": "Guaranteed Investment Certificate used to prove funds for a Canadian study permit (SDS).",
                "full_explanation": "Under SDS, students purchase a GIC from a participating Canadian bank. Funds are released after arrival according to bank rules.",
                "key_metrics": {"gic_amount": 20635, "currency": "CAD", "holding_days": 28},
                "tags": ["canada", "funds", "sds"],
                "official_source_url": "https://www.canada.ca/en/immigration-refugees-citizenship.html",
                "is_student_facing": True,
                "status": "ACTIVE",
            },
            {
                "id": uuid.uuid4(),
                "term_name": "I-20",
                "slug": "i-20",
                "category": "Admissions",
                "country_code": "US",
                "lifecycle_stage": "3_Offer",
                "short_definition": "Certificate of Eligibility for Nonimmigrant Student Status issued by a SEVP-certified school.",
                "full_explanation": "The Form I-20 is required for F-1/M-1 visa applications and SEVIS fee payment.",
                "key_metrics": {},
                "tags": ["usa", "f1", "sevis"],
                "official_source_url": "https://studyinthestates.dhs.gov/",
                "is_student_facing": True,
                "status": "ACTIVE",
            },
            {
                "id": uuid.uuid4(),
                "term_name": "APS",
                "slug": "aps",
                "category": "Admissions",
                "country_code": "DE",
                "lifecycle_stage": "2_Prep",
                "short_definition": "Akademische Prüfstelle — academic credential verification required for many Indian applicants to Germany.",
                "full_explanation": "APS evaluates academic documents before German university applications/visa for students from certain countries.",
                "key_metrics": {},
                "tags": ["germany", "verification"],
                "official_source_url": "https://www.aps-india.de/",
                "is_student_facing": True,
                "status": "ACTIVE",
            },
            {
                "id": uuid.uuid4(),
                "term_name": "Proof of Funds",
                "slug": "proof-of-funds",
                "category": "Financial",
                "country_code": "GLOBAL",
                "lifecycle_stage": "4_Finance",
                "short_definition": "Evidence that a student can cover tuition and living costs for the destination country.",
                "full_explanation": "Requirements vary by country (bank statements, GIC, blocked account, sponsorship letters).",
                "key_metrics": {},
                "tags": ["finance", "visa"],
                "official_source_url": None,
                "is_student_facing": True,
                "status": "ACTIVE",
            },
            {
                "id": uuid.uuid4(),
                "term_name": "PSW",
                "slug": "psw",
                "category": "Work_Rights",
                "country_code": "GLOBAL",
                "lifecycle_stage": "6_Onboarding",
                "short_definition": "Post-Study Work rights allowing graduates to remain and work after completing studies.",
                "full_explanation": "Examples include UK Graduate route, Canada PGWP, Australia Temporary Graduate visa.",
                "key_metrics": {},
                "tags": ["work", "graduate"],
                "official_source_url": None,
                "is_student_facing": True,
                "status": "ACTIVE",
            },
        ],
    )

    trivia = sa.table(
        "intel_trivia",
        sa.column("id", postgresql.UUID),
        sa.column("question", sa.Text),
        sa.column("options", postgresql.JSONB),
        sa.column("correct_option_index", sa.Integer),
        sa.column("explanation", sa.Text),
        sa.column("country_code", sa.String),
        sa.column("active_date", sa.Date),
    )
    op.bulk_insert(
        trivia,
        [
            {
                "id": uuid.uuid4(),
                "question": "What does CAS stand for in UK student admissions?",
                "options": [
                    "Certificate of Academic Standing",
                    "Confirmation of Acceptance for Studies",
                    "Canadian Admissions Statement",
                    "Campus Accommodation Slip",
                ],
                "correct_option_index": 1,
                "explanation": "CAS means Confirmation of Acceptance for Studies — required for UK Student visa applications.",
                "country_code": "UK",
                "active_date": date.today(),
            }
        ],
    )

    scraper = sa.table(
        "intel_scraper_config",
        sa.column("id", postgresql.UUID),
        sa.column("source_name", sa.String),
        sa.column("target_url", sa.Text),
        sa.column("country_code", sa.String),
        sa.column("scrape_interval_hours", sa.Integer),
        sa.column("status", sa.String),
    )
    op.bulk_insert(
        scraper,
        [
            {
                "id": uuid.uuid4(),
                "source_name": "UKVI Student Visa",
                "target_url": "https://www.gov.uk/student-visa",
                "country_code": "UK",
                "scrape_interval_hours": 168,
                "status": "IDLE",
            },
            {
                "id": uuid.uuid4(),
                "source_name": "IRCC Study Permits",
                "target_url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada.html",
                "country_code": "CA",
                "scrape_interval_hours": 168,
                "status": "IDLE",
            },
            {
                "id": uuid.uuid4(),
                "source_name": "Australian Home Affairs",
                "target_url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-500",
                "country_code": "AU",
                "scrape_interval_hours": 168,
                "status": "IDLE",
            },
            {
                "id": uuid.uuid4(),
                "source_name": "DAAD Study in Germany",
                "target_url": "https://www.daad.de/en/",
                "country_code": "DE",
                "scrape_interval_hours": 168,
                "status": "IDLE",
            },
        ],
    )

    academy = sa.table(
        "intel_academy_modules",
        sa.column("id", postgresql.UUID),
        sa.column("title", sa.String),
        sa.column("slug", sa.String),
        sa.column("summary", sa.Text),
        sa.column("country_code", sa.String),
        sa.column("duration_minutes", sa.Integer),
        sa.column("quiz", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        academy,
        [
            {
                "id": uuid.uuid4(),
                "title": "UK CAS Essentials",
                "slug": "uk-cas-essentials",
                "summary": "5-minute refresh on CAS issuance, validity, and visa timing for counselors.",
                "country_code": "UK",
                "duration_minutes": 5,
                "quiz": {
                    "question": "When can a student typically apply for a UK Student visa after receiving a CAS?",
                    "options": ["Immediately", "Only after arriving in the UK", "Only after paying SEVIS", "Never"],
                    "correct_option_index": 0,
                    "explanation": "Students can apply once they have a valid CAS and meet other visa requirements.",
                },
                "is_active": True,
                "sort_order": 1,
            },
            {
                "id": uuid.uuid4(),
                "title": "Canada GIC & SDS",
                "slug": "canada-gic-sds",
                "summary": "Quick certification on Guaranteed Investment Certificates under SDS.",
                "country_code": "CA",
                "duration_minutes": 5,
                "quiz": {
                    "question": "A GIC is primarily used to demonstrate:",
                    "options": ["English proficiency", "Proof of funds", "Health insurance", "Housing"],
                    "correct_option_index": 1,
                    "explanation": "GICs demonstrate living-cost funds for SDS study permit applications.",
                },
                "is_active": True,
                "sort_order": 2,
            },
        ],
    )

    # silence unused
    _ = now


def downgrade() -> None:
    op.drop_table("intel_scrape_reviews")
    op.drop_table("intel_academy_modules")
    op.drop_table("intel_scraper_config")
    op.drop_table("intel_user_preferences")
    op.drop_index("ix_intel_trivia_answers_user_id", table_name="intel_trivia_answers")
    op.drop_table("intel_trivia_answers")
    op.drop_table("intel_trivia")
    op.drop_index("ix_intel_glossary_status", table_name="intel_glossary")
    op.drop_index("ix_intel_glossary_lifecycle_stage", table_name="intel_glossary")
    op.drop_index("ix_intel_glossary_country_code", table_name="intel_glossary")
    op.drop_index("ix_intel_glossary_category", table_name="intel_glossary")
    op.drop_index("ix_intel_glossary_term_name", table_name="intel_glossary")
    op.drop_table("intel_glossary")
