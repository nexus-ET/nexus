from sqlalchemy.orm import Session

from app.models.status_change_reason import StatusChangeReason

DEFAULT_STATUS_CHANGE_REASONS: list[dict[str, str | bool]] = [
    {
        "reason_type": "Create",
        "reason": "New User Onboarded",
        "description": "Default reason when an admin creates a new user account",
    },
    {
        "reason_type": "Activate",
        "reason": "Role Restored",
        "description": "User access restored after administrative review",
    },
    {
        "reason_type": "Activate",
        "reason": "Returned from Leave",
        "description": "User returning from approved leave or suspension",
    },
    {
        "reason_type": "Activate",
        "reason": "Security Cleared",
        "description": "Security review completed and account re-enabled",
    },
    {
        "reason_type": "Activate",
        "reason": "Administrative Reactivation",
        "description": "Routine administrative reactivation of the account",
    },
    {
        "reason_type": "Deactivate",
        "reason": "Suspicious Activity",
        "description": "Immediate deactivation due to suspicious activity",
    },
    {
        "reason_type": "Deactivate",
        "reason": "Security Violation",
        "description": "Account deactivated following a security policy breach",
    },
    {
        "reason_type": "Deactivate",
        "reason": "Administrative",
        "description": "Routine administrative deactivation or role change",
    },
    {
        "reason_type": "Deactivate",
        "reason": "Employment Ended",
        "description": "Staff member no longer employed by the organization",
    },
    {
        "reason_type": "Deactivate",
        "reason": "Inactivity",
        "description": "Account deactivated due to prolonged inactivity",
    },
]


def seed_status_change_reasons(db: Session) -> None:
    """Disabled — status change reasons are managed via Admin UI / migrations, not startup seeds."""
    return


def get_reason_by_type(
    db: Session,
    reason_type: str,
    *,
    reason_id: int | None = None,
) -> StatusChangeReason | None:
    query = db.query(StatusChangeReason).filter(
        StatusChangeReason.reason_type == reason_type,
        StatusChangeReason.is_active.is_(True),
    )
    if reason_id is not None:
        query = query.filter(StatusChangeReason.id == reason_id)
    return query.first()


def get_create_reason(db: Session) -> StatusChangeReason | None:
    return get_reason_by_type(db, "Create")


def get_activate_reason(db: Session) -> StatusChangeReason | None:
    """Prefer an onboarding-friendly Activate reason when available."""
    preferred_labels = (
        "Initial Account Activation",
        "Administrative Reactivation",
        "Role Restored",
    )
    for label in preferred_labels:
        row = (
            db.query(StatusChangeReason)
            .filter(
                StatusChangeReason.reason_type == "Activate",
                StatusChangeReason.reason == label,
                StatusChangeReason.is_active.is_(True),
            )
            .first()
        )
        if row:
            return row
    return get_reason_by_type(db, "Activate")


def ensure_initial_activation_reason(db: Session) -> StatusChangeReason | None:
    """Create a stable Activate reason for first-time account activation if missing."""
    existing = (
        db.query(StatusChangeReason)
        .filter(
            StatusChangeReason.reason_type == "Activate",
            StatusChangeReason.reason == "Initial Account Activation",
        )
        .first()
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
        return existing

    row = StatusChangeReason(
        reason_type="Activate",
        reason="Initial Account Activation",
        description="Account activated when the user was first created or onboarded",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row
