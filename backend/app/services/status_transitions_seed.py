from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.status_transition import StatusTransition, TransitionType
from app.services.status_definition_service import (
    STATUS_ADMISSION_DOC_PREP,
    STATUS_COUNSELLING_FINISHED,
    STATUS_COUNSELLING_SCHEDULED,
    STATUS_LEAD_ENGAGEMENT,
    STATUS_LEAD_NEW,
    STATUS_PROSPECT_CANCELLED,
    STATUS_PROSPECT_RELAUNCH,
    STATUS_VISA_DOC_PREP,
)

logger = logging.getLogger(__name__)

EXPRESS_TRANSITIONS: list[tuple[int, int]] = [
    (STATUS_LEAD_NEW, STATUS_COUNSELLING_SCHEDULED),
    (STATUS_LEAD_ENGAGEMENT, STATUS_ADMISSION_DOC_PREP),
    (STATUS_COUNSELLING_FINISHED, STATUS_VISA_DOC_PREP),
]

RELAUNCH_TRANSITIONS: list[tuple[int, int]] = [
    (STATUS_PROSPECT_CANCELLED, STATUS_PROSPECT_RELAUNCH),
]


def seed_status_transitions_if_empty(db: Session) -> bool:
    """Bootstrap transition graph when Alembic seed did not run."""
    if db.query(StatusTransition.id).limit(1).first() is not None:
        return False
    logger.warning("status_transitions is empty — seeding forward, express, backward, and relaunch paths.")
    _insert_all_transitions(db)
    db.commit()
    return True


def _insert_all_transitions(db: Session) -> None:
    db.execute(
        text(
            """
            INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
            SELECT id, next_stage_id, 'forward'
            FROM status_definitions
            WHERE next_stage_id IS NOT NULL
            ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
            """
        )
    )

    for from_id, to_id in EXPRESS_TRANSITIONS:
        db.execute(
            text(
                """
                INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
                VALUES (:from_id, :to_id, 'express')
                ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
                """
            ),
            {"from_id": from_id, "to_id": to_id},
        )

    for from_id, to_id in RELAUNCH_TRANSITIONS:
        db.execute(
            text(
                """
                INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
                VALUES (:from_id, :to_id, 'relaunch')
                ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
                """
            ),
            {"from_id": from_id, "to_id": to_id},
        )

    db.execute(
        text(
            """
            INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
            SELECT to_status_id, from_status_id, 'backward'
            FROM status_transitions
            WHERE transition_type = 'forward'
            ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING
            """
        )
    )


def ensure_status_transitions_seeded(db: Session) -> None:
    seed_status_transitions_if_empty(db)
