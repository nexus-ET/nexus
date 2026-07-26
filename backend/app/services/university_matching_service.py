"""Phase 1 university shortlisting: soft filters + heuristic WSM scoring.

Uses existing student and academia catalog data only. Fit bands are heuristic
confidence labels — not statistical admission probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.academia_institution import Institution
from app.models.academia_wizard import InstitutionCourseOffering, InstitutionIntake
from app.models.candidate_education import CandidateEducation
from app.models.candidate_test_score import CandidateTestScore
from app.models.counselling_booking import CounsellingBooking
from app.models.digital_presence_link import DigitalPresenceLink
from app.models.lead import Lead
from app.models.research_project import ResearchProject
from app.models.target_course import TargetCourse
from app.models.university_matching import (
    MatchingShortlistItem,
    MatchingShortlistRun,
    MatchingWeightProfile,
)
from app.models.user import User
from app.models.work_experience import WorkExperience
from app.schemas.student_aspirations import StudentAspirationsData, migrate_legacy_aspirations_data
from app.services.student_aspirations_service import find_students_master_for_booking

ALGORITHM_VERSION = "phase1-v1"
CLASSIFICATION_MODE = "heuristic_fit"
DEFAULT_LIMIT = 40

DISCLAIMER = (
    "Phase 1 fit confidence only. Safe/Target/Reach are heuristics from "
    "existing profile and catalog data — not admission probability."
)

GPA_BAND_SCORE: dict[str, float] = {
    "GPA_375_400": 95,
    "GPA_350_374": 85,
    "GPA_300_349": 72,
    "GPA_250_299": 55,
    "GPA_200_249": 40,
    "GPA_BELOW_200": 20,
    "CGPA_900_1000": 95,
    "CGPA_800_899": 85,
    "CGPA_700_799": 72,
    "CGPA_600_699": 55,
    "CGPA_500_599": 40,
    "CGPA_BELOW_500": 20,
    "PCT_90_100": 95,
    "PCT_80_89": 85,
    "PCT_70_79": 72,
    "PCT_60_69": 55,
    "PCT_50_59": 40,
    "PCT_BELOW_50": 20,
}

RANKING_CODE_TO_LABEL: dict[str, str] = {
    "TOP_100_GLOBAL_ELITE": "Top 100 (Global Elite)",
    "TOP_300_RESEARCH_INTENSIVE": "Top 300 (Highly Research-Intensive)",
    "TOP_500_BROAD_ACADEMIC": "Top 500 (Broad Academic Excellence)",
    "ANY_INCLUSIVE": "Others",
}

RANKING_LABEL_TO_CODE: dict[str, str] = {v: k for k, v in RANKING_CODE_TO_LABEL.items()}
RANKING_LABEL_TO_CODE["Others"] = "ANY_INCLUSIVE"

RANKING_SELECTIVITY: dict[str, float] = {
    "TOP_100_GLOBAL_ELITE": 90,
    "TOP_300_RESEARCH_INTENSIVE": 70,
    "TOP_500_BROAD_ACADEMIC": 50,
    "ANY_INCLUSIVE": 30,
}

INSTITUTION_TYPE_CODE_TO_LABEL: dict[str, str] = {
    "PUBLIC_STATE_UNIVERSITY": "Public / State University",
    "PRIVATE_UNIVERSITY": "Private University",
    "COMMUNITY_COLLEGE_TECHNICAL": "Community College / Technical Institute",
    "ANY": "Others",
}

ENGLISH_TESTS = {"IELTS", "TOEFL", "PTE", "DUOLINGO"}
APTITUDE_TESTS = {"GRE", "SAT", "GMAT", "ACT"}

INTAKE_SEASON_MONTHS: dict[str, set[int]] = {
    "JAN_FEB_SPRING": {1, 2},
    "APR_MAY_SUMMER": {4, 5},
    "JUL_AUG_SEP_OCT_AUTUMN": {7, 8, 9, 10},
    "FEB_MAR_SEM1_AUS_NZ": {2, 3},
    "JUL_AUG_SEM2_AUS_NZ": {7, 8},
    "APRIL_JAPAN": {4},
}


@dataclass
class StudentMatchContext:
    aspirations: StudentAspirationsData
    gpa_band_code: str | None = None
    gpa_band_score: float | None = None
    test_names: set[str] = field(default_factory=set)
    work_years: float = 0.0
    research_count: int = 0
    digital_presence_count: int = 0
    students_master_id: int | None = None
    completeness: float = 0.0


@dataclass
class ScoredCandidate:
    institution: Institution
    offering: InstitutionCourseOffering | None
    course: TargetCourse | None
    country_iso2: str | None
    consolidated: float
    s_academic: float
    s_profile: float
    s_aspirations: float
    s_safety: float
    fit_band: str
    explanation: dict[str, Any]
    primary_pathway: dict[str, Any] | None = None
    matched_pathways: list[dict[str, Any]] = field(default_factory=list)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round2(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _normalize_ranking_code(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if token in RANKING_SELECTIVITY:
        return token
    return RANKING_LABEL_TO_CODE.get(token)


def _months_for_seasons(seasons: list[str]) -> set[int]:
    months: set[int] = set()
    for season in seasons:
        months |= INTAKE_SEASON_MONTHS.get(season, set())
    return months


def _work_years(experiences: list[WorkExperience], today: date | None = None) -> float:
    today = today or date.today()
    total_days = 0
    for exp in experiences:
        if not exp.start_date:
            continue
        end = today if exp.is_current or not exp.end_date else exp.end_date
        if end < exp.start_date:
            continue
        total_days += (end - exp.start_date).days
    return round(total_days / 365.25, 2)


def _load_weight_profile(db: Session, code: str | None) -> MatchingWeightProfile:
    query = db.query(MatchingWeightProfile).filter(MatchingWeightProfile.is_active.is_(True))
    if code:
        profile = query.filter(MatchingWeightProfile.code == code.strip()).first()
        if not profile:
            raise HTTPException(status_code=404, detail=f"Weight profile '{code}' not found.")
        return profile
    profile = query.filter(MatchingWeightProfile.is_default.is_(True)).first()
    if profile:
        return profile
    profile = query.order_by(MatchingWeightProfile.id.asc()).first()
    if not profile:
        raise HTTPException(status_code=500, detail="No matching weight profiles are configured.")
    return profile


def build_student_match_context(
    db: Session,
    booking: CounsellingBooking,
    lead: Lead | None,
) -> StudentMatchContext:
    master = find_students_master_for_booking(db, booking, lead)
    raw = master.aspirations_data if master and isinstance(master.aspirations_data, dict) else {}
    aspirations = StudentAspirationsData.model_validate(migrate_legacy_aspirations_data(raw))

    lead_id = lead.id if lead else None
    educations = (
        db.query(CandidateEducation)
        .filter(
            (CandidateEducation.lead_id == lead_id)
            if lead_id
            else (CandidateEducation.booking_id == booking.id)
        )
        .order_by(CandidateEducation.sort_order.asc(), CandidateEducation.id.asc())
        .all()
    )
    gpa_code = None
    for edu in educations:
        if edu.gpa_cgpa_code:
            gpa_code = edu.gpa_cgpa_code
            break
    if not gpa_code and master and master.gpa_cgpa_code:
        gpa_code = master.gpa_cgpa_code

    test_rows = (
        db.query(CandidateTestScore)
        .filter(
            (CandidateTestScore.lead_id == lead_id)
            if lead_id
            else (CandidateTestScore.booking_id == booking.id)
        )
        .all()
    )
    test_names = {row.test_name.strip().upper() for row in test_rows if row.test_name}

    work = (
        db.query(WorkExperience)
        .filter(
            (WorkExperience.lead_id == lead_id)
            if lead_id
            else (WorkExperience.booking_id == booking.id)
        )
        .all()
    )
    research = (
        db.query(ResearchProject)
        .filter(
            (ResearchProject.lead_id == lead_id)
            if lead_id
            else (ResearchProject.booking_id == booking.id)
        )
        .count()
    )
    digital = (
        db.query(DigitalPresenceLink)
        .filter(
            (DigitalPresenceLink.lead_id == lead_id)
            if lead_id
            else (DigitalPresenceLink.booking_id == booking.id)
        )
        .count()
    )

    signals = [
        bool(aspirations.study_countries_iso2),
        bool(aspirations.global_ranking or aspirations.institution_type),
        bool(aspirations.programs or aspirations.discipline_university_college),
        gpa_code is not None,
        bool(test_names),
        bool(work) or research > 0 or digital > 0,
    ]
    completeness = sum(1 for s in signals if s) / len(signals)

    return StudentMatchContext(
        aspirations=aspirations,
        gpa_band_code=gpa_code,
        gpa_band_score=GPA_BAND_SCORE.get(gpa_code) if gpa_code else None,
        test_names=test_names,
        work_years=_work_years(work),
        research_count=int(research),
        digital_presence_count=int(digital),
        students_master_id=master.id if master else None,
        completeness=completeness,
    )


def _score_academic(ctx: StudentMatchContext, ranking_code: str | None) -> tuple[float, dict[str, Any]]:
    reasons: list[str] = []
    base = ctx.gpa_band_score if ctx.gpa_band_score is not None else 45.0
    if ctx.gpa_band_score is None:
        reasons.append("No GPA/CGPA band on file; using neutral academic baseline.")
    else:
        reasons.append(f"GPA/CGPA band {ctx.gpa_band_code} → {base:.0f}.")

    desired_english = {t for t in ctx.aspirations.english_tests if t in ENGLISH_TESTS}
    desired_aptitude = {t for t in ctx.aspirations.aptitude_tests if t in APTITUDE_TESTS}
    present_english = ctx.test_names & ENGLISH_TESTS
    present_aptitude = ctx.test_names & APTITUDE_TESTS

    test_bonus = 0.0
    if desired_english:
        if present_english & desired_english:
            test_bonus += 12
            reasons.append("Preferred English test score present.")
        elif present_english:
            test_bonus += 6
            reasons.append("English test present (not preferred type).")
        else:
            test_bonus -= 10
            reasons.append("Preferred English test missing.")
    elif present_english:
        test_bonus += 6
        reasons.append("English test on file.")

    if desired_aptitude:
        if present_aptitude & desired_aptitude:
            test_bonus += 10
            reasons.append("Preferred aptitude test score present.")
        elif present_aptitude:
            test_bonus += 4
        else:
            if "NOT_REQUIRED_TEST_OPTIONAL" not in ctx.aspirations.aptitude_tests:
                test_bonus -= 6
                reasons.append("Preferred aptitude test missing.")
    elif present_aptitude:
        test_bonus += 4

    score = _clamp(base + test_bonus)

    selectivity = RANKING_SELECTIVITY.get(ranking_code or "", 40)
    if ctx.gpa_band_score is not None and selectivity >= 85 and ctx.gpa_band_score < 70:
        score = _clamp(score - 12)
        reasons.append("Soft penalty: elite ranking vs lower GPA band.")

    return score, {"reasons": reasons, "gpa_band_code": ctx.gpa_band_code}


def _score_profile(ctx: StudentMatchContext) -> tuple[float, dict[str, Any]]:
    work_pts = min(ctx.work_years / 5.0 * 40.0, 40.0)
    research_pts = min(ctx.research_count * 15.0, 30.0)
    digital_pts = min(ctx.digital_presence_count * 10.0, 30.0)
    baseline = 15.0 if (work_pts + research_pts + digital_pts) == 0 else 0.0
    score = _clamp(baseline + work_pts + research_pts + digital_pts)
    return score, {
        "work_years": ctx.work_years,
        "research_count": ctx.research_count,
        "digital_presence_count": ctx.digital_presence_count,
        "reasons": [
            f"Work experience ≈ {ctx.work_years:.1f}y → {work_pts:.0f}",
            f"Research projects {ctx.research_count} → {research_pts:.0f}",
            f"Digital presence links {ctx.digital_presence_count} → {digital_pts:.0f}",
        ],
    }


def _normalize_token(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", " ").replace("_", " ")


def _academic_pathway_from_course(
    course: TargetCourse | None,
    *,
    offering_id: int | None = None,
    match_score: float | None = None,
    match_reason: str | None = None,
) -> dict[str, Any] | None:
    if course is None:
        return None

    qualification = getattr(course, "qualification_program", None)
    target_program = getattr(course, "program", None)
    education_major = getattr(course, "education_major", None)

    if qualification is not None:
        program_code = getattr(qualification, "code", None)
        program_name = getattr(qualification, "name", None)
    elif target_program is not None:
        program_code = getattr(target_program, "code", None)
        program_name = getattr(target_program, "label", None)
    else:
        program_code = None
        program_name = None

    if education_major is not None:
        major_code = getattr(education_major, "code", None)
        major_name = getattr(education_major, "label", None)
    elif target_program is not None:
        major_code = getattr(target_program, "code", None)
        major_name = getattr(target_program, "label", None)
    else:
        major_code = None
        major_name = None

    pathway: dict[str, Any] = {
        "offering_id": offering_id,
        "program_code": program_code,
        "program_name": program_name,
        "major_code": major_code,
        "major_name": major_name,
        "course_id": course.id,
        "course_code": course.code,
        "course_label": course.label,
        "course_level": course.level,
    }
    if match_score is not None:
        pathway["match_score"] = round(match_score, 2)
    if match_reason is not None:
        pathway["match_reason"] = match_reason
    return pathway


def _offering_program_match(
    course: TargetCourse | None,
    aspirations: StudentAspirationsData,
) -> tuple[float, str]:
    if course is None:
        return 25.0, "No course offering linked."

    preferred_programs = {
        _normalize_token(p) for p in aspirations.programs if p and p != "OTHER"
    }
    preferred_degrees = {
        _normalize_token(d) for d in aspirations.discipline_university_college if d
    }
    preferred_other = _normalize_token(aspirations.programs_other)

    pathway = _academic_pathway_from_course(course) or {}
    course_code = _normalize_token(course.code)
    course_label = _normalize_token(course.label)
    program_code = _normalize_token(pathway.get("program_code"))
    program_name = _normalize_token(pathway.get("program_name"))
    major_code = _normalize_token(pathway.get("major_code"))
    major_name = _normalize_token(pathway.get("major_name"))
    haystack = " | ".join(
        part for part in (course_code, course_label, program_code, program_name, major_code, major_name) if part
    )

    if preferred_programs:
        if course_code in preferred_programs or program_code in preferred_programs or major_code in preferred_programs:
            return 100.0, f"Course/program matches preference ({course.code or pathway.get('program_code')})."
        if any(
            pref and (pref in haystack or haystack in pref)
            for pref in preferred_programs
            if len(pref) > 3
        ):
            return 82.0, "Program/major/course label soft-matches preferred focus."
        if preferred_other and preferred_other in haystack:
            return 78.0, "Matches custom program preference text."

    if preferred_degrees and (
        program_code in preferred_degrees
        or major_code in preferred_degrees
        or any(d in haystack for d in preferred_degrees if len(d) > 3)
    ):
        return 80.0, "Linked to preferred discipline family."

    if preferred_programs or preferred_degrees:
        return 40.0, "Offering present but not an exact program match."
    return 55.0, "No program preference set; neutral course credit."


def _rank_offerings(
    offerings: list[InstitutionCourseOffering],
    aspirations: StudentAspirationsData,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    ranked: list[tuple[float, InstitutionCourseOffering, TargetCourse | None, str]] = []
    for offering in offerings:
        course = offering.course
        score, reason = _offering_program_match(course, aspirations)
        ranked.append((score, offering, course, reason))
    ranked.sort(
        key=lambda row: (
            -row[0],
            (row[2].label if row[2] and row[2].label else ""),
            row[1].id,
        )
    )

    pathways: list[dict[str, Any]] = []
    for score, offering, course, reason in ranked[: max(1, limit)]:
        pathway = _academic_pathway_from_course(
            course,
            offering_id=offering.id,
            match_score=score,
            match_reason=reason,
        )
        if pathway:
            pathways.append(pathway)
    return pathways


def _score_aspirations(
    ctx: StudentMatchContext,
    institution: Institution,
    country_iso2: str | None,
    ranking_code: str | None,
    course: TargetCourse | None,
    intakes: list[InstitutionIntake],
    *,
    pathway_match_reason: str | None = None,
) -> tuple[float, dict[str, Any]]:
    reasons: list[str] = []
    parts: list[float] = []

    preferred_countries = {c.upper() for c in ctx.aspirations.study_countries_iso2}
    if preferred_countries:
        if country_iso2 and country_iso2.upper() in preferred_countries:
            parts.append(100.0)
            reasons.append(f"Country match ({country_iso2}).")
        else:
            parts.append(0.0)
            reasons.append("Country mismatch (should be filtered).")
    else:
        parts.append(50.0)
        reasons.append("No target countries set; neutral location score.")

    preferred_rankings = set(ctx.aspirations.global_ranking)
    if preferred_rankings:
        if "ANY_INCLUSIVE" in preferred_rankings:
            parts.append(85.0)
            reasons.append("Ranking preference includes Any.")
        elif ranking_code and ranking_code in preferred_rankings:
            parts.append(100.0)
            reasons.append("Ranking tier matches preference.")
        elif ranking_code:
            # Adjacent tiers get partial credit
            order = [
                "TOP_100_GLOBAL_ELITE",
                "TOP_300_RESEARCH_INTENSIVE",
                "TOP_500_BROAD_ACADEMIC",
                "ANY_INCLUSIVE",
            ]
            pref_idx = [order.index(r) for r in preferred_rankings if r in order]
            inst_idx = order.index(ranking_code) if ranking_code in order else None
            if pref_idx and inst_idx is not None and min(abs(inst_idx - i) for i in pref_idx) == 1:
                parts.append(65.0)
                reasons.append("Adjacent ranking tier.")
            else:
                parts.append(35.0)
                reasons.append("Ranking tier outside preference.")
        else:
            parts.append(40.0)
            reasons.append("Institution ranking tier missing.")
    else:
        parts.append(55.0)

    preferred_types = set(ctx.aspirations.institution_type)
    inst_type = (institution.institution_type or "").strip()
    if preferred_types:
        if "ANY" in preferred_types:
            parts.append(85.0)
        else:
            labels = {INSTITUTION_TYPE_CODE_TO_LABEL.get(t, t) for t in preferred_types}
            if inst_type in labels:
                parts.append(100.0)
                reasons.append("Institution type matches.")
            else:
                parts.append(40.0)
                reasons.append("Institution type differs from preference.")
    else:
        parts.append(55.0)

    course_score, course_reason = _offering_program_match(course, ctx.aspirations)
    if pathway_match_reason:
        course_reason = pathway_match_reason
    parts.append(course_score)
    reasons.append(course_reason)

    # Intake year / season soft match
    intake_score = 50.0
    preferred_years = set(ctx.aspirations.intake_years or [])
    preferred_months = _months_for_seasons(ctx.aspirations.intake_seasons or [])
    if preferred_years or preferred_months:
        year_hit = False
        month_hit = False
        for intake in intakes:
            if preferred_years and intake.year and intake.year in preferred_years:
                year_hit = True
            start = intake.start_date or intake.class_start_date
            if preferred_months and start and start.month in preferred_months:
                month_hit = True
        if year_hit and month_hit:
            intake_score = 100.0
            reasons.append("Intake year and season align.")
        elif year_hit or month_hit:
            intake_score = 75.0
            reasons.append("Partial intake year/season alignment.")
        elif intakes:
            intake_score = 35.0
            reasons.append("Intakes exist but do not align with preference.")
        else:
            intake_score = 40.0
            reasons.append("No institution intakes published.")
    else:
        reasons.append("No intake preference; neutral intake credit.")
    parts.append(intake_score)

    # Budget cannot be scored without tuition — stay neutral with explicit note
    if ctx.aspirations.budget:
        parts.append(50.0)
        reasons.append("Budget set but tuition data unavailable (Phase 2).")
    else:
        parts.append(50.0)

    score = _clamp(sum(parts) / len(parts))
    return score, {"reasons": reasons, "component_count": len(parts)}


def _score_safety(s_academic: float, ranking_code: str | None) -> tuple[float, dict[str, Any]]:
    """Heuristic competitiveness vs selectivity — not historical admit probability."""
    selectivity = RANKING_SELECTIVITY.get(ranking_code or "", 40.0)
    delta = s_academic - selectivity
    # Map delta (-100..100) roughly onto 0..100 with center at 55
    score = _clamp(55.0 + delta * 0.7)
    return score, {
        "mode": CLASSIFICATION_MODE,
        "selectivity": selectivity,
        "academic_vs_selectivity_delta": round(delta, 2),
        "reasons": [
            "Heuristic safety from academic strength vs ranking selectivity — not admit odds."
        ],
    }


def classify_fit_band(s_safety: float) -> str:
    if s_safety >= 70:
        return "safe"
    if s_safety >= 40:
        return "target"
    return "reach"


def score_institution(
    ctx: StudentMatchContext,
    institution: Institution,
    country_iso2: str | None,
    offerings: list[InstitutionCourseOffering],
    intakes: list[InstitutionIntake],
    weights: MatchingWeightProfile,
) -> ScoredCandidate | None:
    preferred_countries = {c.upper() for c in ctx.aspirations.study_countries_iso2}
    if preferred_countries:
        if not country_iso2 or country_iso2.upper() not in preferred_countries:
            return None

    ranking_code = _normalize_ranking_code(institution.ranking_tier_global)
    matched_pathways = _rank_offerings(offerings, ctx.aspirations, limit=5)
    primary_pathway = matched_pathways[0] if matched_pathways else None
    offering = None
    course = None
    if primary_pathway and primary_pathway.get("offering_id") is not None:
        offering_id = primary_pathway["offering_id"]
        for candidate_offering in offerings:
            if candidate_offering.id == offering_id:
                offering = candidate_offering
                course = candidate_offering.course
                break

    s_academic, academic_explain = _score_academic(ctx, ranking_code)
    s_profile, profile_explain = _score_profile(ctx)
    s_aspirations, aspirations_explain = _score_aspirations(
        ctx,
        institution,
        country_iso2,
        ranking_code,
        course,
        intakes,
        pathway_match_reason=(primary_pathway or {}).get("match_reason"),
    )
    s_safety, safety_explain = _score_safety(s_academic, ranking_code)

    w1 = float(weights.weight_academic)
    w2 = float(weights.weight_profile)
    w3 = float(weights.weight_aspirations)
    w4 = float(weights.weight_safety)
    consolidated = _clamp(s_academic * w1 + s_profile * w2 + s_aspirations * w3 + s_safety * w4)
    fit_band = classify_fit_band(s_safety)

    return ScoredCandidate(
        institution=institution,
        offering=offering,
        course=course,
        country_iso2=country_iso2,
        consolidated=consolidated,
        s_academic=s_academic,
        s_profile=s_profile,
        s_aspirations=s_aspirations,
        s_safety=s_safety,
        fit_band=fit_band,
        primary_pathway=primary_pathway,
        matched_pathways=matched_pathways,
        explanation={
            "algorithm_version": ALGORITHM_VERSION,
            "classification_mode": CLASSIFICATION_MODE,
            "disclaimer": DISCLAIMER,
            "academic": academic_explain,
            "profile": profile_explain,
            "aspirations": aspirations_explain,
            "safety": safety_explain,
            "primary_pathway": primary_pathway,
            "matched_pathways": matched_pathways,
            "weights": {
                "academic": w1,
                "profile": w2,
                "aspirations": w3,
                "safety": w4,
            },
            "data_completeness": round(ctx.completeness, 2),
        },
    )


def _extract_item_pathway(item: MatchingShortlistItem) -> dict[str, Any] | None:
    explanation = item.explanation if isinstance(item.explanation, dict) else {}
    primary = explanation.get("primary_pathway")
    if isinstance(primary, dict) and (
        primary.get("course_code") or primary.get("program_name") or primary.get("major_name")
    ):
        return primary

    offering = item.offering
    course = offering.course if offering else None
    return _academic_pathway_from_course(
        course,
        offering_id=item.offering_id,
    )


def _serialize_item(item: MatchingShortlistItem) -> dict[str, Any]:
    institution = item.institution
    offering = item.offering
    course = offering.course if offering else None
    country = institution.country if institution else None
    explanation = item.explanation if isinstance(item.explanation, dict) else {}
    primary_pathway = _extract_item_pathway(item)
    matched_pathways = explanation.get("matched_pathways")
    if not isinstance(matched_pathways, list) or not matched_pathways:
        matched_pathways = [primary_pathway] if primary_pathway else []

    return {
        "id": item.id,
        "institution_id": item.institution_id,
        "institution_name": institution.name if institution else None,
        "institution_country_iso2": country.iso2 if country else None,
        "ranking_tier_global": institution.ranking_tier_global if institution else None,
        "institution_type": institution.institution_type if institution else None,
        "offering_id": item.offering_id,
        "program_code": (primary_pathway or {}).get("program_code"),
        "program_name": (primary_pathway or {}).get("program_name"),
        "major_code": (primary_pathway or {}).get("major_code"),
        "major_name": (primary_pathway or {}).get("major_name"),
        "course_code": (primary_pathway or {}).get("course_code")
        or (course.code if course else None),
        "course_label": (primary_pathway or {}).get("course_label")
        or (course.label if course else None),
        "course_level": (primary_pathway or {}).get("course_level")
        or (course.level if course else None),
        "matched_pathways": matched_pathways,
        "rank": item.rank,
        "consolidated_score": item.consolidated_score,
        "s_academic": item.s_academic,
        "s_profile": item.s_profile,
        "s_aspirations": item.s_aspirations,
        "s_safety": item.s_safety,
        "fit_band": item.fit_band,
        "explanation": item.explanation,
    }


def _unique_labeled(items: list[dict[str, Any]], code_key: str, name_key: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in items:
        code = (item.get(code_key) or "").strip()
        name = (item.get(name_key) or "").strip()
        if not code and not name:
            continue
        key = f"{code}|{name}".upper()
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, str] = {}
        if code:
            row["code"] = code
        if name:
            row["name"] = name
        out.append(row)
    return out


_GENERIC_FOCUS_WORDS = {
    "SCIENCE",
    "ARTS",
    "STUDIES",
    "GENERAL",
    "PROGRAM",
    "COURSE",
    "DEGREE",
}


def _token_soft_match(needle: str, *haystacks: str | None) -> bool:
    needle_n = _normalize_token(needle)
    if not needle_n or len(needle_n) < 3:
        return False
    needle_words = {w for w in needle_n.split() if len(w) > 2}
    for raw in haystacks:
        value = _normalize_token(raw)
        if not value:
            continue
        if needle_n == value:
            return True
        if needle_n in value or value in needle_n:
            # Reject short code/label substrings (COM ⊂ COMPUTER SCIENCE).
            if len(value) <= 3 and value != needle_n and value not in needle_words:
                continue
            if len(needle_n) <= 3 and needle_n != value and needle_n not in {
                w for w in value.split() if len(w) > 2
            }:
                continue
            # Reject weak single-token overlaps (e.g. Science ⊂ Computer Science).
            if " " not in value and value in _GENERIC_FOCUS_WORDS:
                continue
            if " " not in needle_n and needle_n in _GENERIC_FOCUS_WORDS and " " in value:
                continue
            return True
        value_words = {w for w in value.split() if len(w) > 2}
        shared = needle_words & value_words
        distinctive = shared - _GENERIC_FOCUS_WORDS
        if len(distinctive) >= 1:
            return True
        if len(shared) >= 2:
            return True
    return False


def derive_catalog_matches_from_aspirations(
    db: Session,
    aspirations: StudentAspirationsData | dict[str, Any],
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Match aspiration focus against global academic catalog when offerings are thin/missing."""
    from app.models.education_course import EducationCourse
    from app.models.education_degree import EducationDegree
    from app.models.education_major import EducationMajor
    from app.models.program import Program
    from app.models.target_course import TargetCourse
    from app.models.target_program import TargetProgram

    if isinstance(aspirations, dict):
        aspirations = StudentAspirationsData.model_validate(
            migrate_legacy_aspirations_data(aspirations)
        )

    preferred_focus = [
        p for p in (aspirations.programs or []) if p and p != "OTHER"
    ]
    if aspirations.programs_other:
        preferred_focus.append(aspirations.programs_other)
    preferred_degrees = list(aspirations.discipline_university_college or [])

    majors = (
        db.query(EducationMajor)
        .filter(EducationMajor.is_active.is_(True))
        .order_by(EducationMajor.sort_order.asc(), EducationMajor.id.asc())
        .all()
    )
    matched_majors: list[dict[str, Any]] = []
    for major in majors:
        if preferred_focus and any(
            _token_soft_match(pref, major.code, major.label) for pref in preferred_focus
        ):
            matched_majors.append(
                {
                    "code": major.code,
                    "name": major.label,
                    "id": major.id,
                    "match_score": 95.0,
                }
            )
    if not matched_majors and preferred_focus:
        # Keep empty — don't invent majors.
        pass

    matched_major_ids = {m["id"] for m in matched_majors if m.get("id") is not None}

    level_ids: set[int] = set()
    if preferred_degrees:
        degrees = (
            db.query(EducationDegree)
            .filter(EducationDegree.code.in_(preferred_degrees), EducationDegree.is_active.is_(True))
            .all()
        )
        level_ids = {d.level_id for d in degrees if d.level_id is not None}

    programs = (
        db.query(Program)
        .filter(Program.is_active.is_(True))
        .order_by(Program.sort_order.asc(), Program.name.asc())
        .all()
    )
    matched_programs: list[dict[str, Any]] = []
    for program in programs:
        score = 0.0
        if preferred_focus and any(
            _token_soft_match(pref, program.code, program.name) for pref in preferred_focus
        ):
            score = 90.0
        elif level_ids and program.level_id in level_ids:
            # Prefer science-ish qualifications when CS-like majors matched
            name_n = _normalize_token(program.name)
            if matched_majors and any(
                token in name_n for token in ("SCIENCE", "ENGINEERING", "COMPUTER", "TECHNOLOGY")
            ):
                score = 75.0
            elif not matched_majors:
                score = 60.0
        if score > 0:
            matched_programs.append(
                {
                    "code": program.code,
                    "name": program.name,
                    "id": str(program.id),
                    "match_score": score,
                }
            )
    matched_programs.sort(key=lambda row: (-float(row["match_score"]), row.get("name") or ""))
    matched_programs = matched_programs[:limit]

    # Framework target programs (discipline umbrellas)
    for tp in (
        db.query(TargetProgram)
        .filter(TargetProgram.is_active.is_(True))
        .order_by(TargetProgram.sort_order.asc())
        .all()
    ):
        if preferred_focus and any(
            _token_soft_match(pref, tp.code, tp.label) for pref in preferred_focus
        ):
            matched_programs.append(
                {
                    "code": tp.code,
                    "name": tp.label,
                    "match_score": 70.0,
                }
            )

    matched_courses: list[dict[str, Any]] = []
    # Education framework courses under matched majors / soft label match
    edu_courses = (
        db.query(EducationCourse)
        .filter(EducationCourse.is_active.is_(True))
        .order_by(EducationCourse.sort_order.asc(), EducationCourse.id.asc())
        .all()
    )
    for course in edu_courses:
        score = 0.0
        if course.education_major_id and course.education_major_id in matched_major_ids:
            score = 88.0
        elif preferred_focus and any(
            _token_soft_match(pref, course.code, course.label) for pref in preferred_focus
        ):
            score = 80.0
        if score > 0:
            matched_courses.append(
                {
                    "code": course.code,
                    "name": course.label,
                    "course_label": course.label,
                    "course_code": course.code,
                    "course_level": course.course_level,
                    "match_score": score,
                    "source": "education_course",
                }
            )

    target_courses = (
        db.query(TargetCourse)
        .options(
            joinedload(TargetCourse.program),
            joinedload(TargetCourse.education_major),
            joinedload(TargetCourse.qualification_program),
        )
        .filter(TargetCourse.is_active.is_(True))
        .order_by(TargetCourse.sort_order.asc(), TargetCourse.id.asc())
        .all()
    )
    for course in target_courses:
        score = 0.0
        if course.education_major_id and course.education_major_id in matched_major_ids:
            score = 92.0
        elif preferred_focus and any(
            _token_soft_match(pref, course.code, course.label) for pref in preferred_focus
        ):
            score = 85.0
        if score <= 0:
            continue
        pathway = _academic_pathway_from_course(course, match_score=score)
        if not pathway:
            continue
        matched_courses.append(
            {
                "code": pathway.get("course_code"),
                "name": pathway.get("course_label"),
                "course_code": pathway.get("course_code"),
                "course_label": pathway.get("course_label"),
                "course_level": pathway.get("course_level"),
                "program_code": pathway.get("program_code"),
                "program_name": pathway.get("program_name"),
                "major_code": pathway.get("major_code"),
                "major_name": pathway.get("major_name"),
                "match_score": score,
                "source": "target_course",
            }
        )

    matched_courses.sort(key=lambda row: (-float(row.get("match_score") or 0), row.get("name") or ""))
    matched_courses = matched_courses[:limit]
    matched_majors = matched_majors[:limit]
    # Dedupe programs by code|name
    matched_programs = _unique_labeled(matched_programs, "code", "name")[:limit]

    pathways: list[dict[str, Any]] = []
    # Build readable pathways: program × major × course where possible
    top_programs = matched_programs[:3] or [{"code": None, "name": None}]
    top_majors = matched_majors[:3] or [{"code": None, "name": None}]
    if matched_courses:
        for course in matched_courses[:5]:
            program = next(
                (
                    p
                    for p in matched_programs
                    if p.get("code") and p.get("code") == course.get("program_code")
                ),
                top_programs[0],
            )
            major = next(
                (
                    m
                    for m in matched_majors
                    if m.get("code") and m.get("code") == course.get("major_code")
                ),
                top_majors[0],
            )
            pathways.append(
                {
                    "offering_id": None,
                    "program_code": course.get("program_code") or program.get("code"),
                    "program_name": course.get("program_name") or program.get("name"),
                    "major_code": course.get("major_code") or major.get("code"),
                    "major_name": course.get("major_name") or major.get("name"),
                    "course_code": course.get("course_code") or course.get("code"),
                    "course_label": course.get("course_label") or course.get("name"),
                    "course_level": course.get("course_level"),
                    "match_score": course.get("match_score"),
                    "match_reason": (
                        "Derived from aspirations vs academic catalog "
                        "(no institution course offerings published)."
                    ),
                }
            )
    else:
        for program in top_programs[:2]:
            for major in top_majors[:2]:
                if not program.get("name") and not major.get("name"):
                    continue
                pathways.append(
                    {
                        "offering_id": None,
                        "program_code": program.get("code"),
                        "program_name": program.get("name"),
                        "major_code": major.get("code"),
                        "major_name": major.get("name"),
                        "course_code": None,
                        "course_label": None,
                        "course_level": None,
                        "match_score": min(
                            float(program.get("match_score") or 60),
                            float(major.get("match_score") or 60),
                        ),
                        "match_reason": (
                            "Derived from aspirations vs academic catalog "
                            "(no institution course offerings published)."
                        ),
                    }
                )

    return {
        "source": "aspiration_catalog",
        "matched_programs": [{"code": r.get("code"), "name": r.get("name")} for r in matched_programs],
        "matched_majors": [{"code": r.get("code"), "name": r.get("name")} for r in matched_majors],
        "matched_courses": [
            {"code": r.get("code") or r.get("course_code"), "name": r.get("name") or r.get("course_label")}
            for r in matched_courses
        ],
        "pathways": pathways[:5],
    }


def _build_derived_academic(
    run: MatchingShortlistRun,
    serialized_items: list[dict[str, Any]],
    *,
    catalog_fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = run.input_snapshot if isinstance(run.input_snapshot, dict) else {}
    aspirations = snapshot.get("aspirations") if isinstance(snapshot.get("aspirations"), dict) else {}
    pathway_rows: list[dict[str, Any]] = []
    for item in serialized_items:
        pathways = item.get("matched_pathways") or []
        if pathways:
            pathway_rows.extend(pathways)
        else:
            pathway_rows.append(item)

    matched_programs = _unique_labeled(pathway_rows, "program_code", "program_name")
    matched_majors = _unique_labeled(pathway_rows, "major_code", "major_name")
    matched_courses = _unique_labeled(pathway_rows, "course_code", "course_label")

    snapshot_catalog = snapshot.get("derived_catalog") if isinstance(snapshot.get("derived_catalog"), dict) else None
    fallback = catalog_fallback or snapshot_catalog or {}
    source = "institution_offerings"
    if not matched_programs and fallback.get("matched_programs"):
        matched_programs = fallback.get("matched_programs") or []
        source = fallback.get("source") or "aspiration_catalog"
    if not matched_majors and fallback.get("matched_majors"):
        matched_majors = fallback.get("matched_majors") or []
        source = fallback.get("source") or "aspiration_catalog"
    if not matched_courses and fallback.get("matched_courses"):
        matched_courses = fallback.get("matched_courses") or []
        source = fallback.get("source") or "aspiration_catalog"

    return {
        "student_preferences": {
            "programs": aspirations.get("programs") or [],
            "programs_other": aspirations.get("programs_other"),
            "discipline_university_college": aspirations.get("discipline_university_college") or [],
            "discipline_pre_college": aspirations.get("discipline_pre_college") or [],
        },
        "matched_programs": matched_programs,
        "matched_majors": matched_majors,
        "matched_courses": matched_courses,
        "source": source,
    }


def _hydrate_items_with_catalog_pathways(
    serialized_items: list[dict[str, Any]],
    catalog: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    pathways = (catalog or {}).get("pathways") or []
    if not pathways:
        return serialized_items
    hydrated: list[dict[str, Any]] = []
    for item in serialized_items:
        current = list(item.get("matched_pathways") or [])
        if current:
            hydrated.append(item)
            continue
        primary = pathways[0]
        next_item = {
            **item,
            "program_code": item.get("program_code") or primary.get("program_code"),
            "program_name": item.get("program_name") or primary.get("program_name"),
            "major_code": item.get("major_code") or primary.get("major_code"),
            "major_name": item.get("major_name") or primary.get("major_name"),
            "course_code": item.get("course_code") or primary.get("course_code"),
            "course_label": item.get("course_label") or primary.get("course_label"),
            "course_level": item.get("course_level") or primary.get("course_level"),
            "matched_pathways": pathways,
        }
        hydrated.append(next_item)
    return hydrated


def _serialize_run(
    run: MatchingShortlistRun,
    *,
    db: Session | None = None,
) -> dict[str, Any]:
    items = [_serialize_item(item) for item in (run.items or [])]
    snapshot = run.input_snapshot if isinstance(run.input_snapshot, dict) else {}
    catalog = snapshot.get("derived_catalog") if isinstance(snapshot.get("derived_catalog"), dict) else None
    if (not catalog or not (catalog.get("matched_majors") or catalog.get("matched_programs"))) and db is not None:
        aspirations = snapshot.get("aspirations") if isinstance(snapshot.get("aspirations"), dict) else {}
        if aspirations:
            catalog = derive_catalog_matches_from_aspirations(db, aspirations)
    items = _hydrate_items_with_catalog_pathways(items, catalog)
    return {
        "id": run.id,
        "lead_id": run.lead_id,
        "booking_id": run.booking_id,
        "students_master_id": run.students_master_id,
        "algorithm_version": run.algorithm_version,
        "status": run.status,
        "classification_mode": run.classification_mode,
        "item_count": run.item_count,
        "weight_profile": run.weight_profile,
        "notes": run.notes,
        "disclaimer": DISCLAIMER,
        "created_at": run.created_at,
        "derived_academic": _build_derived_academic(run, items, catalog_fallback=catalog),
        "items": items,
    }


def get_latest_shortlist_for_booking(db: Session, booking_id: int) -> MatchingShortlistRun | None:
    return (
        db.query(MatchingShortlistRun)
        .options(
            joinedload(MatchingShortlistRun.weight_profile),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.institution)
            .joinedload(Institution.country),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.program),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.education_major),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.qualification_program),
        )
        .filter(MatchingShortlistRun.booking_id == booking_id)
        .order_by(MatchingShortlistRun.created_at.desc(), MatchingShortlistRun.id.desc())
        .first()
    )


def get_shortlist_run(db: Session, run_id: int, booking_id: int) -> MatchingShortlistRun | None:
    return (
        db.query(MatchingShortlistRun)
        .options(
            joinedload(MatchingShortlistRun.weight_profile),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.institution)
            .joinedload(Institution.country),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.program),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.education_major),
            joinedload(MatchingShortlistRun.items)
            .joinedload(MatchingShortlistItem.offering)
            .joinedload(InstitutionCourseOffering.course)
            .joinedload(TargetCourse.qualification_program),
        )
        .filter(
            MatchingShortlistRun.id == run_id,
            MatchingShortlistRun.booking_id == booking_id,
        )
        .first()
    )


def generate_university_shortlist(
    db: Session,
    booking: CounsellingBooking,
    lead: Lead | None,
    *,
    created_by_user_id: int | None,
    weight_profile_code: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    weights = _load_weight_profile(db, weight_profile_code)
    ctx = build_student_match_context(db, booking, lead)

    institutions = (
        db.query(Institution)
        .options(joinedload(Institution.country))
        .filter(Institution.is_active.is_(True))
        .all()
    )
    institution_ids = [inst.id for inst in institutions]

    offerings_by_inst: dict[int, list[InstitutionCourseOffering]] = {i: [] for i in institution_ids}
    if institution_ids:
        offerings = (
            db.query(InstitutionCourseOffering)
            .options(
                joinedload(InstitutionCourseOffering.course).joinedload(TargetCourse.program),
                joinedload(InstitutionCourseOffering.course).joinedload(TargetCourse.education_major),
                joinedload(InstitutionCourseOffering.course).joinedload(
                    TargetCourse.qualification_program
                ),
            )
            .filter(
                InstitutionCourseOffering.institution_id.in_(institution_ids),
                InstitutionCourseOffering.is_active.is_(True),
            )
            .all()
        )
        for offering in offerings:
            offerings_by_inst.setdefault(offering.institution_id, []).append(offering)

    intakes_by_inst: dict[int, list[InstitutionIntake]] = {i: [] for i in institution_ids}
    if institution_ids:
        intakes = (
            db.query(InstitutionIntake)
            .filter(
                InstitutionIntake.institution_id.in_(institution_ids),
                InstitutionIntake.is_active.is_(True),
            )
            .all()
        )
        for intake in intakes:
            intakes_by_inst.setdefault(intake.institution_id, []).append(intake)

    scored: list[ScoredCandidate] = []
    for institution in institutions:
        country_iso2 = institution.country.iso2 if institution.country else None
        candidate = score_institution(
            ctx,
            institution,
            country_iso2,
            offerings_by_inst.get(institution.id, []),
            intakes_by_inst.get(institution.id, []),
            weights,
        )
        if candidate:
            scored.append(candidate)

    scored.sort(key=lambda c: (-c.consolidated, c.institution.name or ""))
    scored = scored[: max(1, min(limit, 100))]

    catalog_matches = derive_catalog_matches_from_aspirations(db, ctx.aspirations)
    total_offerings = sum(len(v) for v in offerings_by_inst.values())
    if total_offerings == 0 and catalog_matches.get("pathways"):
        for candidate in scored:
            if candidate.matched_pathways:
                continue
            pathways = catalog_matches.get("pathways") or []
            candidate.matched_pathways = pathways
            candidate.primary_pathway = pathways[0] if pathways else None
            if isinstance(candidate.explanation, dict):
                candidate.explanation = {
                    **candidate.explanation,
                    "primary_pathway": candidate.primary_pathway,
                    "matched_pathways": pathways,
                    "catalog_source": "aspiration_catalog",
                }

    status = "completed"
    notes = None
    if ctx.completeness < 0.34:
        status = "insufficient_data"
        notes = (
            "Student profile is thin; scores may be unreliable. "
            "Complete aspirations, education, and tests for better shortlists."
        )
    elif not scored:
        status = "insufficient_data"
        notes = (
            "No institutions matched current filters "
            "(check target countries and active catalog data)."
        )
    elif total_offerings == 0:
        notes = (
            "No institution course offerings are published yet. "
            "Programs, majors, and courses below are derived from aspirations "
            "against the academic catalog."
        )

    run = MatchingShortlistRun(
        lead_id=lead.id if lead else None,
        booking_id=booking.id,
        students_master_id=ctx.students_master_id,
        weight_profile_id=weights.id,
        algorithm_version=ALGORITHM_VERSION,
        status=status,
        classification_mode=CLASSIFICATION_MODE,
        item_count=len(scored),
        created_by_user_id=created_by_user_id,
        input_snapshot={
            "aspirations": ctx.aspirations.model_dump(),
            "gpa_band_code": ctx.gpa_band_code,
            "test_names": sorted(ctx.test_names),
            "work_years": ctx.work_years,
            "research_count": ctx.research_count,
            "digital_presence_count": ctx.digital_presence_count,
            "data_completeness": ctx.completeness,
            "weight_profile_code": weights.code,
            "limit": limit,
            "derived_catalog": catalog_matches,
            "institution_offerings_count": total_offerings,
        },
        notes=notes,
    )
    db.add(run)
    db.flush()

    for rank, candidate in enumerate(scored, start=1):
        db.add(
            MatchingShortlistItem(
                run_id=run.id,
                institution_id=candidate.institution.id,
                offering_id=candidate.offering.id if candidate.offering else None,
                rank=rank,
                consolidated_score=_round2(candidate.consolidated),
                s_academic=_round2(candidate.s_academic),
                s_profile=_round2(candidate.s_profile),
                s_aspirations=_round2(candidate.s_aspirations),
                s_safety=_round2(candidate.s_safety),
                fit_band=candidate.fit_band,
                explanation=candidate.explanation,
            )
        )

    db.commit()

    loaded = get_shortlist_run(db, run.id, booking.id)
    assert loaded is not None
    return {
        "booking_id": booking.id,
        "run": _serialize_run(loaded, db=db),
    }


def get_university_shortlist_for_booking(
    db: Session,
    user: User,
    booking_id: int,
    *,
    run_id: int | None = None,
) -> dict[str, Any]:
    from app.services.counselling_service import _get_viewable_booking

    booking = _get_viewable_booking(db, user, booking_id)
    if run_id is not None:
        run = get_shortlist_run(db, run_id, booking.id)
        if not run:
            raise HTTPException(status_code=404, detail="Shortlist run not found.")
    else:
        run = get_latest_shortlist_for_booking(db, booking.id)
    return {
        "booking_id": booking.id,
        "run": _serialize_run(run, db=db) if run else None,
    }


def generate_university_shortlist_for_booking(
    db: Session,
    user_id: int,
    booking_id: int,
    *,
    weight_profile_code: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    from app.services.counselling_service import _get_viewable_booking

    user = db.query(User).options(joinedload(User.admin_role_ref)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    booking = _get_viewable_booking(db, user, booking_id)
    lead = db.query(Lead).filter(Lead.id == booking.lead_id).first() if booking.lead_id else None
    return generate_university_shortlist(
        db,
        booking,
        lead,
        created_by_user_id=user_id,
        weight_profile_code=weight_profile_code,
        limit=limit,
    )


def list_weight_profiles(db: Session) -> list[MatchingWeightProfile]:
    return (
        db.query(MatchingWeightProfile)
        .filter(MatchingWeightProfile.is_active.is_(True))
        .order_by(MatchingWeightProfile.is_default.desc(), MatchingWeightProfile.id.asc())
        .all()
    )
