import re

from sqlalchemy.orm import Session

from app.models.admin_role import AdminRole
from app.models.navigation_page import NavigationPage
from app.models.role_page_permission import RolePagePermission
from app.models.user import User

DEFAULT_NAVIGATION_PAGES: list[dict[str, str | int | bool]] = [
    {"name": "Dashboard", "route": "/", "icon": "LayoutDashboard", "sort_order": 1},
    {"name": "Chat", "route": "/messaging-hub", "icon": "MessagesSquare", "sort_order": 2},
    {"name": "Book Appointment", "route": "/book-appointment", "icon": "CalendarPlus", "sort_order": 3},
    {"name": "My Appointments", "route": "/my-bookings", "icon": "CalendarCheck", "sort_order": 4},
    {"name": "Manage Appointments", "route": "/counselling", "icon": "Calendar", "sort_order": 5},
    {"name": "Manage Users", "route": "/users", "icon": "UserCog", "sort_order": 5},
    {"name": "1 Counselling", "route": "/students/counselling", "icon": "GraduationCap", "sort_order": 6},
    {"name": "2 College Finding", "route": "/students/college-finding", "icon": "GraduationCap", "sort_order": 7},
    {"name": "3 Document Readiness", "route": "/students/document-readiness", "icon": "GraduationCap", "sort_order": 8},
    {"name": "4 Admission Processing", "route": "/students/admission-processing", "icon": "GraduationCap", "sort_order": 9},
    {"name": "5 Visa Processing", "route": "/students/visa-processing", "icon": "GraduationCap", "sort_order": 10},
    {"name": "6 Pre-Departure & Travel", "route": "/students/pre-departure-travel", "icon": "GraduationCap", "sort_order": 11},
    {"name": "7 Landing", "route": "/students/landing", "icon": "GraduationCap", "sort_order": 12},
    {"name": "AI Active", "route": "/ai-active", "icon": "Bot", "sort_order": 13},
    {"name": "Handoffs", "route": "/handoffs", "icon": "Users", "sort_order": 14},
    {"name": "All Prospects", "route": "/prospects", "icon": "Users", "sort_order": 15},
    {"name": "Express Leads", "route": "/express-leads", "icon": "Zap", "sort_order": 16},
    {"name": "All Leads", "route": "/offline-leads", "icon": "UserPlus", "sort_order": 17},
    {"name": "Archive", "route": "/archive", "icon": "Archive", "sort_order": 18},
    {"name": "AI Agent Brain", "route": "/agents", "icon": "Bot", "sort_order": 18},
    {"name": "Mission Control", "route": "/command-center", "icon": "Radio", "sort_order": 19},
    {"name": "My Profile", "route": "/my-profile", "icon": "UserCircle", "sort_order": 20},
    {"name": "Settings", "route": "/settings", "icon": "Settings", "sort_order": 21},
    {"name": "Invoice Workspace", "route": "/invoices", "icon": "Receipt", "sort_order": 21},
    {"name": "Access Control", "route": "/access-control", "icon": "ShieldCheck", "sort_order": 22},
    {"name": "Security Audit", "route": "/security-audit", "icon": "ShieldAlert", "sort_order": 23},
    {"name": "Meta Leads", "route": "/reports/meta-leads", "icon": "FileText", "sort_order": 24},
    {"name": "Exception Report", "route": "/reports/exceptions", "icon": "ShieldAlert", "sort_order": 25},
    {"name": "Analytics", "route": "/analytics", "icon": "BarChart3", "sort_order": 26},
    {"name": "Audit Logs", "route": "/reports/audit-logs", "icon": "ScrollText", "sort_order": 27},
    {"name": "Lead Quarantine", "route": "/quarantine", "icon": "ShieldAlert", "sort_order": 28},
    {"name": "Academia Hub", "route": "/academia", "icon": "GraduationCap", "sort_order": 29},
    {"name": "Nexus Intel", "route": "/nexus-intel", "icon": "Brain", "sort_order": 30},
    {"name": "FlowX", "route": "/flowx", "icon": "GitBranch", "sort_order": 31},
]

STUDENT_PIPELINE_PAGE_ROUTES: list[str] = [
    "/students/counselling",
    "/students/college-finding",
    "/students/document-readiness",
    "/students/admission-processing",
    "/students/visa-processing",
    "/students/pre-departure-travel",
    "/students/landing",
]

_LEGACY_STUDENT_PIPELINE_ROUTES: tuple[str, ...] = (
    "/students/documentation",
    "/students/admissions",
    "/students/visa-services",
    "/students/pre-departure",
    "/students/arrivals",
    "/students/prospects",
)
DEFAULT_ROLE_PAGE_ACCESS: dict[str, list[str]] = {
    "Super Admin": [page["route"] for page in DEFAULT_NAVIGATION_PAGES],
    "Web Admin": [
        "/",
        "/users",
        "/ai-active",
        "/handoffs",
        "/prospects",
        *STUDENT_PIPELINE_PAGE_ROUTES,
        "/express-leads",
        "/offline-leads",
        "/archive",
        "/agents",
        "/analytics",
        "/book-appointment",
        "/counselling",
        "/command-center",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
        "/academia",
        "/nexus-intel",
        "/flowx",
        "/invoices",
    ],
    "Student Manager": [
        "/",
        "/ai-active",
        "/handoffs",
        "/prospects",
        *STUDENT_PIPELINE_PAGE_ROUTES,
        "/express-leads",
        "/offline-leads",
        "/archive",
        "/analytics",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
        "/nexus-intel",
        "/flowx",
    ],
    "Student Advisor": [
        "/",
        "/ai-active",
        "/handoffs",
        "/prospects",
        *STUDENT_PIPELINE_PAGE_ROUTES,
        "/express-leads",
        "/offline-leads",
        "/archive",
        "/messaging-hub",
        "/my-bookings",
        "/my-profile",
        "/nexus-intel",
        "/flowx",
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
    ("/api/v1/bookings/staff", "/book-appointment"),
    ("/api/v1/bookings/availability-week", "/book-appointment"),
    ("/api/v1/bookings/availability", "/book-appointment"),
    ("/api/v1/bookings/contact-check", "/book-appointment"),
    ("/api/v1/bookings/counsellors", "/book-appointment"),
    ("/api/v1/bookings/session-config", "/book-appointment"),
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
    ("/api/v1/leads/express", "/express-leads"),
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
    ("/api/v1/students-master", "/invoices"),
    ("/api/v1/invoices", "/invoices"),
    ("/api/v1/security-audit", "/security-audit"),
    ("/api/v1/reports/export/exception-logs", "/reports/exceptions"),
    ("/api/v1/reports/exception-logs", "/reports/exceptions"),
    ("/api/v1/reports", "/reports/meta-leads"),
    ("/api/v1/admin/quarantine", "/quarantine"),
    ("/api/v1/admin/audit-logs", "/reports/audit-logs"),
    ("/api/v1/pages", "/access-control"),
    ("/api/v1/permissions", "/access-control"),
    ("/api/v1/command-center", "/command-center"),
    ("/api/v1/academia", "/academia"),
    ("/api/v1/intel", "/nexus-intel"),
    ("/api/v1/flowx", "/flowx"),
    ("/api/v1/scanx", "/students/document-readiness"),
]

LEAD_MUTATION_PAGE_ROUTES = [
    "/ai-active",
    "/handoffs",
    "/prospects",
    *STUDENT_PIPELINE_PAGE_ROUTES,
    "/express-leads",
    "/offline-leads",
    "/archive",
]

RBAC_EXEMPT_PREFIXES = (
    "/api/v1/login",
    "/api/v1/logout",
    "/api/v1/health",
    "/api/health",
    "/api/v1/webhooks",
    "/api/v1/leads/webhook",
    "/api/v1/ws",
    "/api/v1/academia/media",
    "/api/v1/invoices/download",
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
    "/api/v1/education-majors",
    "/api/v1/levels",
    "/api/v1/programs",
    "/api/v1/gpa-cgpa-scores",
    "/api/v1/full-time-study-years",
    "/api/v1/target-programs",
    "/api/v1/intel/terms",
    "/api/v1/intel/trivia",
    "/api/v1/intel/preferences",
    "/api/v1/audit-events",
    # Authenticated clients may POST exceptions from any page; GET still gated by route deps.
    "/api/v1/reports/exception-logs",
)


def seed_navigation_pages(db: Session) -> None:
    """Upsert catalog pages from DEFAULT_NAVIGATION_PAGES (safe for empty/staging DBs)."""
    # Single fetch — per-route SELECTs were stretching the SSH-tunnel window and
    # aborting startup mid-catalog (often around later routes like /archive).
    by_route = {
        str(page.route): page
        for page in db.query(NavigationPage).all()
    }
    for item in DEFAULT_NAVIGATION_PAGES:
        route = str(item["route"])
        existing = by_route.get(route)
        if existing:
            existing.name = str(item["name"])
            existing.icon = str(item["icon"])
            existing.sort_order = int(item["sort_order"])
            existing.is_active = True
            continue
        page = NavigationPage(
            name=str(item["name"]),
            route=route,
            icon=str(item["icon"]),
            sort_order=int(item["sort_order"]),
            is_active=True,
        )
        db.add(page)
        by_route[route] = page

    legacy_routes = (
        "/counselling-roster",
        "/reports",
        "/audit-logs",
        *_LEGACY_STUDENT_PIPELINE_ROUTES,
    )
    for legacy_route in legacy_routes:
        legacy_page = by_route.get(legacy_route)
        if legacy_page:
            legacy_page.is_active = False
    db.commit()


def seed_role_page_permissions(db: Session) -> None:
    """
    Ensure role_page_permissions rows exist for active roles/pages.

    Only inserts missing rows — does not overwrite Admin UI can_access changes.
    """
    pages = db.query(NavigationPage).filter(NavigationPage.is_active.is_(True)).all()
    if not pages:
        return
    roles = db.query(AdminRole).filter(AdminRole.is_active.is_(True)).all()
    if not roles:
        return

    # One round-trip for existing pairs — avoids N×M queries that stretch the
    # SSH-tunnel window and amplify mid-seed disconnects at startup.
    existing_pairs = {
        (int(admin_role_id), int(navigation_page_id))
        for admin_role_id, navigation_page_id in (
            db.query(
                RolePagePermission.admin_role_id,
                RolePagePermission.navigation_page_id,
            ).all()
        )
    }

    to_add: list[RolePagePermission] = []
    for role in roles:
        allowed_routes = DEFAULT_ROLE_PAGE_ACCESS.get(role.name, ["/"])
        if role.is_superuser:
            allowed_routes = [str(page["route"]) for page in DEFAULT_NAVIGATION_PAGES]
        for page in pages:
            key = (int(role.id), int(page.id))
            if key in existing_pairs:
                continue
            to_add.append(
                RolePagePermission(
                    admin_role_id=role.id,
                    navigation_page_id=page.id,
                    can_access=page.route in allowed_routes,
                )
            )
            existing_pairs.add(key)
    if to_add:
        db.add_all(to_add)
    db.commit()


def ensure_navigation_rbac(db: Session) -> None:
    """Seed navigation pages + missing role permissions (idempotent).

    Retries on transient disconnects (SSH tunnel flap / server closed connection)
    so a dropped socket mid-seed does not abort application startup.
    """
    import logging
    import time

    from sqlalchemy.exc import DBAPIError, OperationalError

    from app.db.database import dispose_db_pool, ensure_db_connection, wait_for_database

    log = logging.getLogger(__name__)
    last_exc: BaseException | None = None
    for attempt in range(4):
        try:
            if attempt:
                try:
                    db.rollback()
                except Exception:
                    pass
                dispose_db_pool(
                    reason=f"navigation rbac retry {attempt}: {type(last_exc).__name__ if last_exc else 'unknown'}"
                )
                # Re-gate on SELECT 1 — tunnel often needs a few seconds after a drop.
                wait_for_database(attempts=8, delay_sec=1.0, dispose_between=True)
                ensure_db_connection(db)
                time.sleep(min(1.0 * attempt, 3.0))
            seed_navigation_pages(db)
            seed_role_page_permissions(db)
            return
        except (OperationalError, DBAPIError) as exc:
            last_exc = exc
            log.warning(
                "Navigation RBAC seed failed attempt=%s/%s: %s",
                attempt + 1,
                4,
                exc,
            )
            try:
                db.rollback()
            except Exception:
                pass
            continue
    if last_exc:
        raise last_exc


def get_admin_role_by_name(db: Session, role_name: str) -> AdminRole | None:
    return (
        db.query(AdminRole)
        .filter(AdminRole.name == role_name.strip(), AdminRole.is_active.is_(True))
        .first()
    )


def _default_route_list() -> list[str]:
    return [str(page["route"]) for page in DEFAULT_NAVIGATION_PAGES]


def get_allowed_routes_for_user(db: Session, user: User) -> list[str]:
    # Match check_page_access: Super Admins see the full menu even if RBAC rows are missing.
    if user.is_superuser:
        routes = [
            route
            for (route,) in (
                db.query(NavigationPage.route)
                .filter(NavigationPage.is_active.is_(True))
                .order_by(NavigationPage.sort_order.asc())
                .all()
            )
        ]
        return routes if routes else _default_route_list()

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
    if path.startswith("/api/v1/leads/express"):
        return ["/express-leads", "/offline-leads"]

    if re.search(r"^/api/v1/leads/offline/\d+", path):
        return ["/offline-leads"]

    if re.search(r"^/api/v1/leads/\d+/status", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/ai-outreach", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/reset-whatsapp", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/whatsapp-conversation/reset", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/mark-read", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/override", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/notes", path):
        return LEAD_MUTATION_PAGE_ROUTES

    if re.search(r"^/api/v1/leads/\d+/journey", path):
        return ["/prospects", *STUDENT_PIPELINE_PAGE_ROUTES, "/my-bookings", "/counselling", "/ai-active", "/handoffs"]

    if re.search(r"^/api/v1/leads/\d+/valid-transitions", path):
        return ["/prospects", *STUDENT_PIPELINE_PAGE_ROUTES, "/my-bookings", "/counselling"]

    if re.search(r"^/api/v1/leads/\d+/pipeline-status", path):
        return ["/prospects", *STUDENT_PIPELINE_PAGE_ROUTES, "/my-bookings", "/counselling"]

    if path.startswith("/api/v1/leads/status-definitions"):
        return ["/prospects", *STUDENT_PIPELINE_PAGE_ROUTES, "/my-bookings", "/counselling"]

    if path.startswith("/api/v1/leads/prospects"):
        return ["/prospects", *STUDENT_PIPELINE_PAGE_ROUTES]

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
        return ["/my-bookings", "/students/counselling", "/prospects"]

    if path.startswith("/api/v1/students-master"):
        return ["/invoices", "/settings"]

    if path.startswith("/api/v1/bookings/matching"):
        return ["/my-bookings", "/students/counselling", "/prospects"]

    if path.startswith("/api/v1/users/me/profile") or path.startswith("/api/v1/users/me/change-password"):
        return ["/my-profile"]

    if path.startswith("/api/v1/admins/available"):
        return ["/counselling", "/my-bookings", "/book-appointment"]

    if path.startswith("/api/v1/bookings/staff"):
        return ["/book-appointment", "/counselling"]

    if path.startswith("/api/v1/bookings/availability-week"):
        return ["/book-appointment", "/counselling"]

    if path.startswith("/api/v1/bookings/availability"):
        return ["/book-appointment", "/counselling"]

    if path.startswith("/api/v1/bookings/contact-check"):
        return ["/book-appointment", "/counselling"]

    if path.startswith("/api/v1/bookings/counsellors"):
        return ["/book-appointment", "/counselling", "/invoices", "/settings"]

    if path.startswith("/api/v1/bookings/session-config"):
        return ["/book-appointment", "/counselling", "/my-bookings"]

    if path.startswith("/api/v1/bookings/switch"):
        return ["/counselling", "/my-bookings"]

    for prefix, page_route in API_ROUTE_TO_PAGE:
        if path == prefix or path.startswith(f"{prefix}/"):
            return [page_route]

    return []


def check_page_access(db: Session, user: User, page_route: str) -> bool:
    return check_any_page_access(db, user, [page_route])


def check_any_page_access(db: Session, user: User, page_routes: list[str]) -> bool:
    """OR-access across routes in two DB round-trips (critical over SSH tunnel RTT)."""
    if user.is_superuser:
        return True

    routes = [r for r in page_routes if r]
    if not routes:
        return False

    pages = (
        db.query(NavigationPage)
        .filter(NavigationPage.route.in_(routes), NavigationPage.is_active.is_(True))
        .all()
    )
    if not pages:
        return False

    if not user.admin_role_id:
        return any(page.route == "/" for page in pages)

    page_ids = [page.id for page in pages]
    permission = (
        db.query(RolePagePermission.id)
        .filter(
            RolePagePermission.admin_role_id == user.admin_role_id,
            RolePagePermission.navigation_page_id.in_(page_ids),
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
