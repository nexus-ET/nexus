import re

from sqlalchemy.orm import Session

from app.models.admin_role import AdminRole
from app.models.navigation_page import NavigationPage
from app.models.role_page_permission import RolePagePermission
from app.models.user import User

DEFAULT_NAVIGATION_PAGES: list[dict[str, str | int | bool]] = [
    {"name": "Dashboard", "route": "/", "icon": "LayoutDashboard", "sort_order": 1},
    {"name": "Chat", "route": "/messaging-hub", "icon": "MessagesSquare", "sort_order": 2},
    {"name": "My Appointments", "route": "/my-bookings", "icon": "CalendarCheck", "sort_order": 3},
    {"name": "Manage Appointments", "route": "/counselling", "icon": "Calendar", "sort_order": 4},
    {"name": "Manage Users", "route": "/users", "icon": "UserCog", "sort_order": 5},
    {"name": "AI Active", "route": "/ai-active", "icon": "Bot", "sort_order": 6},
    {"name": "Handoffs", "route": "/handoffs", "icon": "Users", "sort_order": 7},
    {"name": "All Prospects", "route": "/prospects", "icon": "Users", "sort_order": 8},
    {"name": "Offline Leads", "route": "/offline-leads", "icon": "UserPlus", "sort_order": 9},
    {"name": "Archive", "route": "/archive", "icon": "Archive", "sort_order": 10},
    {"name": "AI Agent Brain", "route": "/agents", "icon": "Bot", "sort_order": 11},
    {"name": "Mission Control", "route": "/command-center", "icon": "Radio", "sort_order": 12},
    {"name": "My Profile", "route": "/my-profile", "icon": "UserCircle", "sort_order": 13},
    {"name": "Settings", "route": "/settings", "icon": "Settings", "sort_order": 14},
    {"name": "Access Control", "route": "/access-control", "icon": "ShieldCheck", "sort_order": 15},
    {"name": "Security Audit", "route": "/security-audit", "icon": "ShieldAlert", "sort_order": 16},
    {"name": "Meta Leads", "route": "/reports/meta-leads", "icon": "FileText", "sort_order": 17},
    {"name": "Analytics", "route": "/analytics", "icon": "BarChart3", "sort_order": 18},
    {"name": "Audit Logs", "route": "/reports/audit-logs", "icon": "ScrollText", "sort_order": 19},
    {"name": "Lead Quarantine", "route": "/quarantine", "icon": "ShieldAlert", "sort_order": 20},
]

DEFAULT_ROLE_PAGE_ACCESS: dict[str, list[str]] = {
    "Super Admin": [page["route"] for page in DEFAULT_NAVIGATION_PAGES],
    "Web Admin": [
        "/",
        "/users",
        "/ai-active",
        "/handoffs",
        "/prospects",
        "/offline-leads",
        "/archive",
        "/agents",
        "/analytics",
        "/counselling",
        "/command-center",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
    ],
    "Student Manager": [
        "/",
        "/ai-active",
        "/handoffs",
        "/prospects",
        "/offline-leads",
        "/archive",
        "/analytics",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
    ],
    "Student Advisor": [
        "/",
        "/ai-active",
        "/handoffs",
        "/prospects",
        "/offline-leads",
        "/archive",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
    ],
}

API_ROUTE_TO_PAGE: list[tuple[str, str]] = [
    ("/api/v1/dashboard", "/"),
    ("/api/v1/users", "/users"),
    ("/api/v1/agents", "/agents"),
    ("/api/v1/audit", "/agents"),
    ("/api/v1/analytics", "/analytics"),
    ("/api/v1/bookings/mine", "/my-bookings"),
    ("/api/v1/counselling/summarize", "/my-bookings"),
    ("/api/v1/admins/available", "/counselling"),
    ("/api/v1/bookings", "/counselling"),
    ("/api/v1/pipeline", "/counselling"),
    ("/api/v1/sessions", "/counselling"),
    ("/api/v1/leads/active-stream", "/ai-active"),
    ("/api/v1/leads/active", "/ai-active"),
    ("/api/v1/leads/handoffs", "/handoffs"),
    ("/api/v1/leads/handoff", "/handoffs"),
    ("/api/v1/leads/queue", "/handoffs"),
    ("/api/v1/leads/all", "/prospects"),
    ("/api/v1/leads/prospects", "/prospects"),
    ("/api/v1/leads/offline", "/offline-leads"),
    ("/api/v1/leads/archive", "/archive"),
    ("/api/v1/leads/pipeline", "/"),
    ("/api/v1/leads", "/ai-active"),
    ("/api/v1/notifications", "/"),
    ("/api/v1/notifications/inbox", "/"),
    ("/api/v1/notifications/push-token", "/"),
    ("/api/v1/settings", "/settings"),
    ("/api/v1/settings/business-timezone", "/"),
    ("/api/v1/settings/business-email-domain", "/users"),
    ("/api/v1/security-audit", "/security-audit"),
    ("/api/v1/reports", "/reports/meta-leads"),
    ("/api/v1/admin/quarantine", "/quarantine"),
    ("/api/v1/admin/audit-logs", "/reports/audit-logs"),
    ("/api/v1/pages", "/access-control"),
    ("/api/v1/permissions", "/access-control"),
    ("/api/v1/command-center", "/command-center"),
]

LEAD_MUTATION_PAGE_ROUTES = ["/ai-active", "/handoffs", "/prospects", "/offline-leads", "/archive"]

RBAC_EXEMPT_PREFIXES = (
    "/api/v1/login",
    "/api/v1/logout",
    "/api/v1/webhooks",
    "/api/v1/leads/webhook",
    "/api/v1/ws",
    "/docs",
    "/openapi.json",
    "/redoc",
)

RBAC_PUBLIC_AUTH_PREFIXES = (
    "/api/v1/permissions/my-role",
    "/api/v1/users/me",
    "/api/v1/settings/business-timezone",
    "/api/v1/settings/whatsapp-outreach",
    "/api/v1/countries",
    "/api/v1/education-degrees",
    "/api/v1/gpa-cgpa-scores",
    "/api/v1/target-programs",
    "/api/v1/audit-events",
)


def seed_navigation_pages(db: Session) -> None:
    for item in DEFAULT_NAVIGATION_PAGES:
        existing = (
            db.query(NavigationPage)
            .filter(NavigationPage.route == item["route"])
            .first()
        )
        if existing:
            existing.name = str(item["name"])
            existing.icon = str(item["icon"])
            existing.sort_order = int(item["sort_order"])
            existing.is_active = True
            continue

        db.add(
            NavigationPage(
                name=str(item["name"]),
                route=str(item["route"]),
                icon=str(item["icon"]),
                sort_order=int(item["sort_order"]),
                is_active=True,
            )
        )
    old_roster_page = (
        db.query(NavigationPage)
        .filter(NavigationPage.route == "/counselling-roster")
        .first()
    )
    if old_roster_page:
        old_roster_page.is_active = False
    for legacy_route in ("/reports", "/audit-logs"):
        legacy_page = (
            db.query(NavigationPage)
            .filter(NavigationPage.route == legacy_route)
            .first()
        )
        if legacy_page:
            legacy_page.is_active = False
    db.commit()


def seed_role_page_permissions(db: Session) -> None:
    pages = db.query(NavigationPage).filter(NavigationPage.is_active.is_(True)).all()
    page_by_route = {page.route: page for page in pages}
    roles = db.query(AdminRole).filter(AdminRole.is_active.is_(True)).all()

    for role in roles:
        allowed_routes = DEFAULT_ROLE_PAGE_ACCESS.get(role.name, ["/"])
        if role.is_superuser:
            allowed_routes = [page["route"] for page in DEFAULT_NAVIGATION_PAGES]
        for page in pages:
            permission = (
                db.query(RolePagePermission)
                .filter(
                    RolePagePermission.admin_role_id == role.id,
                    RolePagePermission.navigation_page_id == page.id,
                )
                .first()
            )
            can_access = page.route in allowed_routes
            if permission:
                if permission.can_access != can_access:
                    permission.can_access = can_access
                continue

            db.add(
                RolePagePermission(
                    admin_role_id=role.id,
                    navigation_page_id=page.id,
                    can_access=can_access,
                )
            )
    db.commit()


def get_admin_role_by_name(db: Session, role_name: str) -> AdminRole | None:
    return (
        db.query(AdminRole)
        .filter(AdminRole.name == role_name.strip(), AdminRole.is_active.is_(True))
        .first()
    )


def get_allowed_routes_for_user(db: Session, user: User) -> list[str]:
    if not user.admin_role_id:
        return ["/"]

    permissions = (
        db.query(NavigationPage.route)
        .join(
            RolePagePermission,
            RolePagePermission.navigation_page_id == NavigationPage.id,
        )
        .filter(
            RolePagePermission.admin_role_id == user.admin_role_id,
            RolePagePermission.can_access.is_(True),
            NavigationPage.is_active.is_(True),
        )
        .order_by(NavigationPage.sort_order.asc())
        .all()
    )
    routes = [route for (route,) in permissions]
    return routes if routes else ["/"]


def resolve_page_route_for_api_path(path: str) -> str | None:
    routes = resolve_page_routes_for_api_path(path)
    return routes[0] if routes else None


def resolve_page_routes_for_api_path(path: str) -> list[str]:
    if re.search(r"^/api/v1/leads/offline/\d+", path):
        return ["/offline-leads"]

    if re.search(r"^/api/v1/leads/\d+/status", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/ai-outreach", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/mark-read", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/override", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/notes", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/journey", path):
        return ["/prospects", "/my-bookings", "/counselling", "/ai-active", "/handoffs"]

    if re.search(r"^/api/v1/leads/\d+/valid-transitions", path):
        return ["/prospects", "/my-bookings", "/counselling"]

    if re.search(r"^/api/v1/leads/\d+/pipeline-status", path):
        return ["/prospects", "/my-bookings", "/counselling"]

    if path.startswith("/api/v1/leads/status-definitions"):
        return ["/prospects", "/my-bookings", "/counselling"]

    if re.search(r"^/api/v1/leads/\d+$", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if path.startswith("/api/v1/leads/webhook/"):
        return LEAD_MUTATION_PAGE_ROUTES

    if path.startswith("/api/v1/chat/config"):
        return ["/messaging-hub", "/command-center"]

    if path.startswith("/api/v1/chat/conversations") or path.startswith("/api/v1/chat/admins"):
        return ["/messaging-hub"]

    if path.startswith("/api/v1/chat/messaging") or path.startswith("/api/v1/chat/messages/search") or path.startswith("/api/v1/chat/search"):
        return ["/messaging-hub"]

    if path.startswith("/api/v1/chat"):
        return ["/command-center", "/messaging-hub"]

    if path.startswith("/api/v1/bookings/mine"):
        return ["/my-bookings"]

    if path.startswith("/api/v1/users/me/profile") or path.startswith("/api/v1/users/me/change-password"):
        return ["/my-profile"]

    if path.startswith("/api/v1/admins/available"):
        return ["/counselling", "/my-bookings"]

    if path.startswith("/api/v1/bookings/switch"):
        return ["/counselling", "/my-bookings"]

    for prefix, page_route in API_ROUTE_TO_PAGE:
        if path == prefix or path.startswith(f"{prefix}/"):
            return [page_route]

    return []


def check_page_access(db: Session, user: User, page_route: str) -> bool:
    if user.is_superuser:
        return True

    page = (
        db.query(NavigationPage)
        .filter(NavigationPage.route == page_route, NavigationPage.is_active.is_(True))
        .first()
    )
    if not page:
        return False

    if not user.admin_role_id:
        return page_route == "/"

    permission = (
        db.query(RolePagePermission)
        .filter(
            RolePagePermission.admin_role_id == user.admin_role_id,
            RolePagePermission.navigation_page_id == page.id,
            RolePagePermission.can_access.is_(True),
        )
        .first()
    )
    return permission is not None


def upsert_role_page_permission(
    db: Session,
    *,
    admin_role_id: int,
    navigation_page_id: int,
    can_access: bool,
) -> RolePagePermission:
    permission = (
        db.query(RolePagePermission)
        .filter(
            RolePagePermission.admin_role_id == admin_role_id,
            RolePagePermission.navigation_page_id == navigation_page_id,
        )
        .first()
    )
    if permission:
        permission.can_access = can_access
    else:
        permission = RolePagePermission(
            admin_role_id=admin_role_id,
            navigation_page_id=navigation_page_id,
            can_access=can_access,
        )
        db.add(permission)

    db.commit()
    db.refresh(permission)
    return permission
