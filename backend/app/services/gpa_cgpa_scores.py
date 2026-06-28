from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.gpa_cgpa_score import GpaCgpaScore
from app.schemas.offline_lead import OfflineLeadEducation

DEFAULT_GPA_CGPA_SCORES: list[dict[str, str | int | bool]] = [
    {"code": "GPA_375_400", "label": "GPA 3.75 - 4.00", "sort_order": 1},
    {"code": "GPA_350_374", "label": "GPA 3.50 - 3.74", "sort_order": 2},
    {"code": "GPA_300_349", "label": "GPA 3.00 - 3.49", "sort_order": 3},
    {"code": "GPA_250_299", "label": "GPA 2.50 - 2.99", "sort_order": 4},
    {"code": "GPA_200_249", "label": "GPA 2.00 - 2.49", "sort_order": 5},
    {"code": "GPA_BELOW_200", "label": "GPA Below 2.00", "sort_order": 6},
    {"code": "CGPA_900_1000", "label": "CGPA 9.00 - 10.00", "sort_order": 7},
    {"code": "CGPA_800_899", "label": "CGPA 8.00 - 8.99", "sort_order": 8},
    {"code": "CGPA_700_799", "label": "CGPA 7.00 - 7.99", "sort_order": 9},
    {"code": "CGPA_600_699", "label": "CGPA 6.00 - 6.99", "sort_order": 10},
    {"code": "CGPA_500_599", "label": "CGPA 5.00 - 5.99", "sort_order": 11},
    {"code": "CGPA_BELOW_500", "label": "CGPA Below 5.00", "sort_order": 12},
    {"code": "PCT_90_100", "label": "90% - 100%", "sort_order": 13},
    {"code": "PCT_80_89", "label": "80% - 89%", "sort_order": 14},
    {"code": "PCT_70_79", "label": "70% - 79%", "sort_order": 15},
    {"code": "PCT_60_69", "label": "60% - 69%", "sort_order": 16},
    {"code": "PCT_50_59", "label": "50% - 59%", "sort_order": 17},
    {"code": "PCT_BELOW_50", "label": "Below 50%", "sort_order": 18},
    {"code": "OTHER", "label": "Other", "sort_order": 99, "is_other": True},
]


def seed_gpa_cgpa_scores(db: Session) -> None:
    for item in DEFAULT_GPA_CGPA_SCORES:
        existing = db.query(GpaCgpaScore).filter(GpaCgpaScore.code == item["code"]).first()
        if existing:
            existing.label = str(item["label"])
            existing.sort_order = int(item["sort_order"])
            existing.is_other = bool(item.get("is_other", False))
            existing.is_active = True
            continue
        db.add(
            GpaCgpaScore(
                code=str(item["code"]),
                label=str(item["label"]),
                sort_order=int(item["sort_order"]),
                is_other=bool(item.get("is_other", False)),
                is_active=True,
            )
        )
    db.commit()


def list_active_gpa_cgpa_scores(db: Session) -> list[GpaCgpaScore]:
    return (
        db.query(GpaCgpaScore)
        .filter(GpaCgpaScore.is_active.is_(True))
        .order_by(GpaCgpaScore.sort_order.asc(), GpaCgpaScore.label.asc())
        .all()
    )


def get_gpa_cgpa_score_by_code(db: Session, code: str) -> GpaCgpaScore | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return (
        db.query(GpaCgpaScore)
        .filter(GpaCgpaScore.code == normalized, GpaCgpaScore.is_active.is_(True))
        .first()
    )


def apply_gpa_cgpa_fields(
    db: Session, education: OfflineLeadEducation, payload: dict[str, str | int]
) -> dict[str, str | int]:
    score_code = (education.gpa_cgpa_code or "").strip().upper() or None
    custom_score = (education.gpa_cgpa or "").strip() or None

    if score_code:
        record = get_gpa_cgpa_score_by_code(db, score_code)
        if not record:
            raise HTTPException(status_code=400, detail="Select a valid GPA/CGPA score.")
        if record.is_other:
            if not custom_score:
                raise HTTPException(
                    status_code=400,
                    detail="Please enter the GPA/CGPA score when Other is selected.",
                )
            payload["gpa_cgpa"] = custom_score
        else:
            payload["gpa_cgpa"] = record.label
        payload["gpa_cgpa_code"] = record.code
    elif custom_score:
        matched = next(
            (
                item
                for item in list_active_gpa_cgpa_scores(db)
                if item.label.lower() == custom_score.lower() and not item.is_other
            ),
            None,
        )
        payload["gpa_cgpa"] = custom_score
        if matched:
            payload["gpa_cgpa_code"] = matched.code

    return payload
