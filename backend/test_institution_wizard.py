"""Institution wizard: campuses are optional on draft save and publish."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.schemas.academia_wizard import WizardStepSaveRequest
from app.services.institution_wizard_service import (
    _validate_publish_payload,
    _validate_step_save_payload,
)

CONTACTS = {
    "phone_numbers": [{"type": "Main", "value": "+15555550100"}],
    "email_addresses": [{"type": "Main", "value": "info@example.edu"}],
}
MIN_INSTITUTION = {"name": "Optional Campus University", **CONTACTS}
MIN_COLLEGE = {"name": "College of Arts", "linked_campuses": [], **CONTACTS}


def _base_payload(**overrides):
    payload = {
        "institution": MIN_INSTITUTION,
        "campuses": [],
        "colleges": [],
        "courses": [],
        "intakes": [],
        "pictures": [],
    }
    payload.update(overrides)
    return payload


def test_step_1_empty_email_list_is_valid():
    payload = _validate_step_save_payload(
        _base_payload(
            institution={
                "name": "Optional Email University",
                "phone_numbers": CONTACTS["phone_numbers"],
                "email_addresses": [],
            }
        ),
        WizardStepSaveRequest(step=1, data={
            "name": "Optional Email University",
            "phone_numbers": CONTACTS["phone_numbers"],
            "email_addresses": [],
        }, mark_complete=True),
    )
    assert payload["institution"]["email_addresses"] == []


def test_step_2_empty_campus_email_list_is_valid():
    campus = {
        "name": "Main Campus",
        "location_id": 10,
        "campus_type_id": 2,
        "phone_numbers": [],
        "email_addresses": [],
    }
    step1 = _validate_step_save_payload(
        _base_payload(campuses=[campus]),
        WizardStepSaveRequest(
            step=1,
            data={"name": "Optional Email University", "email_addresses": []},
            mark_complete=True,
        ),
    )
    assert step1["campuses"][0]["email_addresses"] == []

    payload = _validate_step_save_payload(
        _base_payload(),
        WizardStepSaveRequest(step=2, data=[campus], mark_complete=True),
    )
    assert payload["campuses"][0]["email_addresses"] == []

    from app.schemas.academia_wizard import WizardCampusStep
    from app.schemas.academia_hub import CampusCreate

    parsed = WizardCampusStep.model_validate(campus)
    assert all(not (entry.value or "").strip() for entry in parsed.email_addresses)
    created = CampusCreate(
        institution_id=1,
        **campus,
    )
    assert all(not (entry.value or "").strip() for entry in created.email_addresses)


def test_step_2_empty_campus_list_is_valid():
    payload = _validate_step_save_payload(
        _base_payload(),
        WizardStepSaveRequest(step=2, data=[], mark_complete=True),
    )
    assert payload["campuses"] == []
    assert payload["campus"] is None


def test_later_step_save_does_not_require_campuses():
    payload = _validate_step_save_payload(
        _base_payload(),
        WizardStepSaveRequest(step=3, data=[MIN_COLLEGE], mark_complete=True),
    )
    assert payload["campuses"] == []
    assert payload["colleges"][0]["name"] == "College of Arts"
    assert payload["colleges"][0].get("linked_campuses") in ([], None)


def test_incomplete_campus_still_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_step_save_payload(
            _base_payload(),
            WizardStepSaveRequest(
                step=2,
                data=[{"name": "Main Campus"}],
                mark_complete=True,
            ),
        )
    assert exc.value.status_code == 400
    assert "validation failed" in str(exc.value.detail).lower()


def test_refresh_draft_course_college_ids_stamps_local_ids():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.services.institution_wizard_service import _refresh_draft_course_college_ids

    draft = SimpleNamespace(
        institution_id=4,
        payload={
            "colleges": [
                {"id": 1, "local_id": "law-local", "name": "Law"},
                {"id": 2, "local_id": "arts-local", "name": "Arts"},
            ],
            "courses": [
                {"course_id": 101, "college_id": None, "college_local_id": None},
                {"course_id": 102, "college_id": None, "college_local_id": None},
            ],
        },
    )
    offerings = [
        SimpleNamespace(course_id=101, college_id=1),
        SimpleNamespace(course_id=102, college_id=2),
    ]
    db = MagicMock()
    with patch(
        "app.services.institution_wizard_service._list_institution_course_offerings",
        return_value=offerings,
    ), patch("app.services.institution_wizard_service.flag_modified"):
        changed = _refresh_draft_course_college_ids(db, draft, draft.payload)

    assert changed is True
    by_course = {c["course_id"]: c for c in draft.payload["courses"]}
    assert by_course[101]["college_id"] == 1
    assert by_course[101]["college_local_id"] == "law-local"
    assert by_course[102]["college_id"] == 2
    assert by_course[102]["college_local_id"] == "arts-local"


def test_refresh_draft_campuses_from_records_syncs_description():
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.services.institution_wizard_service import (
        _refresh_draft_campuses_from_records,
    )

    draft = SimpleNamespace(payload={"campuses": [{"id": 1, "name": "Main Campus"}]})
    campus = SimpleNamespace(
        id=1,
        name="Main Campus",
        location_id=10,
        campus_type_id=2,
        description="<p>Historic main quad.</p>",
        address="1 University Ave",
        country_id=1,
        state_id=2,
        zipcode="12345",
        phone_numbers=[],
        fax_numbers=[],
        email_addresses=[],
        web_links=[],
        is_residential=True,
        location=None,
        state=None,
        country=None,
    )

    with patch("app.services.institution_wizard_service.flag_modified"):
        changed = _refresh_draft_campuses_from_records(draft, [campus])

    assert changed is True
    assert draft.payload["campuses"][0]["description"] == "<p>Historic main quad.</p>"


def test_publish_without_campuses_is_valid():
    parsed = _validate_publish_payload(
        _base_payload(colleges=[MIN_COLLEGE]),
    )
    assert parsed.resolved_campuses == []
    assert parsed.colleges[0].name == "College of Arts"
    assert parsed.colleges[0].linked_campuses == []
