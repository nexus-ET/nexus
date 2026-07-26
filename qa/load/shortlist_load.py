#!/usr/bin/env python3
"""
Phase 5 — Lightweight concurrent shortlist scoring load check.

Runs in-process (no Locust dependency). Exercises the weighted scoring helper
under concurrent workers to catch lockups / NaN / exceptions.

Usage:
  cd backend
  .venv\\Scripts\\python.exe ..\\qa\\load\\shortlist_load.py
"""

from __future__ import annotations

import concurrent.futures
import math
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.schemas.student_aspirations import StudentAspirationsData  # noqa: E402
from app.services.university_matching_service import (  # noqa: E402
    StudentMatchContext,
    score_institution,
)


def _one_score(i: int) -> float:
    ctx = StudentMatchContext(
        aspirations=StudentAspirationsData(
            study_countries_iso2=["US", "GB"][i % 2 : (i % 2) + 1] or ["US"],
            programs=["Computer Science"],
        ),
        gpa_band_score=70 + (i % 30),
        work_years=float(i % 8),
        research_count=i % 3,
        digital_presence_count=i % 4,
    )
    institution = SimpleNamespace(
        id=i,
        name=f"Load Uni {i}",
        ranking_tier_global=["TOP_100_GLOBAL_ELITE", "TOP_300_RESEARCH_INTENSIVE", None][i % 3],
        institution_type="University",
    )
    weights = SimpleNamespace(
        weight_academic=0.4,
        weight_profile=0.2,
        weight_aspirations=0.2,
        weight_safety=0.2,
    )
    country = ["US", "GB", "CA"][i % 3]
    candidate = score_institution(ctx, institution, country, [], [], weights)
    if candidate is None:
        return -1.0
    score = float(candidate.consolidated)
    if not math.isfinite(score):
        raise ValueError(f"Non-finite score for i={i}: {score}")
    if score < 0 or score > 100:
        raise ValueError(f"Out-of-range score for i={i}: {score}")
    return score


def main() -> int:
    workers = 16
    iterations = 200
    started = time.perf_counter()
    scores: list[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one_score, i) for i in range(iterations)]
        for fut in concurrent.futures.as_completed(futures):
            scores.append(fut.result())
    elapsed = time.perf_counter() - started
    valid = [s for s in scores if s >= 0]
    print(f"shortlist_load: workers={workers} iterations={iterations}")
    print(f"  elapsed_s={elapsed:.3f} throughput={iterations / elapsed:.1f}/s")
    print(f"  scored={len(valid)} skipped_country_filter={iterations - len(valid)}")
    if valid:
        print(
            f"  score_min={min(valid):.2f} score_max={max(valid):.2f} "
            f"score_mean={statistics.fmean(valid):.2f}"
        )
    # Gate: finish under 30s locally and produce mostly finite scores
    if elapsed > 30:
        print("FAIL: load run exceeded 30s")
        return 1
    if len(valid) < iterations * 0.3:
        print("FAIL: too few scored institutions (country filter too aggressive?)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
