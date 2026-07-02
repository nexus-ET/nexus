from app.models.status_history import ChangedByType, _enum_values


def test_changed_by_type_enum_values_match_database_strings():
    assert _enum_values(ChangedByType) == ["system", "admin"]
    assert ChangedByType.ADMIN.value == "admin"
    assert ChangedByType.SYSTEM.value == "system"
