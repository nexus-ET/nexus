from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.candidate_test_score import CandidateTestScore
from app.models.lead import Lead
from app.schemas.candidate_test_scores import (
    OVERALL_SCORE_CONFIG,
    TEST_SECTION_CONFIG,
    CandidateTestScoreSaveRequest,
    CandidateTestScoresResponse,
    TestName,
    TestSectionConfig,
)
from app.services.candidate_test_scores_sequence import (
    sync_candidate_test_scores_id_sequence,
)
from app.utils.timezone import utc_now_naive


def _get_section_config(test_name: TestName, section_name: str) -> TestSectionConfig | None:
    sections = TEST_SECTION_CONFIG.get(test_name, [])
    normalized = section_name.strip().lower()
    for section in sections:
        if section.section_name.lower() == normalized:
            return section
    return None


def _validate_section_score(
    test_name: TestName,
    section_name: str,
    score: Decimal,
) -> Decimal:
    config = _get_section_config(test_name, section_name)
    if config is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid section '{section_name}' for test {test_name.value}.",
        )

    score_text = format(score, "f").rstrip("0").rstrip(".")
    if len(score_text) > config.max_length:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{section_name} score must be at most {config.max_length} characters "
                f"for {test_name.value}."
            ),
        )

    numeric_score = float(score)
    if numeric_score < config.min_score or numeric_score > config.max_score:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{section_name} score must be between {config.min_score:g} and "
                f"{config.max_score:g} for {test_name.value}."
            ),
        )

    if config.data_type == "integer":
        return Decimal(score).to_integral_value(rounding=ROUND_HALF_UP)

    if config.data_type == "float":
        return Decimal(str(round(numeric_score, 1)))
    return score.to_integral_value()


def _validate_overall_score(
    test_name: TestName,
    score: Decimal | None,
) -> Decimal | None:
    if score is None:
        return None

    config = OVERALL_SCORE_CONFIG.get(test_name)
    if config is None:
        return score

    numeric_score = float(score)
    if numeric_score < config.min_score or numeric_score > config.max_score:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Overall score must be between {config.min_score:g} and "
                f"{config.max_score:g} for {test_name.value}."
            ),
        )

    if config.data_type == "integer":
        normalized = Decimal(score).to_integral_value(rounding=ROUND_HALF_UP)
    elif config.data_type == "float":
        normalized = Decimal(str(round(numeric_score, 1)))
    else:
        normalized = score.to_integral_value()

    score_text = format(normalized, "f").rstrip("0").rstrip(".")
    if len(score_text) > config.max_length:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Overall score must be at most {config.max_length} characters "
                f"for {test_name.value}."
            ),
        )

    return normalized


def _resolve_overall_score(
    test_name: TestName,
    payload: CandidateTestScoreSaveRequest,
) -> Decimal | None:
    if payload.overall_score is not None:
        return _validate_overall_score(test_name, payload.overall_score)

    if test_name in {TestName.DUOLINGO, TestName.LSAT_MCAT}:
        for section in payload.sections:
            if section.section_name.strip().lower() == "overall":
                return _validate_overall_score(test_name, section.score)
    return None


def _serialize_score(record: CandidateTestScore) -> dict:
    return {
        "id": record.id,
        "lead_id": record.lead_id,
        "booking_id": record.booking_id,
        "test_name": record.test_name,
        "test_date": record.test_date,
        "overall_score": record.overall_score,
        "section_name": record.section_name,
        "score": record.score,
        "score_report_url": record.score_report_url,
        "created_at": record.created_at,
    }


def get_candidate_test_scores(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
) -> CandidateTestScoresResponse:
    lead_id = lead.id if lead else None
    if lead_id is not None:
        query = db.query(CandidateTestScore).filter(CandidateTestScore.lead_id == lead_id)
    else:
        query = db.query(CandidateTestScore).filter(CandidateTestScore.booking_id == booking_id)

    records = query.order_by(
        CandidateTestScore.test_date.desc().nullslast(),
        CandidateTestScore.created_at.desc(),
        CandidateTestScore.id.desc(),
    ).all()

    return CandidateTestScoresResponse(
        booking_id=booking_id,
        lead_id=lead_id,
        scores=[_serialize_score(record) for record in records],
    )


def save_candidate_test_scores(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: CandidateTestScoreSaveRequest,
) -> CandidateTestScoresResponse:
    _insert_candidate_test_score_rows(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    )
    db.commit()
    return get_candidate_test_scores(db, booking_id=booking_id, lead=lead)


def _insert_candidate_test_score_rows(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    payload: CandidateTestScoreSaveRequest,
) -> list[CandidateTestScore]:
    expected_sections = {
        section.section_name.lower(): section
        for section in TEST_SECTION_CONFIG[payload.test_name]
    }
    provided_sections = {item.section_name.strip().lower(): item for item in payload.sections}

    if set(provided_sections) != set(expected_sections):
        missing = sorted(expected_sections.keys() - set(provided_sections))
        extra = sorted(set(provided_sections) - set(expected_sections))
        details: list[str] = []
        if missing:
            details.append(f"missing sections: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected sections: {', '.join(extra)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sections for {payload.test_name.value} ({'; '.join(details)}).",
        )

    lead_id = lead.id if lead else None
    created_records: list[CandidateTestScore] = []
    # Column is naive DateTime; keep writes naive UTC to avoid adapter/DB errors.
    batch_created_at = utc_now_naive()
    validated_overall = _resolve_overall_score(payload.test_name, payload)
    # Imported/seeded rows can leave the serial sequence behind MAX(id).
    sync_candidate_test_scores_id_sequence(db)

    for section_key, section_input in provided_sections.items():
        canonical_name = expected_sections[section_key].section_name
        validated_score = _validate_section_score(
            payload.test_name,
            canonical_name,
            section_input.score,
        )
        record = CandidateTestScore(
            lead_id=lead_id,
            booking_id=booking_id,
            test_name=payload.test_name.value,
            test_date=payload.test_date,
            overall_score=validated_overall,
            section_name=canonical_name,
            score=validated_score,
            score_report_url=payload.score_report_url,
            created_at=batch_created_at,
        )
        db.add(record)
        created_records.append(record)

    db.flush()
    for record in created_records:
        db.refresh(record)
    return created_records


def delete_candidate_test_score_attempt(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    score_ids: list[int],
    commit: bool = True,
) -> CandidateTestScoresResponse:
    """Delete all section rows belonging to one grouped test attempt."""
    if not score_ids:
        raise HTTPException(status_code=400, detail="No score ids provided.")

    lead_id = lead.id if lead else None
    query = db.query(CandidateTestScore).filter(CandidateTestScore.id.in_(score_ids))
    if lead_id is not None:
        query = query.filter(CandidateTestScore.lead_id == lead_id)
    else:
        query = query.filter(CandidateTestScore.booking_id == booking_id)

    records = query.all()
    if not records:
        raise HTTPException(status_code=404, detail="Test score attempt not found.")

    for record in records:
        db.delete(record)

    if commit:
        db.commit()
    else:
        db.flush()

    return get_candidate_test_scores(db, booking_id=booking_id, lead=lead)


def replace_candidate_test_score_attempt(
    db: Session,
    *,
    booking_id: int,
    lead: Lead | None,
    score_ids: list[int],
    payload: CandidateTestScoreSaveRequest,
) -> CandidateTestScoresResponse:
    """Atomically replace one attempt: delete old section rows, then insert the new set."""
    delete_candidate_test_score_attempt(
        db,
        booking_id=booking_id,
        lead=lead,
        score_ids=score_ids,
        commit=False,
    )
    _insert_candidate_test_score_rows(
        db,
        booking_id=booking_id,
        lead=lead,
        payload=payload,
    )
    db.commit()
    return get_candidate_test_scores(db, booking_id=booking_id, lead=lead)
