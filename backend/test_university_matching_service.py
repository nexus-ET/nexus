"""Unit tests for Phase 1 university matching heuristics."""

from __future__ import annotations

from types import SimpleNamespace

from app.schemas.student_aspirations import StudentAspirationsData
from app.services.university_matching_service import (
    StudentMatchContext,
    _academic_pathway_from_course,
    _offering_program_match,
    classify_fit_band,
    _normalize_ranking_code,
    _score_academic,
    _score_profile,
    _score_safety,
)


def test_normalize_ranking_label_and_code():
    assert _normalize_ranking_code("TOP_100_GLOBAL_ELITE") == "TOP_100_GLOBAL_ELITE"
    assert _normalize_ranking_code("Top 100 (Global Elite)") == "TOP_100_GLOBAL_ELITE"
    assert _normalize_ranking_code(None) is None


def test_classify_fit_band_thresholds():
    assert classify_fit_band(80) == "safe"
    assert classify_fit_band(55) == "target"
    assert classify_fit_band(20) == "reach"


def test_score_academic_uses_gpa_band():
    ctx = StudentMatchContext(
        aspirations=StudentAspirationsData(english_tests=["IELTS"]),
        gpa_band_code="GPA_375_400",
        gpa_band_score=95,
        test_names={"IELTS"},
    )
    score, explain = _score_academic(ctx, "TOP_300_RESEARCH_INTENSIVE")
    assert score >= 95
    assert explain["gpa_band_code"] == "GPA_375_400"


def test_score_profile_caps_components():
    ctx = StudentMatchContext(
        aspirations=StudentAspirationsData(),
        work_years=10,
        research_count=5,
        digital_presence_count=5,
    )
    score, explain = _score_profile(ctx)
    assert score == 100
    assert explain["work_years"] == 10


def test_score_safety_is_heuristic_not_probability():
    score, explain = _score_safety(90, "TOP_100_GLOBAL_ELITE")
    assert 0 <= score <= 100
    assert explain["mode"] == "heuristic_fit"


def test_academic_pathway_prefers_qualification_and_education_major():
    course = SimpleNamespace(
        id=11,
        code="CS101",
        label="BSc Computer Science",
        level="Undergraduate",
        qualification_program=SimpleNamespace(code="BSC", name="Bachelor of Science"),
        education_major=SimpleNamespace(code="CS", label="Computer Science"),
        program=SimpleNamespace(code="ENG", label="Engineering & Technology"),
    )
    pathway = _academic_pathway_from_course(course, offering_id=99, match_score=88)
    assert pathway is not None
    assert pathway["program_name"] == "Bachelor of Science"
    assert pathway["major_name"] == "Computer Science"
    assert pathway["course_code"] == "CS101"
    assert pathway["offering_id"] == 99


def test_offering_match_soft_matches_aspiration_major_label():
    course = SimpleNamespace(
        id=11,
        code="DS200",
        label="MSc Data Science",
        level="Postgraduate",
        qualification_program=SimpleNamespace(code="MSC", name="Master of Science"),
        education_major=SimpleNamespace(code="DATA", label="Data Science"),
        program=SimpleNamespace(code="COMP", label="Computing"),
    )
    aspirations = StudentAspirationsData(programs=["Data Science"])
    score, reason = _offering_program_match(course, aspirations)
    assert score >= 80
    assert "soft-matches" in reason or "matches preference" in reason.lower()
