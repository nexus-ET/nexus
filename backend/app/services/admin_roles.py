from sqlalchemy.orm import Session

from app.models.admin_role import AdminRole

DEFAULT_ADMIN_ROLES: list[dict[str, str | bool | int]] = [
    {
        "name": "Web Admin",
        "description": "Full access to web administration and user management features",
        "is_superuser": False,
        "sort_order": 1,
    },
    {
        "name": "Student Advisor",
        "description": "Manages assigned leads and student advisor workflows",
        "is_superuser": False,
        "sort_order": 2,
    },
    {
        "name": "Student Manager",
        "description": "Oversees advisor teams and operational lead management",
        "is_superuser": False,
        "sort_order": 3,
    },
    {
        "name": "Super Admin",
        "description": "Highest privilege level with full system access",
        "is_superuser": True,
        "sort_order": 4,
    },
]


def seed_admin_roles(db: Session) -> None:
    for item in DEFAULT_ADMIN_ROLES:
        existing = (
            db.query(AdminRole)
            .filter(AdminRole.name == item["name"])
            .first()
        )
        if existing:
            existing.description = str(item["description"])
            existing.is_superuser = bool(item["is_superuser"])
            existing.sort_order = int(item["sort_order"])
            existing.is_active = True
            continue

        db.add(
            AdminRole(
                name=str(item["name"]),
                description=str(item["description"]),
                is_superuser=bool(item["is_superuser"]),
                is_active=True,
                sort_order=int(item["sort_order"]),
            )
        )
    db.commit()


def get_active_admin_roles(db: Session) -> list[AdminRole]:
    return (
        db.query(AdminRole)
        .filter(AdminRole.is_active.is_(True))
        .order_by(AdminRole.sort_order.asc(), AdminRole.id.asc())
        .all()
    )


def get_active_admin_role_names(db: Session) -> list[str]:
    return [role.name for role in get_active_admin_roles(db)]


def get_active_admin_role_ids(db: Session) -> list[int]:
    return [role.id for role in get_active_admin_roles(db)]


def get_admin_role_by_id(db: Session, role_id: int | None) -> AdminRole | None:
    if not role_id:
        return None
    return (
        db.query(AdminRole)
        .filter(
            AdminRole.id == role_id,
            AdminRole.is_active.is_(True),
        )
        .first()
    )


def get_admin_role_by_name(db: Session, role_name: str | None) -> AdminRole | None:
    if not role_name:
        return None
    return (
        db.query(AdminRole)
        .filter(
            AdminRole.name == role_name.strip(),
            AdminRole.is_active.is_(True),
        )
        .first()
    )


def get_default_admin_role(db: Session) -> AdminRole | None:
    roles = get_active_admin_roles(db)
    if not roles:
        return None
    for role in roles:
        if role.name == "Web Admin":
            return role
    return roles[0]
