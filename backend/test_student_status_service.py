from types import SimpleNamespace

from app.models.status_history import ChangedByType
from app.services.status_definition_service import STATUS_LEAD_NEW, STATUS_LEAD_OUTREACH
from app.services.student_status_service import _format_user_name


def test_format_user_name_prefers_full_name():
    user = SimpleNamespace(first_name="Jane", last_name="Doe", email="jane@example.com")
    assert _format_user_name(user) == "Jane Doe"


def test_format_user_name_system_fallback():
    assert _format_user_name(None) == "System"


def test_changed_by_type_enum_values():
    assert ChangedByType.SYSTEM.value == "system"
    assert ChangedByType.ADMIN.value == "admin"


def test_lead_status_constants_for_automation():
    assert STATUS_LEAD_NEW == 1
    assert STATUS_LEAD_OUTREACH == 2
