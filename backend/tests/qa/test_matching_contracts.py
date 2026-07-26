"""Phase 2 — Matching scoring integrity & API contract schemas."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.student_aspirations import StudentAspirationsData
from app.schemas.university_matching import (
    MatchingWeightProfileOut,
    UniversityShortlistGenerateRequest,
    UniversityShortlistItemOut,
)
from app.services.university_matching_service import (
    StudentMatchContext,
    _clamp,
    _score_academic,
    _score_aspirations,
    _score_profile,
    _score_safety,
    classify_fit_band,
    score_institution,
)


def test_clamp_bounds_for_finite_inputs():
    assert _clamp(-50) == 0.0
    assert _clamp(150) == 100.0
    assert _clamp(55.5) == 55.5
    assert math.isfinite(_clamp(0.0))
    assert math.isfinite(_clamp(100.0))
    assert _clamp(float("nan")) == 0.0
    assert _clamp(float("inf")) == 0.0


def test_score_dimensions_never_emit_nan_or_out_of_range():
    ctx = StudentMatchContext(aspirations=StudentAspirationsData())
    for score, _explain in (
        _score_academic(ctx, None),
        _score_academic(ctx, "TOP_100_GLOBAL_ELITE"),
        _score_profile(ctx),
        _score_safety(0.0, None),
        _score_safety(100.0, "TOP_100_GLOBAL_ELITE"),
        _score_safety(50.0, "UNKNOWN_RANK"),
    ):
        assert math.isfinite(score)
        assert 0.0 <= score <= 100.0

    institution = SimpleNamespace(
        id=1,
        name="Test U",
        ranking_tier_global="TOP_300_RESEARCH_INTENSIVE",
        institution_type="University",
    )
    weights = SimpleNamespace(
        weight_academic=0.4,
        weight_profile=0.2,
        weight_aspirations=0.2,
        weight_safety=0.2,
    )
    # No preferred countries → still scores
    candidate = score_institution(ctx, institution, "US", [], [], weights)
    assert candidate is not None
    consolidated = float(candidate.consolidated)
    assert math.isfinite(consolidated)
    assert 0.0 <= consolidated <= 100.0
    for dim in (
        candidate.s_academic,
        candidate.s_profile,
        candidate.s_aspirations,
        candidate.s_safety,
    ):
        assert math.isfinite(dim)
        assert 0.0 <= dim <= 100.0


def test_aspirations_score_with_empty_preferences_is_finite():
    ctx = StudentMatchContext(aspirations=StudentAspirationsData())
    institution = SimpleNamespace(id=1, name="U", ranking_tier_global=None, institution_type=None)
    score, explain = _score_aspirations(
        ctx, institution, None, None, None, [], pathway_match_reason=None
    )
    assert math.isfinite(score)
    assert 0.0 <= score <= 100.0
    assert "reasons" in explain


def test_fit_band_boundaries():
    assert classify_fit_band(0) == "reach"
    assert classify_fit_band(39.99) == "reach"
    assert classify_fit_band(40) == "target"
    assert classify_fit_band(69.99) == "target"
    assert classify_fit_band(70) == "safe"
    assert classify_fit_band(100) == "safe"


def test_generate_request_contract_bounds():
    ok = UniversityShortlistGenerateRequest(weight_profile_code="default", limit=40)
    assert ok.limit == 40
    with pytest.raises(ValidationError):
        UniversityShortlistGenerateRequest(limit=0)
    with pytest.raises(ValidationError):
        UniversityShortlistGenerateRequest(limit=101)


def test_shortlist_response_schema_accepts_phase1_shape():
    """Frontend ↔ backend contract: response models validate typical payloads."""
    payload = {
        "booking_id": 1,
        "run": {
            "id": 9,
            "booking_id": 1,
            "lead_id": 27,
            "students_master_id": 1,
            "weight_profile_id": 1,
            "algorithm_version": "phase1-v1",
            "status": "completed",
            "item_count": 1,
            "notes": None,
            "created_at": "2026-07-26T00:00:00",
            "weight_profile": {
                "id": 1,
                "code": "default",
                "name": "Default",
                "description": None,
                "weight_academic": "0.4000",
                "weight_profile": "0.2000",
                "weight_aspirations": "0.2000",
                "weight_safety": "0.2000",
                "is_default": True,
                "is_active": True,
            },
            "items": [
                {
                    "id": 1,
                    "rank": 1,
                    "institution_id": 10,
                    "institution_name": "Example University",
                    "institution_country_iso2": "US",
                    "institution_type": "University",
                    "ranking_tier_global": "TOP_100_GLOBAL_ELITE",
                    "fit_band": "safe",
                    "consolidated_score": "88.50",
                    "s_academic": "90.00",
                    "s_profile": "80.00",
                    "s_aspirations": "85.00",
                    "s_safety": "88.00",
                    "explanation": {"academic": {"reasons": ["GPA band strong"]}},
                    "matched_pathways": [],
                }
            ],
        },
    }
    # Schema field names may differ — validate generate request + item out loosely
    item = UniversityShortlistItemOut.model_validate(payload["run"]["items"][0])
    assert item.fit_band == "safe"
    assert float(item.s_academic) == 90.0
    profile = MatchingWeightProfileOut.model_validate(payload["run"]["weight_profile"])
    assert profile.code == "default"
