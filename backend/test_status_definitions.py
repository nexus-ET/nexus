from types import SimpleNamespace

from app.services.status_definition_service import (
    LEGACY_ADMISSION_STAGE_MAP,
    STAGE_LEAD_OUTREACH,
    STATUS_COUNSELLING_FINISHED,
    STATUS_COUNSELLING_SCHEDULED,
    STATUS_LEAD_NEW,
    STATUS_LEAD_OUTREACH,
    STATUS_PROSPECT_ENROLLED,
    TERMINAL_STATUS_IDS,
    serialize_status_definition,
)


def test_legacy_admission_stage_map_contains_counselling():
    assert LEGACY_ADMISSION_STAGE_MAP["COUNSELLING"] == STATUS_COUNSELLING_SCHEDULED


def test_status_constants():
    assert STATUS_LEAD_NEW == 1
    assert STATUS_LEAD_OUTREACH == 2
    assert STATUS_COUNSELLING_SCHEDULED == 10
    assert STATUS_COUNSELLING_FINISHED == 11
    assert STATUS_PROSPECT_ENROLLED == 37


def test_terminal_status_ids():
    assert 8 in TERMINAL_STATUS_IDS
    assert 39 in TERMINAL_STATUS_IDS
    assert 6 not in TERMINAL_STATUS_IDS
    assert 10 not in TERMINAL_STATUS_IDS


def test_serialize_status_definition_shape():
    row = SimpleNamespace(
        id=2,
        stage_name=STAGE_LEAD_OUTREACH,
        category="Lead",
        description="First outreach attempt initiated by advisor.",
        next_stage_id=3,
    )
    payload = serialize_status_definition(row)
    assert payload["stage_name"] == "Lead: Outreach"
    assert payload["next_stage_id"] == 3
    assert payload["is_terminal"] is False
