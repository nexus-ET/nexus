from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

# API prefixes handled by @log_action — middleware skips these to avoid duplicate rows.
EXPLICIT_AUDIT_API_PREFIXES: tuple[str, ...] = (
    "/api/v1/settings/lead-sync",
    "/api/v1/settings/update",
    "/api/v1/settings/business-profile",
    "/api/v1/settings/public-holidays",
    "/api/v1/admin/quarantine",
    "/api/v1/admin/audit-logs/retention",
    "/api/v1/chat/",
    "/api/v1/command-center",
    "/api/v1/bookings",
    "/api/v1/sessions",
    "/api/v1/security-audit",
)

_FRONTEND_ROUTE_LABELS: dict[str, str] = {
    "/": "Dashboard",
    "/ai-active": "Manage Leads > AI Active",
    "/handoffs": "Manage Leads > Handoffs",
    "/prospects": "Manage Leads > All Prospects",
    "/archive": "Manage Leads > Archive",
    "/users": "Users > Manage Users",
    "/access-control": "Users > Access Control",
    "/agents": "Cockpit > AI Agent Brain",
    "/analytics": "Reports > Analytics",
    "/counselling": "Appointments > Manage Appointments",
    "/command-center": "Cockpit > Mission Control",
    "/messaging-hub": "Chat",
    "/my-bookings": "Appointments > My Appointments",
    "/my-profile": "My Profile",
    "/settings": "Cockpit > Application Settings",
    "/reports/meta-leads": "Reports > Meta Leads",
    "/reports/audit-logs": "Reports > Audit Logs",
    "/quarantine": "Manage Leads > Lead Quarantine",
    "/security-audit": "Cockpit > Security Audit",
}

# Longest-prefix wins (paths must be sorted by length descending when matching).
_API_AUDIT_RULES: list[tuple[str, dict[str, str]]] = [
    ("/api/v1/settings/lead-sync/run", {
        "page": "Dashboard",
        "menu": "Dashboard > Meta Lead Sync",
        "action": "Run Meta lead sync now",
    }),
    ("/api/v1/settings/lead-sync", {
        "page": "Dashboard",
        "menu": "Dashboard > Meta Lead Sync",
        "action": "Save Meta lead sync schedule",
    }),
    ("/api/v1/settings/business-profile", {
        "page": "Application Settings",
        "menu": "Settings",
        "action": "Update business profile",
    }),
    ("/api/v1/settings/update", {
        "page": "Application Settings",
        "menu": "Settings",
        "action": "Update application setting",
    }),
    ("/api/v1/settings/public-holidays", {
        "page": "Application Settings",
        "menu": "Settings > Public Holidays",
        "action": "Update public holidays",
    }),
    ("/api/v1/admin/audit-logs/retention", {
        "page": "Reports > Audit Logs",
        "menu": "Reports > Audit Logs",
        "action": "Update audit log retention",
    }),
    ("/api/v1/admin/quarantine", {
        "page": "Manage Leads > Lead Quarantine",
        "menu": "Manage Leads",
        "action": "Manage quarantined lead",
    }),
    ("/api/v1/security-audit/run", {
        "page": "Security Audit",
        "menu": "Security Audit",
        "action": "Run security audit",
    }),
    ("/api/v1/leads/active", {
        "page": "Manage Leads > AI Active",
        "menu": "Manage Leads",
        "action": "Update AI Active lead",
    }),
    ("/api/v1/leads/handoff", {
        "page": "Manage Leads > Handoffs",
        "menu": "Manage Leads",
        "action": "Update handoff lead",
    }),
    ("/api/v1/leads", {
        "page": "Manage Leads",
        "menu": "Manage Leads",
        "action": "Update lead record",
    }),
    ("/api/v1/bookings", {
        "page": "Appointments > Manage Appointments",
        "menu": "Appointments",
        "action": "Update counselling booking",
    }),
    ("/api/v1/chat", {
        "page": "Chat",
        "menu": "Chat",
        "action": "Chat activity",
    }),
    ("/api/v1/users", {
        "page": "Users > Manage Users",
        "menu": "Users",
        "action": "Manage user account",
    }),
    ("/api/v1/permissions", {
        "page": "Users > Access Control",
        "menu": "Users",
        "action": "Update access permissions",
    }),
    ("/api/v1/notifications", {
        "page": "Dashboard",
        "menu": "Dashboard",
        "action": "Update notification",
    }),
]

_ACTION_TYPE_LABELS: dict[str, str] = {
    "LOGIN_SUCCESS": "Signed in successfully",
    "LOGIN_FAILURE": "Failed sign-in attempt",
    "LOGOUT": "Signed out",
    "CREATE": "Created record",
    "UPDATE": "Updated record",
    "DELETE": "Deleted record",
    "update_setting": "Updated application setting",
    "update_business_profile": "Updated business profile",
    "update_lead_sync_settings": "Saved Meta lead sync schedule",
    "run_lead_sync": "Ran Meta lead sync",
    "update_quarantine_record": "Updated quarantined lead payload",
    "reprocess_quarantine_record": "Reprocessed quarantined lead",
    "delete_quarantine_record": "Deleted quarantined lead",
    "update_audit_log_retention": "Updated audit log retention",
    "trigger_security_audit": "Triggered security audit",
    "send_team_chat": "Sent team chat message",
    "assign_lead_from_chat": "Assigned lead from chat",
    "move_pipeline_candidate": "Moved pipeline candidate",
    "assign_booking": "Assigned counselling booking",
    "cancel_booking": "Cancelled counselling booking",
    "complete_session": "Completed counselling session",
    "save_session_notes": "Saved counselling session notes",
    "save_public_holiday": "Saved public holiday",
    "remove_public_holiday": "Removed public holiday",
    "bulk_save_public_holidays": "Bulk saved public holidays",
    "bulk_remove_public_holidays": "Bulk removed public holidays",
    "toggle_public_holiday": "Toggled public holiday",
    "PAGE_VIEW": "Viewed page",
    "UI_CLICK": "Clicked control",
    "UI_FIELD_CHANGE": "Changed field",
    "API_READ": "Loaded data",
}


_GENERIC_ACTION_TYPES = frozenset({"CREATE", "UPDATE", "DELETE"})


def should_skip_middleware_audit(api_path: str) -> bool:
    normalized = api_path.rstrip("/") or "/"
    for prefix in EXPLICIT_AUDIT_API_PREFIXES:
        p = prefix.rstrip("/")
        if normalized == p or normalized.startswith(f"{p}/"):
            return True
    return False


def _normalize_api_path(path: str) -> str:
    return path.split("?", 1)[0].rstrip("/") or "/"


def _match_api_rule(api_path: str) -> dict[str, str] | None:
    normalized = _normalize_api_path(api_path)
    for prefix, rule in sorted(_API_AUDIT_RULES, key=lambda item: len(item[0]), reverse=True):
        p = prefix.rstrip("/")
        if normalized == p or normalized.startswith(f"{p}/"):
            return dict(rule)
    return None


def _label_from_frontend_path(path: str) -> str | None:
    normalized = path.rstrip("/") or "/"
    if normalized in _FRONTEND_ROUTE_LABELS:
        return _FRONTEND_ROUTE_LABELS[normalized]
    for route, label in sorted(_FRONTEND_ROUTE_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        if route != "/" and (normalized == route or normalized.startswith(f"{route}/")):
            return label
    return None


def resolve_ui_context(
    *,
    api_path: str,
    method: str,
    referer: str | None = None,
    ui_page_header: str | None = None,
) -> dict[str, str]:
    rule = _match_api_rule(api_path) or {}
    page = rule.get("page", "")
    menu = rule.get("menu", "")
    action = rule.get("action", "")

    if ui_page_header:
        ui_label = _label_from_frontend_path(ui_page_header) or ui_page_header
        if ui_label:
            menu = menu or ui_label
            page = page or ui_label

    if referer:
        referer_path = urlparse(referer).path
        referer_label = _label_from_frontend_path(referer_path)
        if referer_label:
            menu = menu or referer_label
            page = page or referer_label

    if not action:
        verb = method.upper()
        if verb == "POST":
            action = "Created or submitted data"
        elif verb in {"PUT", "PATCH"}:
            action = "Updated data"
        elif verb == "DELETE":
            action = "Deleted data"
        else:
            action = f"{verb} request"

    if not page:
        parts = [segment for segment in api_path.split("/") if segment not in {"api", "v1"}]
        page = " / ".join(parts[:2]) if parts else "Application"

    if not menu:
        menu = page

    return {"page": page, "menu": menu, "action": action}


def build_audit_details(
    *,
    method: str,
    api_path: str,
    status_code: int,
    action_type: str | None = None,
    referer: str | None = None,
    ui_page_header: str | None = None,
    request_body: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ui = resolve_ui_context(
        api_path=api_path,
        method=method,
        referer=referer,
        ui_page_header=ui_page_header,
    )
    if action_type and action_type in _ACTION_TYPE_LABELS and action_type not in _GENERIC_ACTION_TYPES:
        ui_action = _ACTION_TYPE_LABELS[action_type]
    else:
        ui_action = ui["action"]

    summary = f"{ui_action} on {ui['page']}"
    if status_code >= 400:
        summary = f"Failed: {summary} (HTTP {status_code})"

    details: dict[str, Any] = {
        "summary": summary,
        "page": ui["page"],
        "menu": ui["menu"],
        "action": ui_action,
        "http_method": method.upper(),
        "api_endpoint": _normalize_api_path(api_path),
        "status_code": status_code,
    }
    if action_type:
        details["action_type"] = action_type
    if request_body:
        details["request_body"] = request_body
    if extra:
        details.update(extra)
    return details


def build_auth_audit_details(
    action_type: str,
    username: str,
    *,
    reason: str | None = None,
    status_code: int = 200,
) -> dict[str, Any]:
    action = _ACTION_TYPE_LABELS.get(action_type, action_type.replace("_", " ").title())
    page = "Login" if action_type != "LOGOUT" else "Sign out"
    menu = "Authentication"
    summary = f"{action} — {username}"
    if reason:
        summary = f"{summary} ({reason.replace('_', ' ')})"
    if status_code >= 400:
        summary = f"Failed: {summary}"

    details: dict[str, Any] = {
        "summary": summary,
        "page": page,
        "menu": menu,
        "action": action,
        "username": username,
        "http_method": "POST",
        "api_endpoint": "/api/v1/logout" if action_type == "LOGOUT" else "/api/v1/login",
        "status_code": status_code,
        "action_type": action_type,
    }
    if reason:
        details["reason"] = reason
    return details


def client_event_target_resource(action_type: str, requested: str | None = None) -> str:
    if requested and requested.strip() and requested.strip() != "ui_activity":
        return requested.strip()[:100]
    mapping = {
        "PAGE_VIEW": "navigation",
        "UI_CLICK": "ui_interaction",
        "UI_FIELD_CHANGE": "ui_interaction",
        "API_READ": "api_read",
    }
    return mapping.get(action_type, "ui_activity")


def build_client_event_details(
    *,
    action_type: str,
    page: str,
    action: str,
    menu: str | None = None,
    element_type: str | None = None,
    element_label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_path = page.rstrip("/") or "/"
    page_label = _label_from_frontend_path(page_path) or page_path
    menu_label = menu or page_label
    labeled_action = _ACTION_TYPE_LABELS.get(action_type, action)

    if action_type == "PAGE_VIEW":
        summary = f"Viewed {page_label}"
    elif action_type == "UI_CLICK":
        target = element_label or action or "control"
        summary = f"Clicked \"{target}\" on {page_label}"
    elif action_type == "UI_FIELD_CHANGE":
        target = element_label or action or "field"
        field_value = (metadata or {}).get("field_value") or (metadata or {}).get("trigger_value")
        if field_value and str(field_value) not in str(target):
            summary = f"Changed {target} to {field_value} on {page_label}"
        else:
            summary = f"Changed \"{target}\" on {page_label}"
    elif action_type == "API_READ":
        trigger_control = (metadata or {}).get("trigger_control")
        trigger_value = (metadata or {}).get("trigger_value")
        if trigger_control and trigger_value:
            summary = f"Loaded data — {trigger_control} set to {trigger_value} on {page_label}"
        elif action and action != "Loaded data":
            summary = f"{action} on {page_label}"
        else:
            summary = f"Loaded data on {page_label}"
    else:
        summary = f"{labeled_action} on {page_label}"

    details: dict[str, Any] = {
        "summary": summary,
        "page": page_label,
        "menu": menu_label,
        "action": action or labeled_action,
        "action_type": action_type,
        "page_path": page_path,
    }
    if element_type:
        details["element_type"] = element_type
    if element_label:
        details["element_label"] = element_label
    if metadata:
        details["metadata"] = metadata
    return details


def format_audit_details_for_display(details: dict[str, Any] | None) -> str:
    if not details:
        return "—"

    if isinstance(details.get("summary"), str) and details["summary"].strip():
        lines = [details["summary"].strip()]
        page = details.get("page") or details.get("menu")
        if page and page not in details["summary"]:
            lines.append(f"Page: {page}")
        action = details.get("action")
        if action and str(action) not in details["summary"]:
            lines.append(f"Action: {action}")
        endpoint = details.get("api_endpoint")
        if endpoint:
            lines.append(f"API: {endpoint}")
        return " · ".join(lines)

    if details.get("username") and not details.get("summary"):
        return f"Auth event for {details['username']}"

    # Legacy rows
    method = details.get("method") or details.get("http_method")
    path = details.get("path") or details.get("api_endpoint")
    status_code = details.get("status_code")
    parts: list[str] = []
    if method and path:
        parts.append(f"{method} {path}")
    if status_code is not None:
        parts.append(f"HTTP {status_code}")
    if details.get("message"):
        parts.append(str(details["message"]))
    return " · ".join(parts) if parts else "—"
