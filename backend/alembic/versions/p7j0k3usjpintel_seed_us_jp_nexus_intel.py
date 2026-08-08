"""Seed US and JP Nexus Intel glossary, scrapers, and academy content.

Revision ID: p7j0k3usjpintel
Revises: o6h9i2nexusintel
Create Date: 2026-07-28
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "p7j0k3usjpintel"
down_revision = "o6h9i2nexusintel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

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
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("last_verified_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    glossary_rows = [
        {
            "term_name": "OPT (Optional Practical Training)",
            "slug": "opt-us",
            "category": "Work_Rights",
            "country_code": "US",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Temporary employment authorization for F-1 students in the US related to their major area of study.",
            "full_explanation": "Standard OPT allows up to 12 months of work post-graduation, with an additional 24-month STEM extension available for qualifying degree holders.",
            "key_metrics": {"standard_months": 12, "stem_extension_months": 24},
            "tags": ["usa", "f1", "opt", "stem"],
            "official_source_url": "https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors/optional-practical-training-opt",
            "is_student_facing": True,
        },
        {
            "term_name": "SEVIS",
            "slug": "sevis-us",
            "category": "Visa",
            "country_code": "US",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Student and Exchange Visitor Information System — DHS database tracking F/M/J status.",
            "full_explanation": "Schools issue I-20s through SEVIS. Students pay the I-901 SEVIS fee before the visa interview and must maintain SEVIS records while studying.",
            "key_metrics": {},
            "tags": ["usa", "sevis", "i901"],
            "official_source_url": "https://www.ice.gov/sevis",
            "is_student_facing": True,
        },
        {
            "term_name": "F-1 Visa",
            "slug": "f1-visa-us",
            "category": "Visa",
            "country_code": "US",
            "lifecycle_stage": "5_Visa",
            "short_definition": "US nonimmigrant student visa for full-time academic study at SEVP-certified schools.",
            "full_explanation": "Requires a valid Form I-20, SEVIS fee payment, and a consular interview. Maintains status via full-time enrollment and authorized work only.",
            "key_metrics": {},
            "tags": ["usa", "f1", "visa"],
            "official_source_url": "https://travel.state.gov/content/travel/en/us-visas/study/student-visa.html",
            "is_student_facing": True,
        },
        {
            "term_name": "CPT (Curricular Practical Training)",
            "slug": "cpt-us",
            "category": "Work_Rights",
            "country_code": "US",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Employer-authorized work that is an integral part of an F-1 student's established curriculum.",
            "full_explanation": "CPT is authorized by the DSO before employment begins. Full-time CPT of 12+ months can eliminate eligibility for OPT at the same education level.",
            "key_metrics": {},
            "tags": ["usa", "cpt", "f1"],
            "official_source_url": "https://studyinthestates.dhs.gov/students/training-opportunities-in-the-united-states",
            "is_student_facing": True,
        },
        {
            "term_name": "Common App",
            "slug": "common-app-us",
            "category": "Admissions",
            "country_code": "US",
            "lifecycle_stage": "2_Prep",
            "short_definition": "Centralized undergraduate application platform used by many US colleges and universities.",
            "full_explanation": "Students complete one core application and submit school-specific questions, essays, recommendations, and fee payments to multiple institutions.",
            "key_metrics": {},
            "tags": ["usa", "admissions", "undergraduate"],
            "official_source_url": "https://www.commonapp.org/",
            "is_student_facing": True,
        },
        {
            "term_name": "GPA Scaling (US)",
            "slug": "gpa-scaling-us",
            "category": "Admissions",
            "country_code": "US",
            "lifecycle_stage": "1_Discovery",
            "short_definition": "Conversion of international marks into a US 4.0-scale GPA for admissions review.",
            "full_explanation": "US universities may recalculate GPA using their own scale or rely on credential evaluators. Weighted vs unweighted scales and grade inflation norms differ by school.",
            "key_metrics": {"scale_max": 4.0},
            "tags": ["usa", "gpa", "admissions"],
            "official_source_url": None,
            "is_student_facing": True,
        },
        {
            "term_name": "SAT / ACT",
            "slug": "sat-act-us",
            "category": "Admissions",
            "country_code": "US",
            "lifecycle_stage": "2_Prep",
            "short_definition": "Standardized US undergraduate entrance exams used by many colleges (optional at some schools).",
            "full_explanation": "SAT and ACT remain part of admissions for test-required and test-optional institutions. Score send policies and superscoring vary by university.",
            "key_metrics": {},
            "tags": ["usa", "sat", "act", "testing"],
            "official_source_url": "https://www.collegeboard.org/",
            "is_student_facing": True,
        },
        {
            "term_name": "WES Credential Evaluation",
            "slug": "wes-us",
            "category": "Admissions",
            "country_code": "US",
            "lifecycle_stage": "2_Prep",
            "short_definition": "World Education Services evaluation equating foreign credentials to US degree/GPA equivalents.",
            "full_explanation": "Many US graduate programs and licensing boards request a course-by-course or document-by-document WES (or similar) evaluation of international transcripts.",
            "key_metrics": {},
            "tags": ["usa", "wes", "credentials"],
            "official_source_url": "https://www.wes.org/",
            "is_student_facing": True,
        },
        {
            "term_name": "CoE (Certificate of Eligibility)",
            "slug": "coe-jp",
            "category": "Visa",
            "country_code": "JP",
            "lifecycle_stage": "5_Visa",
            "short_definition": "A document issued by the Immigration Services Agency of Japan prior to a visa application.",
            "full_explanation": "The CoE is required to apply for a student visa at a Japanese embassy or consulate and proves the student has permission to land in Japan for the stated activity.",
            "key_metrics": {},
            "tags": ["japan", "coe", "visa"],
            "official_source_url": "https://www.isa.go.jp/",
            "is_student_facing": True,
        },
        {
            "term_name": "Zairyu Card (Residence Card)",
            "slug": "zairyu-card-jp",
            "category": "Legal",
            "country_code": "JP",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Japan residence card issued to mid- to long-term foreign residents, including students.",
            "full_explanation": "Students typically receive the Zairyu Card at the airport on landing (or later at municipal offices). It must be carried and updated for address and status changes.",
            "key_metrics": {},
            "tags": ["japan", "residence", "zairyu"],
            "official_source_url": "https://www.isa.go.jp/en/publications/materials/newsys_powerpoint_zairyu_card.html",
            "is_student_facing": True,
        },
        {
            "term_name": "MEXT Scholarship",
            "slug": "mext-jp",
            "category": "Financial",
            "country_code": "JP",
            "lifecycle_stage": "4_Finance",
            "short_definition": "Japanese government (Monbukagakusho) scholarship covering tuition and living stipend for selected international students.",
            "full_explanation": "MEXT awards include embassy and university recommendation tracks. Benefits often include tuition waiver, monthly stipend, and travel support, subject to program rules.",
            "key_metrics": {},
            "tags": ["japan", "mext", "scholarship"],
            "official_source_url": "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
            "is_student_facing": True,
        },
        {
            "term_name": "JASSO",
            "slug": "jasso-jp",
            "category": "Financial",
            "country_code": "JP",
            "lifecycle_stage": "1_Discovery",
            "short_definition": "Japan Student Services Organization — central body for study-in-Japan guidance, scholarships, and student support.",
            "full_explanation": "JASSO publishes Study in Japan resources, scholarship listings, and support programs for international students and host institutions.",
            "key_metrics": {},
            "tags": ["japan", "jasso", "study"],
            "official_source_url": "https://www.studyinjapan.go.jp/en/",
            "is_student_facing": True,
        },
        {
            "term_name": "EJU (Examination for Japanese University Admission)",
            "slug": "eju-jp",
            "category": "Admissions",
            "country_code": "JP",
            "lifecycle_stage": "2_Prep",
            "short_definition": "Standardized exam assessing Japanese language and basic academic skills for international applicants to Japanese universities.",
            "full_explanation": "EJU subjects commonly include Japanese as a Foreign Language, Science, Japan and the World, and Mathematics. Many universities require EJU for Japanese-taught programs.",
            "key_metrics": {},
            "tags": ["japan", "eju", "admissions"],
            "official_source_url": "https://www.jasso.go.jp/en/ryugaku/eju/index.html",
            "is_student_facing": True,
        },
        {
            "term_name": "Ryugaku (Student) Visa",
            "slug": "ryugaku-visa-jp",
            "category": "Visa",
            "country_code": "JP",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Japan status of residence 'Student' (留学) for full-time study at recognized Japanese educational institutions.",
            "full_explanation": "After CoE issuance, applicants obtain a Student visa from a Japanese mission abroad, then receive landing permission and typically a Residence Card on arrival.",
            "key_metrics": {},
            "tags": ["japan", "student", "visa", "ryugaku"],
            "official_source_url": "https://www.isa.go.jp/en/applications/guide/nyukanryou15.html",
            "is_student_facing": True,
        },
    ]

    for row in glossary_rows:
        exists = conn.execute(
            sa.text("SELECT 1 FROM intel_glossary WHERE slug = :slug LIMIT 1"),
            {"slug": row["slug"]},
        ).scalar()
        if exists:
            continue
        op.bulk_insert(
            glossary,
            [
                {
                    "id": uuid.uuid4(),
                    **row,
                    "status": "ACTIVE",
                    "created_at": now,
                    "updated_at": now,
                    "last_verified_at": now,
                }
            ],
        )

    # Enrich existing I-20 metrics if present.
    conn.execute(
        sa.text(
            """
            UPDATE intel_glossary
            SET key_metrics = COALESCE(key_metrics, '{}'::jsonb) ||
                '{"covers": "first_academic_year", "currency": "USD"}'::jsonb,
                updated_at = :now,
                last_verified_at = :now
            WHERE slug = 'i-20'
            """
        ),
        {"now": now},
    )

    scraper = sa.table(
        "intel_scraper_config",
        sa.column("id", postgresql.UUID),
        sa.column("source_name", sa.String),
        sa.column("target_url", sa.Text),
        sa.column("country_code", sa.String),
        sa.column("scrape_interval_hours", sa.Integer),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    scraper_rows = [
        {
            "source_name": "US State Dept Student Visa",
            "target_url": "https://travel.state.gov/content/travel/en/us-visas/study/student-visa.html",
            "country_code": "US",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "USCIS Students & Exchange Visitors",
            "target_url": "https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors",
            "country_code": "US",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "ISA Japan Immigration",
            "target_url": "https://www.isa.go.jp/en/",
            "country_code": "JP",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "JASSO Study in Japan",
            "target_url": "https://www.studyinjapan.go.jp/en/",
            "country_code": "JP",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
    ]
    for row in scraper_rows:
        exists = conn.execute(
            sa.text("SELECT 1 FROM intel_scraper_config WHERE source_name = :name LIMIT 1"),
            {"name": row["source_name"]},
        ).scalar()
        if exists:
            continue
        op.bulk_insert(
            scraper,
            [
                {
                    "id": uuid.uuid4(),
                    **row,
                    "created_at": now,
                    "updated_at": now,
                }
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
    academy_rows = [
        {
            "title": "US OPT & STEM Extension Essentials",
            "slug": "us-opt-essentials",
            "summary": "5-minute refresh on OPT windows, STEM extension, and counselor timing checkpoints.",
            "country_code": "US",
            "duration_minutes": 5,
            "quiz": {
                "question": "How long is standard post-completion OPT before any STEM extension?",
                "options": ["6 months", "12 months", "24 months", "36 months"],
                "correct_option_index": 1,
                "explanation": "Standard OPT is up to 12 months; STEM OPT can add up to 24 more months for eligible degrees.",
            },
            "is_active": True,
            "sort_order": 30,
        },
        {
            "title": "Japan CoE & Student Status",
            "slug": "jp-coe-essentials",
            "summary": "Quick certification on Certificate of Eligibility, Student (Ryugaku) status, and Zairyu Card basics.",
            "country_code": "JP",
            "duration_minutes": 5,
            "quiz": {
                "question": "What document is typically required before applying for a Japan student visa at an embassy?",
                "options": ["Zairyu Card", "Certificate of Eligibility (CoE)", "My Number Card", "JLPT certificate only"],
                "correct_option_index": 1,
                "explanation": "A CoE from Immigration Services Agency of Japan is generally required before the overseas visa application.",
            },
            "is_active": True,
            "sort_order": 40,
        },
    ]
    for row in academy_rows:
        exists = conn.execute(
            sa.text("SELECT 1 FROM intel_academy_modules WHERE slug = :slug LIMIT 1"),
            {"slug": row["slug"]},
        ).scalar()
        if exists:
            continue
        op.bulk_insert(
            academy,
            [
                {
                    "id": uuid.uuid4(),
                    **row,
                }
            ],
        )

    # Prefer JP alongside existing destinations for new preference defaults going forward.
    op.alter_column(
        "intel_user_preferences",
        "preferred_countries",
        server_default=sa.text("'[\"UK\", \"CA\", \"AU\", \"DE\", \"US\", \"JP\"]'::jsonb"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [
        "opt-us",
        "sevis-us",
        "f1-visa-us",
        "cpt-us",
        "common-app-us",
        "gpa-scaling-us",
        "sat-act-us",
        "wes-us",
        "coe-jp",
        "zairyu-card-jp",
        "mext-jp",
        "jasso-jp",
        "eju-jp",
        "ryugaku-visa-jp",
    ]
    conn.execute(
        sa.text("DELETE FROM intel_glossary WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
    conn.execute(
        sa.text(
            "DELETE FROM intel_scraper_config WHERE source_name = ANY(:names)"
        ),
        {
            "names": [
                "US State Dept Student Visa",
                "USCIS Students & Exchange Visitors",
                "ISA Japan Immigration",
                "JASSO Study in Japan",
            ]
        },
    )
    conn.execute(
        sa.text("DELETE FROM intel_academy_modules WHERE slug = ANY(:slugs)"),
        {"slugs": ["us-opt-essentials", "jp-coe-essentials"]},
    )
    op.alter_column(
        "intel_user_preferences",
        "preferred_countries",
        server_default=sa.text("'[\"UK\", \"CA\", \"AU\", \"DE\", \"US\"]'::jsonb"),
    )
