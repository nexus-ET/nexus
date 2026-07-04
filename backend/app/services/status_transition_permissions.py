from __future__ import annotations

from app.models.user import User

LIFECYCLE_MANAGER_ROLE_NAMES = frozenset(
    {
        "Student Manager",
        "Super Admin",
        "Web Admin",
    }
)

RESTRICTED_TRANSITION_TYPES = frozenset({"express", "backward", "relaunch"})


def resolve_user_role_name(user: User) -> str:
    if user.is_superuser:
        return "Super Admin"
    role = getattr(user, "admin_role_ref", None) or getattr(user, "admin_role", None)
    if role and getattr(role, "name", None):
        return str(role.name)
    legacy = getattr(user, "role", None)
    return str(legacy or "")


def can_use_restricted_lifecycle_transition(user: User | None) -> bool:
    """Express, backward, and relaunch moves require manager-level access."""
    if not user:
        return False
    if user.is_superuser:
        return True
    return resolve_user_role_name(user) in LIFECYCLE_MANAGER_ROLE_NAMES


def can_use_transition_type(user: User | None, transition_type: str) -> bool:
    normalized = (transition_type or "forward").strip().lower()
    if normalized == "forward":
        return user is not None
    if normalized in RESTRICTED_TRANSITION_TYPES:
        return can_use_restricted_lifecycle_transition(user)
    return False
