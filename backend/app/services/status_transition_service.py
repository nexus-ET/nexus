from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.status_definition import StatusDefinition
from app.services.status_definition_service import (
    STATUS_COUNSELLING_SCHEDULED,
    STATUS_LEAD_ENGAGEMENT,
    STATUS_LEAD_NEW,
    STATUS_LEAD_OUTREACH,
    STATUS_LEAD_SESSION_BOOKED,
    STATUS_LEAD_SESSION_CANCELLED,
    STATUS_LEAD_SESSION_RESCHEDULED,
    STATUS_PROSPECT_RELAUNCH,
    TERMINAL_STATUS_IDS,
    get_status_definition,
)

REPEATABLE_EVENT_STATUS_IDS = frozenset(
    {STATUS_LEAD_SESSION_RESCHEDULED, STATUS_LEAD_SESSION_CANCELLED}
)

# Automation shortcuts that mirror real-world event handlers.
AUTOMATION_ALLOWED_TRANSITIONS: dict[int | None, frozenset[int]] = {
    None: frozenset({STATUS_LEAD_NEW}),
    1: frozenset({STATUS_LEAD_OUTREACH}),
    2: frozenset({STATUS_LEAD_ENGAGEMENT}),
    3: frozenset({STATUS_LEAD_SESSION_BOOKED}),
    4: frozenset({STATUS_LEAD_SESSION_RESCHEDULED, STATUS_LEAD_SESSION_CANCELLED}),
    5: frozenset(
        {
            STATUS_LEAD_SESSION_BOOKED,
            STATUS_LEAD_SESSION_RESCHEDULED,
            STATUS_LEAD_SESSION_CANCELLED,
            STATUS_COUNSELLING_SCHEDULED,
        }
    ),
    6: frozenset(
        {
            STATUS_LEAD_SESSION_BOOKED,
            STATUS_LEAD_SESSION_RESCHEDULED,
            STATUS_LEAD_SESSION_CANCELLED,
        }
    ),
    10: frozenset({STATUS_LEAD_SESSION_RESCHEDULED, STATUS_LEAD_SESSION_CANCELLED}),
}


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    reason: str
    requires_override_comment: bool = False
    is_override: bool = False


def _definition_exists(db: Session, status_id: int) -> bool:
    return (
        db.query(StatusDefinition.id).filter(StatusDefinition.id == status_id).first() is not None
    )


def can_transition_to(
    db: Session,
    current_status_id: int | None,
    next_status_id: int,
    *,
    allow_override: bool = False,
    force_repeat: bool = False,
) -> TransitionResult:
    """
    Central workflow authority for pipeline status changes.

    Standard flow: next status must equal current.next_stage_id (forward motion).
    Admin override: any target is allowed when allow_override=True, but callers
    must require a status_history comment explaining the exception.
    """
    if not _definition_exists(db, next_status_id):
        return TransitionResult(
            allowed=False,
            reason=f"Status definition {next_status_id} does not exist.",
        )

    if current_status_id == next_status_id:
        if force_repeat and next_status_id in REPEATABLE_EVENT_STATUS_IDS:
            return TransitionResult(
                allowed=True,
                reason="Repeatable event status logged again.",
            )
        return TransitionResult(allowed=True, reason="Status is already set.")

    if current_status_id is None:
        if next_status_id == STATUS_LEAD_NEW:
            return TransitionResult(allowed=True, reason="Initial lead status.")
        if allow_override:
            return TransitionResult(
                allowed=True,
                reason="Admin override from unset status.",
                requires_override_comment=True,
                is_override=True,
            )
        return TransitionResult(
            allowed=False,
            reason="Only Lead: New may be assigned when no pipeline status exists.",
        )

    current = get_status_definition(db, current_status_id)

    if current_status_id in TERMINAL_STATUS_IDS:
        if next_status_id == STATUS_PROSPECT_RELAUNCH:
            if allow_override:
                return TransitionResult(
                    allowed=True,
                    reason="Admin relaunch from terminal status.",
                )
            return TransitionResult(
                allowed=False,
                reason="Relaunch from a terminal status requires an admin action.",
            )
        if allow_override:
            return TransitionResult(
                allowed=True,
                reason="Admin override from terminal status.",
                requires_override_comment=True,
                is_override=True,
            )
        return TransitionResult(
            allowed=False,
            reason=(
                f"Terminal status '{current.stage_name}' is locked for automated updates."
            ),
        )

    if current.next_stage_id == next_status_id:
        return TransitionResult(
            allowed=True,
            reason=f"Forward transition via next_stage_id ({current.next_stage_id}).",
        )

    automation_targets = AUTOMATION_ALLOWED_TRANSITIONS.get(current_status_id, frozenset())
    if next_status_id in automation_targets:
        return TransitionResult(
            allowed=True,
            reason="Allowed automation funnel transition.",
        )

    if allow_override:
        return TransitionResult(
            allowed=True,
            reason=(
                f"Admin override: '{current.stage_name}' → "
                f"status {next_status_id} is outside the standard next step."
            ),
            requires_override_comment=True,
            is_override=True,
        )

    next_def = get_status_definition(db, next_status_id)
    expected = current.next_stage_id
    return TransitionResult(
        allowed=False,
        reason=(
            f"Illegal transition from '{current.stage_name}' to '{next_def.stage_name}'. "
            f"Expected next stage id: {expected}."
        ),
    )


def is_terminal_status(status_id: int | None) -> bool:
    return status_id is not None and status_id in TERMINAL_STATUS_IDS
