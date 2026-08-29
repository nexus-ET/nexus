"""Nexus Intel domain services."""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.models.nexus_intel import (
    IntelAcademyModule,
    IntelGlossary,
    IntelInquiryFaq,
    IntelScrapeReview,
    IntelScraperConfig,
    IntelTrivia,
    IntelTriviaAnswer,
    IntelUserPreferences,
)
from app.data.intel_inquiry_seed import INQUIRY_TAXONOMY, resolve_inquiry_path
from app.models.user import User  # noqa: F401 — ensure users table is in metadata for FKs
from app.schemas.nexus_intel import (
    CountryComparisonItem,
    IntelPreferencesRead,
    IntelPreferencesUpdate,
    ProofOfFundsRequest,
    ProofOfFundsResponse,
    SortDir,
    SortField,
)

COUNTRY_FUNDS: dict[str, dict[str, Any]] = {
    "UK": {
        "currency": "GBP",
        "holding_days": 28,
        "living_outside_london": 1334 * 9,
        "notes": ["Show 28 consecutive days of funds ending within 31 days of application."],
    },
    "CA": {
        "currency": "CAD",
        "holding_days": 28,
        "gic_amount": 20635,
        "notes": ["SDS pathway typically uses a GIC from a participating bank."],
    },
    "AU": {
        "currency": "AUD",
        "holding_days": 90,
        "living_annual": 29710,
        "notes": ["Genuine Temporary Entrant and funds evidence required."],
    },
    "DE": {
        "currency": "EUR",
        "holding_days": 365,
        "blocked_account": 11904,
        "notes": ["Blocked account (Sperrkonto) is the common proof-of-funds path."],
    },
    "US": {
        "currency": "USD",
        "holding_days": 30,
        "i20_first_year": True,
        "notes": [
            "I-20 financial proof must cover the first academic year of tuition + living costs listed by the SEVP school.",
            "Liquid funds / sponsorship evidence must match or exceed the I-20 estimated expenses.",
        ],
    },
    "JP": {
        "currency": "JPY",
        "holding_days": 90,
        "coe_min_funds": 2_000_000,
        "coe_min_funds_low": 1_500_000,
        "notes": [
            "CoE applications commonly evidence ~¥1.5M–¥2.0M for first-year tuition + living costs (institution/sponsor dependent).",
            "Bank statements, scholarship award letters, or sponsor affidavits are typical supporting documents.",
        ],
    },
    "FR": {
        "currency": "EUR",
        "holding_days": 30,
        "notes": [
            "Evidence typically covers tuition + living resources for the first year; VLS-TS validation follows arrival.",
        ],
    },
    "AE": {
        "currency": "AED",
        "holding_days": 30,
        "notes": [
            "Student residence visa funding is institution- and free-zone/GDRFA-dependent; use offer letter cost estimates.",
        ],
    },
    "NZ": {
        "currency": "NZD",
        "holding_days": 30,
        "living_annual": 20000,
        "notes": [
            "Immigration NZ expects funds for living costs plus tuition; living guideline modeled at NZD $20,000/year (policy updates may vary).",
        ],
    },
    "SG": {
        "currency": "SGD",
        "holding_days": 30,
        "notes": [
            "Student's Pass funding follows ICA/school requirements; Tuition Grant acceptance creates a post-grad work bond.",
        ],
    },
    "SE": {
        "currency": "SEK",
        "holding_days": 30,
        "living_monthly": 10250,
        "notes": [
            "Migrationsverket requires proof of means of support for the permit period (monthly living guideline modeled).",
        ],
    },
    "CH": {
        "currency": "CHF",
        "holding_days": 30,
        "notes": [
            "Cantonal residence permits require tuition + living evidence; amounts and quotas vary by canton.",
        ],
    },
}

COMPARISON_MATRIX: dict[str, CountryComparisonItem] = {
    "UK": CountryComparisonItem(
        country_code="UK",
        tuition_band="£12k–£38k / year (varies widely)",
        psw_rights="Graduate route up to 2 years (3 for PhD)",
        dependent_rules="Limited; depends on course level and policy updates",
        work_limits="Typically 20 hrs/week in term for degree-level Student visa",
        proof_of_funds_summary="28-day bank evidence; CAS-linked",
        language_requirements="IELTS / PTE / LanguageCert (Secure English Language Test) or university equivalent",
    ),
    "CA": CountryComparisonItem(
        country_code="CA",
        tuition_band="CAD $15k–$40k / year",
        psw_rights="PGWP up to 3 years (program-dependent)",
        dependent_rules="Spouse open work permit possible in many cases",
        work_limits="On-campus + off-campus rules per IRCC updates",
        proof_of_funds_summary="GIC / bank evidence; SDS vs regular stream",
        language_requirements="IELTS / CELPIP / TEF (pathway dependent); university English requirements",
    ),
    "AU": CountryComparisonItem(
        country_code="AU",
        tuition_band="AUD $20k–$45k / year",
        psw_rights="Temporary Graduate (subclass 485) pathways",
        dependent_rules="Family members may be included on Student visa",
        work_limits="Student work-hour caps subject to Home Affairs rules",
        proof_of_funds_summary="12 months living + tuition evidence common",
        language_requirements="IELTS / PTE / TOEFL / Cambridge (Genuine Student + uni minima)",
    ),
    "DE": CountryComparisonItem(
        country_code="DE",
        tuition_band="Often low/no tuition at public unis (+ semester fees)",
        psw_rights="18-month job-seeker residence after graduation",
        dependent_rules="Family reunification rules apply separately",
        work_limits="120 full / 240 half days per year typical",
        proof_of_funds_summary="Blocked account (~€11,904/year guideline)",
        language_requirements="TestDaF / DSH / Goethe for German-taught; IELTS/TOEFL for English-taught",
    ),
    "US": CountryComparisonItem(
        country_code="US",
        tuition_band="USD $20k–$60k+ / year",
        psw_rights="1-year OPT; up to 3 years total with STEM OPT (12 + 24)",
        dependent_rules="F-2 dependents; work restrictions apply",
        work_limits="On-campus primarily; CPT/OPT for authorized off-campus",
        proof_of_funds_summary="I-20 first-year tuition + living funding evidence",
        language_requirements="TOEFL / IELTS / Duolingo (school-specific); SAT/ACT may apply for undergrad",
    ),
    "JP": CountryComparisonItem(
        country_code="JP",
        tuition_band="¥500k–¥1.5M+ / year (national vs private varies)",
        psw_rights="Designated Activities (job hunting) or switch to Work / Highly Skilled Professional visa",
        dependent_rules="Dependent status possible for eligible family under separate applications",
        work_limits="Up to 28 hrs/week part-time with permission to engage in activity other than that permitted",
        proof_of_funds_summary="CoE evidence ~¥1.5M–¥2.0M first-year guideline (case-by-case)",
        language_requirements="JLPT N1/N2 for many Japanese-taught programs; TOEFL/IELTS for English/IGP tracks; EJU often required",
    ),
    "FR": CountryComparisonItem(
        country_code="FR",
        tuition_band="Public: low regulated fees; Grandes écoles / private: higher",
        psw_rights="APS / job-search or entrepreneurship residence (often 12–24 months for Master's grads)",
        dependent_rules="Family reunification / accompanying rules are case-specific",
        work_limits="Student work typically capped (commonly ~964 hrs/year guideline)",
        proof_of_funds_summary="First-year tuition + living resources for VLS-TS",
        language_requirements="DELF/DALF / TCF for French-taught; IELTS/TOEFL for English tracks; Campus France steps",
    ),
    "AE": CountryComparisonItem(
        country_code="AE",
        tuition_band="AED high private / international campus fees (Dubai & Abu Dhabi vary)",
        psw_rights="Primarily study-tied residence; post-study work depends on employer sponsorship pathways",
        dependent_rules="Dependent visas via sponsor income/eligibility rules",
        work_limits="On-campus/internship permissions vary by free zone and visa conditions",
        proof_of_funds_summary="Institution-linked student residence visa funding evidence",
        language_requirements="English-medium common (IELTS/TOEFL/EmSAT); Arabic tracks less common for internationals",
    ),
    "NZ": CountryComparisonItem(
        country_code="NZ",
        tuition_band="NZD $22k–$45k+ / year (level and provider dependent)",
        psw_rights="Post Study Work Visa open work rights 1–3 years by qualification tier",
        dependent_rules="Partner/child conditions depend on student visa type and duration",
        work_limits="In-study work hours per visa conditions (commonly up to 20 hrs/week in term for many students)",
        proof_of_funds_summary="Tuition + living funds (living guideline commonly ~NZD $20k/year)",
        language_requirements="IELTS / PTE / TOEFL to meet provider + Immigration NZ settings",
    ),
    "SG": CountryComparisonItem(
        country_code="SG",
        tuition_band="SGD high for internationals; Tuition Grant reduces fees with bond",
        psw_rights="No automatic open PSW; employment pass / related work passes after graduation",
        dependent_rules="LTVP may apply for eligible parents/spouses (not automatic)",
        work_limits="Student's Pass work permissions are limited and scheme-specific",
        proof_of_funds_summary="ICA/school funding evidence; Tuition Grant bond awareness",
        language_requirements="English-medium dominant (IELTS/TOEFL/PTE); MOE/university minima",
    ),
    "SE": CountryComparisonItem(
        country_code="SE",
        tuition_band="EU/EEA often fee-free at public unis; non-EU tuition applies",
        psw_rights="Up to 12 months residence to look for work after Bachelor's/Master's",
        dependent_rules="Family member permits possible subject to Migrationsverket rules",
        work_limits="Students may work without a separate permit while holding a study residence permit",
        proof_of_funds_summary="Means of support for the permit period (monthly living guideline)",
        language_requirements="English-taught common (IELTS/TOEFL); Swedish for Swedish-taught programs",
    ),
    "CH": CountryComparisonItem(
        country_code="CH",
        tuition_band="Public cantonal fees relatively moderate; private/specialty higher",
        psw_rights="~6-month post-grad window to find work of high economic/scientific interest",
        dependent_rules="Family reunification tightly regulated; canton-dependent",
        work_limits="Part-time caps and employer authorization vary; non-EU rules stricter",
        proof_of_funds_summary="Canton-level tuition + living evidence; quota sensitivity",
        language_requirements="German/French/Italian by region; English-taught master's common (IELTS/TOEFL)",
    ),
    "IE": CountryComparisonItem(
        country_code="IE",
        tuition_band="EUR €10k–€25k+ / year (programme dependent)",
        psw_rights="Third Level Graduate Scheme — typically 12–24 months stay-back by level",
        dependent_rules="Stamp conditions for family are case-specific; not automatic for all students",
        work_limits="Typically up to 20 hrs/week in term / 40 hrs in holidays on Stamp 2",
        proof_of_funds_summary="Tuition + living funds evidence for visa/immigration registration",
        language_requirements="IELTS / TOEFL / Duolingo commonly accepted (institution minima)",
    ),
    "NL": CountryComparisonItem(
        country_code="NL",
        tuition_band="Statutory fees for EU; institutional fees higher for non-EU (~€8k–€20k+)",
        psw_rights="Orientation year (zoekjaar) residence permit — typically up to 1 year after graduation",
        dependent_rules="Family reunification / MVV rules apply separately",
        work_limits="Non-EU students usually need a TWV work permit for paid work (hour caps apply)",
        proof_of_funds_summary="Living + tuition evidence for MVV / residence (IND guidelines)",
        language_requirements="English-taught widespread (IELTS/TOEFL); Dutch for Dutch-taught tracks",
    ),
    "NO": CountryComparisonItem(
        country_code="NO",
        tuition_band="Public universities often tuition-free historically; fees increasingly apply for non-EU — verify current rules",
        psw_rights="Job-seeker residence possible after eligible graduation (duration policy-sensitive)",
        dependent_rules="Family immigration rules are separate and income-tested",
        work_limits="Students may work part-time within permit conditions",
        proof_of_funds_summary="Subsistence funds for the study period (UDI living guideline)",
        language_requirements="English-taught programmes common (IELTS/TOEFL); Norwegian for Norwegian-taught",
    ),
    "PL": CountryComparisonItem(
        country_code="PL",
        tuition_band="EUR / PLN moderate for internationals at public unis; private higher",
        psw_rights="Temporary residence to seek work after graduation available under national rules",
        dependent_rules="Family reunification available under standard temporary residence criteria",
        work_limits="Students may work without a separate work permit in many cases (confirm current law)",
        proof_of_funds_summary="Tuition + living funds for national visa / temporary residence",
        language_requirements="English-taught programmes common (IELTS/TOEFL); Polish for Polish-taught",
    ),
    "HK": CountryComparisonItem(
        country_code="HK",
        tuition_band="HKD high for non-local undergraduates; taught postgraduate bands vary widely",
        psw_rights="Immigration Arrangements for Non-local Graduates (IANG) — typically 24 months open stay",
        dependent_rules="Dependents possible under eligible sponsorship / scheme rules",
        work_limits="Part-time work permissions for students are limited and scheme-specific",
        proof_of_funds_summary="School offer + financial evidence for student visa endorsement",
        language_requirements="English-medium dominant (IELTS/TOEFL); some Chinese-taught options",
    ),
    "MY": CountryComparisonItem(
        country_code="MY",
        tuition_band="MYR competitive vs Western destinations; twinning/branch campuses vary",
        psw_rights="No broad automatic multi-year PSW; graduate work depends on Employment Pass / related passes",
        dependent_rules="Dependent passes via eligible sponsor categories",
        work_limits="Student Pass work permissions are restricted; check EMGS / school rules",
        proof_of_funds_summary="EMGS / Student Pass financial evidence with offer letter",
        language_requirements="English-medium common (IELTS/TOEFL/MUET pathways)",
    ),
    "QA": CountryComparisonItem(
        country_code="QA",
        tuition_band="QAR — Education City / private university fees; scholarship pathways common",
        psw_rights="Residence primarily study- or employer-tied; post-study stay depends on sponsorship",
        dependent_rules="Family sponsorship via eligible residence categories",
        work_limits="On-campus / internship permissions vary by visa and institution",
        proof_of_funds_summary="University offer + financial / sponsorship evidence for student residence",
        language_requirements="English-medium common at international campuses (IELTS/TOEFL)",
    ),
    "IN": CountryComparisonItem(
        country_code="IN",
        tuition_band="INR wide range — public institutes lower; private / international campuses higher",
        psw_rights="Foreign students: exit typically after programme unless separately employed under applicable rules",
        dependent_rules="Dependent visas via eligible categories where available",
        work_limits="Internship / work permissions for foreign students are tightly regulated",
        proof_of_funds_summary="Admission offer + bank evidence as required by the institution / visa category",
        language_requirements="English-medium widespread; some programmes require entrance tests (JEE/NEET/CUET etc.)",
    ),
    "RU": CountryComparisonItem(
        country_code="RU",
        tuition_band="RUB — public universities often moderate; English-taught tracks higher",
        psw_rights="Post-study stay is not a broad open PSW model — work/residence requires separate authorization",
        dependent_rules="Family accompaniment under applicable migration categories",
        work_limits="Student work permissions exist with limits; confirm current migration rules",
        proof_of_funds_summary="Invitation / enrolment + financial evidence for student visa",
        language_requirements="Russian-taught majority; English-taught available (IELTS/TOEFL for English tracks)",
    ),
}


def _normalize_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def glossary_to_dict(row: IntelGlossary) -> dict[str, Any]:
    return {
        "id": row.id,
        "term_name": row.term_name,
        "slug": row.slug,
        "category": row.category,
        "country_code": row.country_code,
        "lifecycle_stage": row.lifecycle_stage,
        "short_definition": row.short_definition,
        "full_explanation": row.full_explanation,
        "key_metrics": row.key_metrics or {},
        "tags": _normalize_tags(row.tags),
        "official_source_url": row.official_source_url,
        "is_student_facing": bool(row.is_student_facing),
        "last_verified_at": row.last_verified_at,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_glossary_terms(
    db: Session,
    *,
    q: str | None = None,
    country_code: str | None = None,
    lifecycle_stage: str | None = None,
    category: str | None = None,
    status: str | None = "ACTIVE",
    sort_by: SortField = "updated",
    sort_dir: SortDir = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[IntelGlossary], int]:
    query = db.query(IntelGlossary)
    if status and status.upper() != "ALL":
        query = query.filter(IntelGlossary.status == status.upper())
    if country_code:
        query = query.filter(IntelGlossary.country_code == country_code.upper())
    if lifecycle_stage:
        query = query.filter(IntelGlossary.lifecycle_stage == lifecycle_stage)
    if category:
        query = query.filter(IntelGlossary.category == category)

    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                IntelGlossary.term_name.ilike(needle),
                IntelGlossary.short_definition.ilike(needle),
                IntelGlossary.full_explanation.ilike(needle),
                IntelGlossary.category.ilike(needle),
                IntelGlossary.slug.ilike(needle),
            )
        )

    total = query.count()
    descending = (sort_dir or "asc").lower() == "desc"

    def order(column):
        return desc(column) if descending else asc(column)

    normalized = "term" if sort_by == "alpha" else sort_by
    if normalized == "term":
        query = query.order_by(order(IntelGlossary.term_name))
    elif normalized == "country":
        query = query.order_by(order(IntelGlossary.country_code), asc(IntelGlossary.term_name))
    elif normalized == "category":
        query = query.order_by(order(IntelGlossary.category), asc(IntelGlossary.term_name))
    elif normalized == "lifecycle":
        query = query.order_by(order(IntelGlossary.lifecycle_stage), asc(IntelGlossary.term_name))
    elif normalized == "definition":
        query = query.order_by(order(IntelGlossary.short_definition), asc(IntelGlossary.term_name))
    elif normalized == "source":
        query = query.order_by(order(IntelGlossary.official_source_url), asc(IntelGlossary.term_name))
    else:
        query = query.order_by(order(IntelGlossary.updated_at), asc(IntelGlossary.term_name))

    page = max(1, page)
    page_size = min(max(page_size, 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return rows, total


def get_glossary_by_slug(db: Session, slug: str) -> IntelGlossary | None:
    normalized = (slug or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(IntelGlossary)
        .filter(IntelGlossary.slug == normalized, IntelGlossary.status == "ACTIVE")
        .first()
    )


def get_glossary_by_id(db: Session, term_id: UUID) -> IntelGlossary | None:
    return db.query(IntelGlossary).filter(IntelGlossary.id == term_id).first()


def _ensure_unique_slug(db: Session, slug: str, *, exclude_id: UUID | None = None) -> str:
    base = slugify(slug)
    candidate = base
    suffix = 2
    while True:
        query = db.query(IntelGlossary).filter(IntelGlossary.slug == candidate)
        if exclude_id is not None:
            query = query.filter(IntelGlossary.id != exclude_id)
        if not query.first():
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def create_glossary_term(db: Session, payload: dict[str, Any]) -> IntelGlossary:
    term_name = (payload.get("term_name") or "").strip()
    if not term_name:
        raise HTTPException(status_code=400, detail="term_name is required.")
    slug = _ensure_unique_slug(db, payload.get("slug") or term_name)
    now = datetime.now(timezone.utc)
    row = IntelGlossary(
        term_name=term_name,
        slug=slug,
        category=payload["category"],
        country_code=str(payload["country_code"]).upper(),
        lifecycle_stage=payload["lifecycle_stage"],
        short_definition=payload["short_definition"].strip(),
        full_explanation=(payload.get("full_explanation") or None),
        key_metrics=payload.get("key_metrics") or {},
        tags=payload.get("tags") or [],
        official_source_url=payload.get("official_source_url") or None,
        is_student_facing=bool(payload.get("is_student_facing", False)),
        status=(payload.get("status") or "ACTIVE").upper(),
        last_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_glossary_term(db: Session, term_id: UUID, payload: dict[str, Any]) -> IntelGlossary:
    row = get_glossary_by_id(db, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Term not found.")

    if "term_name" in payload and payload["term_name"] is not None:
        row.term_name = payload["term_name"].strip()
    if "slug" in payload and payload["slug"]:
        row.slug = _ensure_unique_slug(db, payload["slug"], exclude_id=row.id)
    if "category" in payload and payload["category"] is not None:
        row.category = payload["category"]
    if "country_code" in payload and payload["country_code"] is not None:
        row.country_code = str(payload["country_code"]).upper()
    if "lifecycle_stage" in payload and payload["lifecycle_stage"] is not None:
        row.lifecycle_stage = payload["lifecycle_stage"]
    if "short_definition" in payload and payload["short_definition"] is not None:
        row.short_definition = payload["short_definition"].strip()
    if "full_explanation" in payload:
        row.full_explanation = payload["full_explanation"]
    if "key_metrics" in payload:
        row.key_metrics = payload["key_metrics"] or {}
    if "tags" in payload and payload["tags"] is not None:
        row.tags = payload["tags"]
    if "official_source_url" in payload:
        row.official_source_url = payload["official_source_url"] or None
    if "is_student_facing" in payload and payload["is_student_facing"] is not None:
        row.is_student_facing = bool(payload["is_student_facing"])
    if "status" in payload and payload["status"] is not None:
        row.status = str(payload["status"]).upper()

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def archive_glossary_term(db: Session, term_id: UUID) -> IntelGlossary:
    return update_glossary_term(db, term_id, {"status": "ARCHIVED"})


def delete_glossary_term(db: Session, term_id: UUID) -> dict[str, Any]:
    row = get_glossary_by_id(db, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Term not found.")
    payload = {"id": str(row.id), "term_name": row.term_name, "slug": row.slug}
    db.delete(row)
    db.commit()
    return payload


def delete_glossary_terms_bulk(db: Session, term_ids: list[UUID]) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(term_ids))
    if not unique_ids:
        return {"deleted": 0, "skipped": 0, "ids": []}

    rows = db.query(IntelGlossary).filter(IntelGlossary.id.in_(unique_ids)).all()
    found_ids = [row.id for row in rows]
    skipped = len(unique_ids) - len(found_ids)
    for row in rows:
        db.delete(row)
    db.commit()
    return {
        "deleted": len(found_ids),
        "skipped": skipped,
        "ids": [str(item) for item in found_ids],
    }


def get_or_create_preferences(db: Session, user_id: int) -> IntelUserPreferences:
    prefs = db.query(IntelUserPreferences).filter(IntelUserPreferences.user_id == user_id).first()
    if prefs:
        return prefs
    prefs = IntelUserPreferences(user_id=user_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


def preferences_to_read(prefs: IntelUserPreferences) -> IntelPreferencesRead:
    countries = prefs.preferred_countries if isinstance(prefs.preferred_countries, list) else [
        "UK",
        "CA",
        "AU",
        "DE",
        "US",
        "JP",
        "FR",
        "AE",
        "NZ",
        "SG",
        "IE",
        "NL",
        "NO",
        "PL",
        "HK",
        "MY",
        "QA",
        "IN",
        "RU",
        "SE",
        "CH",
    ]
    return IntelPreferencesRead(
        enable_daily_trivia=bool(prefs.enable_daily_trivia),
        enable_contextual_tips=bool(prefs.enable_contextual_tips),
        preferred_countries=[str(c).upper() for c in countries],
        trivia_streak=int(prefs.trivia_streak or 0),
        trivia_correct_count=int(prefs.trivia_correct_count or 0),
    )


def update_preferences(
    db: Session, user_id: int, payload: IntelPreferencesUpdate
) -> IntelPreferencesRead:
    prefs = get_or_create_preferences(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "preferred_countries" in data and data["preferred_countries"] is not None:
        data["preferred_countries"] = [str(c).upper() for c in data["preferred_countries"]]
    for key, value in data.items():
        setattr(prefs, key, value)
    prefs.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(prefs)
    return preferences_to_read(prefs)


def get_daily_trivia(db: Session, user_id: int, *, on_date: date | None = None) -> dict[str, Any] | None:
    prefs = get_or_create_preferences(db, user_id)
    if not prefs.enable_daily_trivia:
        return None

    active = on_date or date.today()
    trivia = db.query(IntelTrivia).filter(IntelTrivia.active_date == active).first()
    if not trivia:
        trivia = db.query(IntelTrivia).order_by(desc(IntelTrivia.active_date)).first()
    if not trivia:
        return None

    answer = (
        db.query(IntelTriviaAnswer)
        .filter(IntelTriviaAnswer.user_id == user_id, IntelTriviaAnswer.trivia_id == trivia.id)
        .first()
    )
    payload: dict[str, Any] = {
        "id": trivia.id,
        "question": trivia.question,
        "options": trivia.options if isinstance(trivia.options, list) else [],
        "country_code": trivia.country_code,
        "active_date": trivia.active_date,
        "already_answered": bool(answer),
        "selected_option_index": answer.selected_option_index if answer else None,
        "is_correct": answer.is_correct if answer else None,
        "explanation": trivia.explanation if answer else None,
        "streak": prefs.trivia_streak,
        "correct_count": prefs.trivia_correct_count,
    }
    return payload


def answer_trivia(
    db: Session, user_id: int, trivia_id: UUID, selected_option_index: int
) -> dict[str, Any]:
    trivia = db.query(IntelTrivia).filter(IntelTrivia.id == trivia_id).first()
    if not trivia:
        raise HTTPException(status_code=404, detail="Trivia question not found.")

    existing = (
        db.query(IntelTriviaAnswer)
        .filter(IntelTriviaAnswer.user_id == user_id, IntelTriviaAnswer.trivia_id == trivia.id)
        .first()
    )
    if existing:
        prefs = get_or_create_preferences(db, user_id)
        return {
            "is_correct": existing.is_correct,
            "correct_option_index": trivia.correct_option_index,
            "explanation": trivia.explanation,
            "streak": prefs.trivia_streak,
            "correct_count": prefs.trivia_correct_count,
        }

    is_correct = selected_option_index == trivia.correct_option_index
    db.add(
        IntelTriviaAnswer(
            user_id=user_id,
            trivia_id=trivia.id,
            selected_option_index=selected_option_index,
            is_correct=is_correct,
        )
    )
    prefs = get_or_create_preferences(db, user_id)
    if is_correct:
        prefs.trivia_streak = int(prefs.trivia_streak or 0) + 1
        prefs.trivia_correct_count = int(prefs.trivia_correct_count or 0) + 1
    else:
        prefs.trivia_streak = 0
    prefs.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(prefs)
    return {
        "is_correct": is_correct,
        "correct_option_index": trivia.correct_option_index,
        "explanation": trivia.explanation,
        "streak": prefs.trivia_streak,
        "correct_count": prefs.trivia_correct_count,
    }


def list_academy_modules(db: Session) -> list[IntelAcademyModule]:
    return (
        db.query(IntelAcademyModule)
        .filter(IntelAcademyModule.is_active.is_(True))
        .order_by(IntelAcademyModule.sort_order.asc(), IntelAcademyModule.title.asc())
        .all()
    )


def calculate_proof_of_funds(payload: ProofOfFundsRequest) -> ProofOfFundsResponse:
    if payload.country_code not in COUNTRY_FUNDS:
        raise HTTPException(status_code=400, detail=f"Unsupported country: {payload.country_code}")
    rules = COUNTRY_FUNDS[payload.country_code]
    scholarships = payload.scholarships or 0
    net_tuition = max(0.0, payload.tuition - scholarships)
    living = payload.living_costs
    required = net_tuition + living
    holding_days = int(rules.get("holding_days", 28))
    notes = list(rules.get("notes") or [])
    breakdown: dict[str, float] = {
        "tuition_net": round(net_tuition, 2),
        "living_costs": round(living, 2),
        "scholarships": round(scholarships, 2),
    }

    if payload.country_code == "CA" and rules.get("gic_amount"):
        required = max(required, float(rules["gic_amount"]) + net_tuition)
        notes.append(f"SDS GIC baseline currently modeled at {rules['gic_amount']} CAD.")
        breakdown["gic_amount"] = float(rules["gic_amount"])
    if payload.country_code == "DE" and rules.get("blocked_account"):
        required = max(required, float(rules["blocked_account"]) + net_tuition)
        notes.append("Blocked-account living cost guideline applied.")
        breakdown["blocked_account"] = float(rules["blocked_account"])
    if payload.country_code == "AU" and rules.get("living_annual"):
        required = max(required, float(rules["living_annual"]) + net_tuition)
        breakdown["living_annual_guideline"] = float(rules["living_annual"])
    if payload.country_code == "NZ" and rules.get("living_annual"):
        required = max(required, float(rules["living_annual"]) + net_tuition)
        notes.append(
            f"NZ living-cost guideline applied at NZD ${rules['living_annual']:,.0f}/year (plus tuition)."
        )
        breakdown["living_annual_guideline"] = float(rules["living_annual"])
    if payload.country_code == "SE" and rules.get("living_monthly"):
        se_living = float(rules["living_monthly"]) * 12
        required = max(required, se_living + net_tuition)
        notes.append(
            f"Sweden means-of-support modeled at SEK {rules['living_monthly']:,.0f}/month × 12."
        )
        breakdown["living_annual_guideline"] = se_living
    if payload.country_code == "US" and rules.get("i20_first_year"):
        notes.append(
            "Modeled as I-20 first-year total (tuition + living − scholarships). Match the issuing school's I-20 figures."
        )
        breakdown["i20_first_year_total"] = round(required, 2)
    if payload.country_code == "JP" and rules.get("coe_min_funds"):
        coe_min = float(rules["coe_min_funds"])
        coe_low = float(rules.get("coe_min_funds_low") or coe_min)
        if required < coe_low:
            notes.append(
                f"Entered total is below the common ¥{coe_low:,.0f}–¥{coe_min:,.0f} CoE evidence range; confirm with the school/sponsor."
            )
        if required < coe_min:
            required = coe_min
            notes.append(f"Raised to ¥{coe_min:,.0f} CoE first-year guideline floor.")
        breakdown["coe_guideline_min"] = coe_min
        breakdown["coe_guideline_low"] = coe_low

    return ProofOfFundsResponse(
        country_code=payload.country_code,
        required_balance=round(required, 2),
        currency=str(rules["currency"]),
        holding_days=holding_days,
        breakdown=breakdown,
        notes=notes,
    )


def compare_countries(country_codes: list[str]) -> list[CountryComparisonItem]:
    unique: list[str] = []
    for code in country_codes:
        upper = (code or "").strip().upper()
        if upper and upper not in unique:
            unique.append(upper)
    if not unique:
        raise HTTPException(status_code=400, detail="Select at least one country.")
    if len(unique) > 3:
        raise HTTPException(status_code=400, detail="Compare up to 3 countries.")
    missing = [code for code in unique if code not in COMPARISON_MATRIX]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unsupported countries: {', '.join(missing)}")
    return [COMPARISON_MATRIX[code] for code in unique]


def scraper_config_to_read(db: Session, row: IntelScraperConfig) -> dict[str, Any]:
    glossary = _find_glossary_for_scraper(db, row)
    return {
        "id": row.id,
        "source_name": row.source_name,
        "target_url": row.target_url,
        "country_code": row.country_code,
        "scrape_interval_hours": row.scrape_interval_hours,
        "last_run_at": row.last_run_at,
        "status": row.status,
        "last_error": row.last_error,
        "last_content_hash": row.last_content_hash,
        "last_fetched_at": row.last_fetched_at,
        "last_http_status": row.last_http_status,
        "linked_glossary_id": glossary.id if glossary else None,
        "linked_glossary_term": glossary.term_name if glossary else None,
    }


def list_scraper_configs(db: Session) -> list[dict[str, Any]]:
    rows = db.query(IntelScraperConfig).order_by(IntelScraperConfig.source_name.asc()).all()
    return [scraper_config_to_read(db, row) for row in rows]


def update_scraper_interval(db: Session, config_id: UUID, hours: int) -> dict[str, Any]:
    row = db.query(IntelScraperConfig).filter(IntelScraperConfig.id == config_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scraper config not found.")
    row.scrape_interval_hours = hours
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return scraper_config_to_read(db, row)


def _scraper_is_due(row: IntelScraperConfig, *, now: datetime) -> bool:
    if row.last_run_at is None:
        return True
    last = row.last_run_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    hours = max(1, int(row.scrape_interval_hours or 168))
    return (now - last).total_seconds() >= hours * 3600


def _find_glossary_for_scraper(db: Session, row: IntelScraperConfig) -> IntelGlossary | None:
    """Best-effort link: exact official URL match, else same host + country."""
    from app.services.intel_scraper import same_source_host

    exact = (
        db.query(IntelGlossary)
        .filter(
            IntelGlossary.status == "ACTIVE",
            IntelGlossary.official_source_url == row.target_url,
        )
        .order_by(asc(IntelGlossary.term_name))
        .first()
    )
    if exact:
        return exact

    candidates = (
        db.query(IntelGlossary)
        .filter(
            IntelGlossary.status == "ACTIVE",
            IntelGlossary.country_code == row.country_code,
            IntelGlossary.official_source_url.isnot(None),
        )
        .all()
    )
    for glossary in candidates:
        if same_source_host(glossary.official_source_url, row.target_url):
            return glossary
    return None


def _pending_review_exists(
    db: Session, *, config_id: UUID, content_hash: str, new_text: str
) -> bool:
    pending = (
        db.query(IntelScrapeReview)
        .filter(
            IntelScrapeReview.scraper_config_id == config_id,
            IntelScrapeReview.status == "NEEDS_REVIEW",
        )
        .order_by(desc(IntelScrapeReview.detected_at))
        .limit(5)
        .all()
    )
    for review in pending:
        if review.new_text == new_text:
            return True
        # Hash of stored new_text for soft dedupe when truncation differs slightly.
        from app.services.intel_scraper import content_hash as hash_text

        if hash_text(review.new_text or "") == content_hash:
            return True
    return False


def run_scraper(
    db: Session,
    config_id: UUID | None = None,
    config_ids: list[UUID] | None = None,
    *,
    due_only: bool = False,
) -> dict[str, Any]:
    """Fetch configured regulatory URLs and open NEEDS_REVIEW rows on content change."""
    from app.services.intel_scraper import build_diff_summary, fetch_url_text

    query = db.query(IntelScraperConfig)
    ids = list(dict.fromkeys(config_ids or []))
    if config_id and config_id not in ids:
        ids.append(config_id)
    if ids:
        query = query.filter(IntelScraperConfig.id.in_(ids))
    rows = query.all()
    if not rows:
        raise HTTPException(status_code=404, detail="No scraper configs found.")

    now = datetime.now(timezone.utc)
    if due_only:
        rows = [row for row in rows if _scraper_is_due(row, now=now)]
        if not rows:
            return {
                "ran": 0,
                "reviews_created": 0,
                "unchanged": 0,
                "errors": 0,
                "skipped": "none_due",
            }

    created_reviews = 0
    unchanged = 0
    errors = 0

    for row in rows:
        row.status = "RUNNING"
        db.flush()
        try:
            fetched = fetch_url_text(row.target_url)
            new_text = fetched["text"]
            new_hash = fetched["hash"]
            previous_text = row.last_content_text
            previous_hash = row.last_content_hash

            row.last_http_status = int(fetched["http_status"])
            row.last_fetched_at = now
            row.last_run_at = now
            row.last_error = None

            glossary = _find_glossary_for_scraper(db, row)
            glossary_id = glossary.id if glossary else None

            if not previous_hash:
                # First successful snapshot — store baseline and queue for human acknowledgement.
                row.last_content_hash = new_hash
                row.last_content_text = new_text
                if not _pending_review_exists(
                    db, config_id=row.id, content_hash=new_hash, new_text=new_text
                ):
                    db.add(
                        IntelScrapeReview(
                            scraper_config_id=row.id,
                            glossary_id=glossary_id,
                            old_text=None,
                            new_text=new_text,
                            diff_summary=(
                                f"Initial live baseline captured from {row.source_name}. "
                                "Review the extracted page text; approving links it as verified "
                                "source content without auto-overwriting unrelated glossary terms "
                                "unless a matching glossary URL is linked."
                            ),
                            status="NEEDS_REVIEW",
                        )
                    )
                    created_reviews += 1
            elif previous_hash == new_hash:
                unchanged += 1
            else:
                # Content changed — do not overwrite glossary automatically.
                if not _pending_review_exists(
                    db, config_id=row.id, content_hash=new_hash, new_text=new_text
                ):
                    db.add(
                        IntelScrapeReview(
                            scraper_config_id=row.id,
                            glossary_id=glossary_id,
                            old_text=previous_text,
                            new_text=new_text,
                            diff_summary=build_diff_summary(
                                previous_text, new_text, source_name=row.source_name
                            ),
                            status="NEEDS_REVIEW",
                        )
                    )
                    created_reviews += 1
                # Keep previous snapshot until human approval applies the new text.
                # Still record that we observed a newer hash on the config for operators.
                row.last_error = None

            row.status = "IDLE"
            row.updated_at = now
        except Exception as exc:  # noqa: BLE001
            errors += 1
            row.status = "ERROR"
            row.last_error = str(exc)[:2000]
            row.last_run_at = now
            row.updated_at = now
            logger.exception("Nexus Intel scraper failed for %s", row.source_name)

    db.commit()
    return {
        "ran": len(rows),
        "reviews_created": created_reviews,
        "unchanged": unchanged,
        "errors": errors,
    }


def run_due_scrapers(db: Session) -> dict[str, Any]:
    """Background tick: only run configs whose interval has elapsed."""
    return run_scraper(db, due_only=True)


def list_scrape_reviews(db: Session, *, status: str = "NEEDS_REVIEW") -> list[IntelScrapeReview]:
    from sqlalchemy.orm import joinedload

    return (
        db.query(IntelScrapeReview)
        .options(joinedload(IntelScrapeReview.scraper_config))
        .filter(IntelScrapeReview.status == status)
        .order_by(desc(IntelScrapeReview.detected_at))
        .all()
    )


def _apply_approved_review_side_effects(db: Session, review: IntelScrapeReview) -> None:
    """Accept scraped snapshot on the scraper config; optionally refresh linked glossary copy."""
    from app.services.intel_scraper import content_hash, normalize_content_text

    now = datetime.now(timezone.utc)
    config = review.scraper_config
    if config is None:
        config = (
            db.query(IntelScraperConfig)
            .filter(IntelScraperConfig.id == review.scraper_config_id)
            .first()
        )
    if config and review.new_text:
        normalized = normalize_content_text(review.new_text)
        config.last_content_text = normalized
        config.last_content_hash = content_hash(normalized)
        config.last_fetched_at = config.last_fetched_at or now
        config.updated_at = now
        config.status = "IDLE"
        config.last_error = None

    if review.glossary_id and review.new_text:
        glossary = db.query(IntelGlossary).filter(IntelGlossary.id == review.glossary_id).first()
        if glossary:
            # Keep curated short_definition; refresh long explanation from approved scrape excerpt.
            excerpt = normalize_content_text(review.new_text)
            if len(excerpt) > 8000:
                excerpt = excerpt[:8000].rstrip() + "…"
            glossary.full_explanation = excerpt
            glossary.status = "ACTIVE"
            glossary.last_verified_at = now
            glossary.updated_at = now


def approve_scrape_review(
    db: Session,
    review_id: UUID,
    user_id: int,
    *,
    commit: bool = True,
) -> IntelScrapeReview:
    from sqlalchemy.orm import joinedload

    review = (
        db.query(IntelScrapeReview)
        .options(joinedload(IntelScrapeReview.scraper_config))
        .filter(IntelScrapeReview.id == review_id)
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")
    if (review.status or "").strip().upper() != "NEEDS_REVIEW":
        raise HTTPException(status_code=400, detail="Review is not pending approval.")
    review.status = "APPROVED"
    review.reviewed_by = user_id
    review.reviewed_at = datetime.now(timezone.utc)
    _apply_approved_review_side_effects(db, review)
    if commit:
        db.commit()
        db.refresh(review)
    else:
        db.flush()
    return review


def scrape_review_to_read(row: IntelScrapeReview) -> dict[str, Any]:
    source_name = None
    try:
        if row.scraper_config is not None:
            source_name = row.scraper_config.source_name
    except Exception:  # noqa: BLE001
        source_name = None
    return {
        "id": row.id,
        "scraper_config_id": row.scraper_config_id,
        "source_name": source_name,
        "glossary_id": row.glossary_id,
        "detected_at": row.detected_at,
        "old_text": row.old_text,
        "new_text": row.new_text,
        "diff_summary": row.diff_summary,
        "status": row.status,
    }


def approve_scrape_reviews_bulk(
    db: Session, review_ids: list[UUID], user_id: int
) -> dict[str, Any]:
    from sqlalchemy.orm import joinedload

    unique_ids = list(dict.fromkeys(review_ids))
    if not unique_ids:
        return {"approved": 0, "skipped": 0, "items": []}

    rows = (
        db.query(IntelScrapeReview)
        .options(joinedload(IntelScrapeReview.scraper_config))
        .filter(
            IntelScrapeReview.id.in_(unique_ids),
            IntelScrapeReview.status == "NEEDS_REVIEW",
        )
        .all()
    )
    found_ids = {row.id for row in rows}
    skipped = len(unique_ids) - len(found_ids)
    now = datetime.now(timezone.utc)
    approved_payloads: list[dict[str, Any]] = []

    for row in rows:
        row.status = "APPROVED"
        row.reviewed_by = user_id
        row.reviewed_at = now
        _apply_approved_review_side_effects(db, row)
        payload = scrape_review_to_read(row)
        payload["status"] = "APPROVED"
        approved_payloads.append(payload)

    db.commit()
    return {
        "approved": len(approved_payloads),
        "skipped": skipped,
        "items": approved_payloads,
    }


def slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return text.strip("-") or "term"


def inquiry_taxonomy() -> list[dict[str, Any]]:
    return INQUIRY_TAXONOMY


def list_inquiry_faqs(
    db: Session,
    *,
    paths: list[str] | None = None,
    q: str | None = None,
) -> tuple[list[IntelInquiryFaq], int]:
    query = db.query(IntelInquiryFaq).filter(IntelInquiryFaq.is_active.is_(True))
    selected_paths = list(dict.fromkeys(path for path in (paths or []) if path))
    if selected_paths:
        hierarchy_filters = []
        for path in selected_paths:
            hierarchy = resolve_inquiry_path(path)
            if hierarchy["nested_process_code"]:
                hierarchy_filters.append(IntelInquiryFaq.nested_process_code == path)
            elif hierarchy["subprocess_code"]:
                hierarchy_filters.append(IntelInquiryFaq.subprocess_code == path)
            else:
                hierarchy_filters.append(IntelInquiryFaq.process_code == path)
        query = query.filter(or_(*hierarchy_filters))
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                IntelInquiryFaq.question.ilike(term),
                IntelInquiryFaq.answer.ilike(term),
                IntelInquiryFaq.process_name.ilike(term),
                IntelInquiryFaq.subprocess_name.ilike(term),
                IntelInquiryFaq.nested_process_name.ilike(term),
            )
        )
    total = query.count()
    rows = query.order_by(
        IntelInquiryFaq.process_code.asc(),
        IntelInquiryFaq.subprocess_code.asc().nullsfirst(),
        IntelInquiryFaq.nested_process_code.asc().nullsfirst(),
        IntelInquiryFaq.sort_order.asc(),
        IntelInquiryFaq.created_at.asc(),
    ).all()
    return rows, total


def create_inquiry_faq(
    db: Session, payload: dict[str, Any], user_id: int
) -> IntelInquiryFaq:
    hierarchy = resolve_inquiry_path(payload.pop("path"))
    row = IntelInquiryFaq(**hierarchy, **payload, created_by=user_id, updated_by=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_inquiry_faq(
    db: Session, faq_id: UUID, payload: dict[str, Any], user_id: int
) -> IntelInquiryFaq:
    row = db.query(IntelInquiryFaq).filter(IntelInquiryFaq.id == faq_id).first()
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Inquiry not found.")
    path = payload.pop("path", None)
    if path is not None:
        for key, value in resolve_inquiry_path(path).items():
            setattr(row, key, value)
    for key, value in payload.items():
        setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def delete_inquiry_faq(db: Session, faq_id: UUID, user_id: int) -> None:
    row = db.query(IntelInquiryFaq).filter(IntelInquiryFaq.id == faq_id).first()
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Inquiry not found.")
    row.is_active = False
    row.updated_by = user_id
    db.commit()
