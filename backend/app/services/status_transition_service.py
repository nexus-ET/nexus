from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.status_definition import StatusDefinition
from app.models.status_transition import StatusTransition, TransitionType
from app.models.user import User
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
from app.services.status_transition_permissions import (
    RESTRICTED_TRANSITION_TYPES,
    can_use_transition_type,
)
from app.services.status_transitions_seed import ensure_status_transitions_seeded

TransitionTypeLiteral = Literal["forward", "backward", "express", "relaunch"]

REPEATABLE_EVENT_STATUS_IDS = frozenset(
    {STATUS_LEAD_SESSION_RESCHEDULED, STATUS_LEAD_SESSION_CANCELLED}
)

# Automation shortcuts that mirror real-world event handlers.
AUTOMATION_ALLOWED_TRANSITIONS: dict[int | None, frozenset[int]] = {
    None: frozenset({STATUS_LEAD_NEW}),
    1: frozenset({STATUS_LEAD_OUTREACH}),
    2: frozenset({STATUS_LEAD_ENGAGEMENT}),
    3: frozenset(
        {
            STATUS_LEAD_SESSION_BOOKED,
            STATUS_LEAD_SESSION_RESCHEDULED,
            STATUS_LEAD_SESSION_CANCELLED,
        }
    ),
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
    12: frozenset({STATUS_LEAD_SESSION_RESCHEDULED, STATUS_LEAD_SESSION_CANCELLED}),
}


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    reason: str
    requires_override_comment: bool = False
    is_override: bool = False
    transition_type: TransitionTypeLiteral | None = None


def _definition_exists(db: Session, status_id: int) -> bool:
    return (
        db.query(StatusDefinition.id).filter(StatusDefinition.id == status_id).first() is not None
    )


def _lookup_transition_row(
    db: Session,
    from_status_id: int | None,
    to_status_id: int,
    *,
    transition_type: TransitionTypeLiteral | None = None,
) -> StatusTransition | None:
    if from_status_id is None:
        return None
    ensure_status_transitions_seeded(db)
    query = db.query(StatusTransition).filter(
        StatusTransition.from_status_id == from_status_id,
        StatusTransition.to_status_id == to_status_id,
    )
    if transition_type:
        query = query.filter(
            StatusTransition.transition_type == TransitionType(transition_type)
        )
    return query.first()


def _serialize_transition_option(
    db: Session,
    row: StatusTransition,
    *,
    user: User | None,
) -> dict[str, Any]:
    target = get_status_definition(db, row.to_status_id)
    transition_type = row.transition_type.value
    requires_comment = transition_type in {"backward", "express", "relaunch"}
    return {
        "to_status_id": row.to_status_id,
        "transition_type": transition_type,
        "stage_name": target.stage_name,
        "category": target.category,
        "description": target.description,
        "requires_comment": requires_comment,
        "can_trigger": can_use_transition_type(user, transition_type),
    }


def get_valid_transitions(
    db: Session,
    current_status_id: int | None,
    *,
    user: User | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return grouped lifecycle transitions available from the current pipeline status."""
    grouped: dict[str, list[dict[str, Any]]] = {
        "forward": [],
        "express": [],
        "backward": [],
        "relaunch": [],
    }
    if current_status_id is None:
        return grouped

    ensure_status_transitions_seeded(db)
    rows = (
        db.query(StatusTransition)
        .filter(StatusTransition.from_status_id == current_status_id)
        .order_by(StatusTransition.transition_type.asc(), StatusTransition.to_status_id.asc())
        .all()
    )
    for row in rows:
        transition_type = row.transition_type.value
        if transition_type not in grouped:
            continue
        grouped[transition_type].append(_serialize_transition_option(db, row, user=user))
    return grouped


def is_backward_transition(
    db: Session,
    current_status_id: int | None,
    next_status_id: int,
) -> bool:
    if current_status_id == next_status_id:
        return True
    row = _lookup_transition_row(db, current_status_id, next_status_id)
    return row is not None and row.transition_type == TransitionType.BACKWARD


def collect_skipped_standard_path_stages(
    db: Session,
    from_status_id: int,
    to_status_id: int,
) -> list[str]:
    """Stages skipped when jumping ahead on the standard forward path."""
    skipped: list[str] = []
    current_id = from_status_id
    visited: set[int] = set()
    while current_id and current_id != to_status_id:
        if current_id in visited:
            break
        visited.add(current_id)
        current = get_status_definition(db, current_id)
        if not current.next_stage_id or current.next_stage_id == to_status_id:
            break
        next_id = current.next_stage_id
        next_def = get_status_definition(db, next_id)
        if next_id == to_status_id:
            break
        skipped.append(next_def.stage_name)
        current_id = next_id
    return skipped


def build_express_transition_comment(
    db: Session,
    *,
    from_status_id: int,
    to_status_id: int,
    user_comment: str | None = None,
) -> str:
    target = get_status_definition(db, to_status_id)
    skipped = collect_skipped_standard_path_stages(db, from_status_id, to_status_id)
    skipped_label = "; ".join(skipped) if skipped else "intermediate workflow stages"
    auto_comment = (
        f"Express jump performed: skipped [{skipped_label}] to move to {target.stage_name}."
    )
    cleaned_user = (user_comment or "").strip()
    if cleaned_user:
        return f"{auto_comment}\n\nAdvisor note: {cleaned_user}"
    return auto_comment


def can_transition_to(
    db: Session,
    current_status_id: int | None,
    next_status_id: int,
    *,
    allow_override: bool = False,
    force_repeat: bool = False,
    transition_type: TransitionTypeLiteral | None = None,
    acting_user: User | None = None,
) -> TransitionResult:
    """
    Central workflow authority for pipeline status changes.

    Uses status_transitions when configured, with legacy automation and override fallbacks.
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

    configured = _lookup_transition_row(
        db,
        current_status_id,
        next_status_id,
        transition_type=transition_type,
    )
    if configured is None and transition_type:
        configured = _lookup_transition_row(db, current_status_id, next_status_id)

    if configured is not None:
        resolved_type = configured.transition_type.value
        if resolved_type in RESTRICTED_TRANSITION_TYPES and acting_user is not None:
            if not can_use_transition_type(acting_user, resolved_type):
                return TransitionResult(
                    allowed=False,
                    reason=(
                        f"Unauthorized Attempt: '{resolved_type}' transitions require "
                        "Student Manager or Super Admin access."
                    ),
                    transition_type=resolved_type,
                )
        requires_comment = resolved_type in {"backward", "express", "relaunch"}
        return TransitionResult(
            allowed=True,
            reason=f"Allowed {resolved_type} transition via status_transitions.",
            requires_override_comment=requires_comment,
            is_override=resolved_type in {"express", "backward", "relaunch"},
            transition_type=resolved_type,
        )

    if current_status_id is None:
        if next_status_id == STATUS_LEAD_NEW:
            return TransitionResult(
                allowed=True,
                reason="Initial lead status.",
                transition_type="forward",
            )
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
            if acting_user is not None and not can_use_transition_type(acting_user, "relaunch"):
                return TransitionResult(
                    allowed=False,
                    reason="Unauthorized Attempt: relaunch requires manager-level access.",
                    transition_type="relaunch",
                )
            if allow_override or can_use_transition_type(acting_user, "relaunch"):
                return TransitionResult(
                    allowed=True,
                    reason="Relaunch from terminal status.",
                    requires_override_comment=True,
                    transition_type="relaunch",
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
            transition_type="forward",
        )

    automation_targets = AUTOMATION_ALLOWED_TRANSITIONS.get(current_status_id, frozenset())
    if next_status_id in automation_targets:
        return TransitionResult(
            allowed=True,
            reason="Allowed automation funnel transition.",
        )

    if allow_override:
        if transition_type in RESTRICTED_TRANSITION_TYPES and acting_user is not None:
            if not can_use_transition_type(acting_user, transition_type):
                return TransitionResult(
                    allowed=False,
                    reason=(
                        f"Unauthorized Attempt: '{transition_type}' transitions require "
                        "Student Manager or Super Admin access."
                    ),
                    transition_type=transition_type,
                )
        return TransitionResult(
            allowed=True,
            reason=(
                f"Admin override: '{current.stage_name}' → "
                f"status {next_status_id} is outside the standard next step."
            ),
            requires_override_comment=True,
            is_override=True,
            transition_type=transition_type,
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
