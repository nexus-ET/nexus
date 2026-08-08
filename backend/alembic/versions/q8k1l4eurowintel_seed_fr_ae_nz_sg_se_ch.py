"""Seed FR, AE, NZ, SG, SE, CH Nexus Intel glossary and scrapers.

Revision ID: q8k1l4eurowintel
Revises: p7j0k3usjpintel
Create Date: 2026-07-28
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "q8k1l4eurowintel"
down_revision = "p7j0k3usjpintel"
branch_labels = None
depends_on = None

PREFERRED_COUNTRIES_DEFAULT = (
    '["UK", "CA", "AU", "DE", "US", "JP", "FR", "AE", "NZ", "SG", "SE", "CH"]'
)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

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

    glossary_rows = [
        # France
        {
            "term_name": "VLS-TS France",
            "slug": "vls-ts-france",
            "category": "Visa",
            "country_code": "FR",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Visa de Long Séjour valant Titre de Séjour — long-stay visa that serves as a residence permit for students in France.",
            "full_explanation": "Valid for the first year of studies, it must be validated online upon arrival in France and allows travel within the Schengen Area.",
            "key_metrics": {"validation_window_months": 3, "schengen_access": True},
            "tags": ["france", "vls-ts", "schengen", "visa"],
            "official_source_url": "https://france-visas.gouv.fr/",
            "is_student_facing": True,
        },
        {
            "term_name": "APS France (Job Search / Entrepreneurship)",
            "slug": "aps-france",
            "category": "Work_Rights",
            "country_code": "FR",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Autorisation Provisoire de Séjour allowing eligible graduates to remain in France to seek work or start a business.",
            "full_explanation": "Master's (and some other) graduates may obtain an APS / residence permit for job search or entrepreneurship, commonly up to 12–24 months depending on pathway and nationality agreements.",
            "key_metrics": {"typical_months_min": 12, "typical_months_max": 24},
            "tags": ["france", "aps", "psw", "job-search"],
            "official_source_url": "https://www.service-public.fr/",
            "is_student_facing": True,
        },
        {
            "term_name": "Campus France",
            "slug": "campus-france",
            "category": "Admissions",
            "country_code": "FR",
            "lifecycle_stage": "2_Prep",
            "short_definition": "Official French agency supporting international student applications, Études en France procedures, and pre-consular steps.",
            "full_explanation": "Many applicants complete Campus France / Études en France processes before visa filing, including academic evaluation interviews where required by nationality.",
            "key_metrics": {},
            "tags": ["france", "admissions", "campus-france"],
            "official_source_url": "https://www.campusfrance.org/",
            "is_student_facing": True,
        },
        # UAE / Dubai
        {
            "term_name": "UAE Student Residence Visa",
            "slug": "uae-student-residence-visa",
            "category": "Visa",
            "country_code": "AE",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Student residence visa issued via GDRFA or free-zone authorities for full-time study in the UAE.",
            "full_explanation": "Validity commonly ranges from 1 to 5 years and is tied to enrollment at a licensed university. Dubai institutions are often regulated under KHDA frameworks alongside federal licensing.",
            "key_metrics": {"typical_validity_years_min": 1, "typical_validity_years_max": 5},
            "tags": ["uae", "dubai", "gdrfa", "khda", "visa"],
            "official_source_url": "https://www.gdrfad.gov.ae/",
            "is_student_facing": True,
        },
        {
            "term_name": "KHDA (Dubai)",
            "slug": "khda-dubai",
            "category": "Legal",
            "country_code": "AE",
            "lifecycle_stage": "1_Discovery",
            "short_definition": "Knowledge and Human Development Authority — Dubai regulator for many private education providers.",
            "full_explanation": "KHDA oversees quality and licensing expectations for many Dubai schools and higher-education providers operating in the emirate.",
            "key_metrics": {},
            "tags": ["uae", "dubai", "khda", "regulation"],
            "official_source_url": "https://www.khda.gov.ae/",
            "is_student_facing": True,
        },
        # New Zealand
        {
            "term_name": "NZ Student Visa",
            "slug": "nz-student-visa",
            "category": "Visa",
            "country_code": "NZ",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Immigration New Zealand visa permitting full-time study at an approved education provider.",
            "full_explanation": "Requires an offer of place, funds evidence, and insurance. Work conditions during study depend on the visa conditions and course level.",
            "key_metrics": {},
            "tags": ["new-zealand", "student-visa", "inz"],
            "official_source_url": "https://www.immigration.govt.nz/new-zealand-visas/visas/visa/student-visa",
            "is_student_facing": True,
        },
        {
            "term_name": "Post Study Work Visa NZ",
            "slug": "pswv-new-zealand",
            "category": "Work_Rights",
            "country_code": "NZ",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "An open work visa granted to international students who graduate with an eligible New Zealand qualification.",
            "full_explanation": "Allows graduates to work for any employer and in any job for 1, 2, or 3 years depending on the level of study completed and qualification tier.",
            "key_metrics": {"max_duration_years": 3, "open_work_rights": True},
            "tags": ["new-zealand", "pswv", "psw"],
            "official_source_url": "https://www.immigration.govt.nz/",
            "is_student_facing": True,
        },
        # Singapore
        {
            "term_name": "Singapore Student's Pass",
            "slug": "sg-students-pass",
            "category": "Visa",
            "country_code": "SG",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Immigration & Checkpoints Authority (ICA) pass required for full-time international students in Singapore.",
            "full_explanation": "Issued after an In-Principle Approval (IPA). Validity aligns with the course; students must maintain enrollment and comply with ICA conditions.",
            "key_metrics": {},
            "tags": ["singapore", "ica", "students-pass"],
            "official_source_url": "https://www.ica.gov.sg/",
            "is_student_facing": True,
        },
        {
            "term_name": "Singapore Tuition Grant",
            "slug": "sg-tuition-grant",
            "category": "Financial",
            "country_code": "SG",
            "lifecycle_stage": "4_Finance",
            "short_definition": "Government tuition subsidy that can reduce fees for eligible students in return for a post-graduation service bond.",
            "full_explanation": "International students accepting a Tuition Grant typically sign a deed requiring them to work in a Singapore entity for about three years after graduation, subject to scheme rules.",
            "key_metrics": {"bond_years": 3},
            "tags": ["singapore", "tuition-grant", "bond"],
            "official_source_url": "https://www.moe.gov.sg/",
            "is_student_facing": True,
        },
        {
            "term_name": "LTVP Singapore",
            "slug": "ltvp-singapore",
            "category": "Legal",
            "country_code": "SG",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Long-Term Visit Pass used in some cases for eligible parents/spouses accompanying or visiting students/graduates.",
            "full_explanation": "LTVP eligibility is case-specific and not automatic with a Student's Pass. Counselors should verify ICA criteria for dependents and accompanying family.",
            "key_metrics": {},
            "tags": ["singapore", "ltvp", "dependents"],
            "official_source_url": "https://www.ica.gov.sg/",
            "is_student_facing": True,
        },
        # Sweden
        {
            "term_name": "Sweden Residence Permit for Studies",
            "slug": "se-residence-permit-studies",
            "category": "Visa",
            "country_code": "SE",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Migrationsverket residence permit required for non-EU/EEA students studying in Sweden for more than 90 days.",
            "full_explanation": "Applicants need admission, comprehensive insurance, and proof of means of support. The permit is tied to the study period and full-time enrollment.",
            "key_metrics": {},
            "tags": ["sweden", "migrationsverket", "residence-permit"],
            "official_source_url": "https://www.migrationsverket.se/",
            "is_student_facing": True,
        },
        {
            "term_name": "Sweden Job-Seeking Residence Permit",
            "slug": "se-job-seeking-permit",
            "category": "Work_Rights",
            "country_code": "SE",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Post-study residence option allowing graduates to remain in Sweden to look for work after completing higher education.",
            "full_explanation": "Eligible Bachelor's/Master's graduates may apply to stay and look for work for up to 12 months after completing their degree, subject to Migrationsverket rules.",
            "key_metrics": {"job_search_months": 12},
            "tags": ["sweden", "psw", "job-search"],
            "official_source_url": "https://www.migrationsverket.se/",
            "is_student_facing": True,
        },
        # Switzerland
        {
            "term_name": "Switzerland Student Residence Permit",
            "slug": "ch-student-residence-permit",
            "category": "Visa",
            "country_code": "CH",
            "lifecycle_stage": "5_Visa",
            "short_definition": "Canton-issued residence authorization for full-time study at a recognized Swiss institution.",
            "full_explanation": "Non-EU/EFTA students typically need a national visa followed by a cantonal residence permit. Quotas and evidence requirements vary by canton.",
            "key_metrics": {"canton_quotas": True},
            "tags": ["switzerland", "canton", "residence-permit"],
            "official_source_url": "https://www.sem.admin.ch/",
            "is_student_facing": True,
        },
        {
            "term_name": "Switzerland Post-Graduation Job Search",
            "slug": "ch-postgrad-job-search",
            "category": "Work_Rights",
            "country_code": "CH",
            "lifecycle_stage": "6_Onboarding",
            "short_definition": "Limited post-graduation window for graduates to remain and seek employment of high economic/scientific interest to Switzerland.",
            "full_explanation": "Graduates commonly have around six months after studies to find qualifying work. Approvals remain subject to strict cantonal labour-market and quota rules.",
            "key_metrics": {"job_search_months": 6},
            "tags": ["switzerland", "psw", "job-search", "quota"],
            "official_source_url": "https://www.sem.admin.ch/",
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
            "source_name": "France-Visas",
            "target_url": "https://france-visas.gouv.fr/",
            "country_code": "FR",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "Campus France",
            "target_url": "https://www.campusfrance.org/en",
            "country_code": "FR",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "GDRFA Dubai",
            "target_url": "https://www.gdrfad.gov.ae/",
            "country_code": "AE",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "KHDA Dubai",
            "target_url": "https://www.khda.gov.ae/",
            "country_code": "AE",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "Immigration New Zealand",
            "target_url": "https://www.immigration.govt.nz/",
            "country_code": "NZ",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "ICA Singapore",
            "target_url": "https://www.ica.gov.sg/",
            "country_code": "SG",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "Migrationsverket Sweden",
            "target_url": "https://www.migrationsverket.se/en.html",
            "country_code": "SE",
            "scrape_interval_hours": 168,
            "status": "IDLE",
        },
        {
            "source_name": "SEM Switzerland",
            "target_url": "https://www.sem.admin.ch/sem/en/home.html",
            "country_code": "CH",
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
            "title": "France VLS-TS & APS Essentials",
            "slug": "fr-vls-ts-aps",
            "summary": "5-minute refresh on VLS-TS validation and APS job-search pathways for Master's graduates.",
            "country_code": "FR",
            "duration_minutes": 5,
            "quiz": {
                "question": "What must students typically do after arriving in France with a VLS-TS?",
                "options": [
                    "Nothing until year two",
                    "Validate the VLS-TS online",
                    "Convert immediately to APS",
                    "Apply for a Swiss permit",
                ],
                "correct_option_index": 1,
                "explanation": "VLS-TS student visas must be validated online after arrival to act as the residence title.",
            },
            "is_active": True,
            "sort_order": 50,
        },
        {
            "title": "NZ Post-Study Work Visa Tiers",
            "slug": "nz-pswv-tiers",
            "summary": "Quick certification on PSWV open-work duration by qualification level.",
            "country_code": "NZ",
            "duration_minutes": 5,
            "quiz": {
                "question": "What is the maximum common PSWV duration for eligible NZ graduates?",
                "options": ["6 months", "1 year", "3 years", "5 years"],
                "correct_option_index": 2,
                "explanation": "Eligible graduates may receive open work rights for up to 3 years depending on qualification level/tier.",
            },
            "is_active": True,
            "sort_order": 60,
        },
    ]
    for row in academy_rows:
        exists = conn.execute(
            sa.text("SELECT 1 FROM intel_academy_modules WHERE slug = :slug LIMIT 1"),
            {"slug": row["slug"]},
        ).scalar()
        if exists:
            continue
        op.bulk_insert(academy, [{"id": uuid.uuid4(), **row}])

    op.alter_column(
        "intel_user_preferences",
        "preferred_countries",
        server_default=sa.text(f"'{PREFERRED_COUNTRIES_DEFAULT}'::jsonb"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [
        "vls-ts-france",
        "aps-france",
        "campus-france",
        "uae-student-residence-visa",
        "khda-dubai",
        "nz-student-visa",
        "pswv-new-zealand",
        "sg-students-pass",
        "sg-tuition-grant",
        "ltvp-singapore",
        "se-residence-permit-studies",
        "se-job-seeking-permit",
        "ch-student-residence-permit",
        "ch-postgrad-job-search",
    ]
    conn.execute(sa.text("DELETE FROM intel_glossary WHERE slug = ANY(:slugs)"), {"slugs": slugs})
    conn.execute(
        sa.text("DELETE FROM intel_scraper_config WHERE source_name = ANY(:names)"),
        {
            "names": [
                "France-Visas",
                "Campus France",
                "GDRFA Dubai",
                "KHDA Dubai",
                "Immigration New Zealand",
                "ICA Singapore",
                "Migrationsverket Sweden",
                "SEM Switzerland",
            ]
        },
    )
    conn.execute(
        sa.text("DELETE FROM intel_academy_modules WHERE slug = ANY(:slugs)"),
        {"slugs": ["fr-vls-ts-aps", "nz-pswv-tiers"]},
    )
    op.alter_column(
        "intel_user_preferences",
        "preferred_countries",
        server_default=sa.text("'[\"UK\", \"CA\", \"AU\", \"DE\", \"US\", \"JP\"]'::jsonb"),
    )
