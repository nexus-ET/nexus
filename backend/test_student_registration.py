from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.schemas.student_registration import StudentRegistrationData
from app.services.student_registration_service import (
    age_from_dob,
    status_id_for_registration,
    validate_registration_decision,
)
from app.services.status_definition_service import (
    STATUS_COUNSELLING_CANCELLED,
    STATUS_COUNSELLING_DEFERRED,
    STATUS_COUNSELLING_FOLLOW_UP,
    STATUS_COUNSELLING_PROSPECT_QUALIFIED,
)


def test_age_from_dob_under_18():
    today = date(2026, 8, 12)
    assert age_from_dob(date(2010, 8, 13), today) == 15
    assert age_from_dob(date(2008, 8, 12), today) == 18
    assert age_from_dob(None, today) is None


def test_status_id_for_yes_requires_payment():
    unpaid = StudentRegistrationData(agrees_to_register=True)
    assert status_id_for_registration(unpaid) is None
    paid = StudentRegistrationData(
        agrees_to_register=True,
        payment_received=True,
        invoice_id="inv_1",
        invoice_number="INV-1",
        invoice_status="issued",
        payment_mode="upi",
        total_payable_inr=11800,
        amount_paid_inr=11800,
    )
    assert status_id_for_registration(paid) == STATUS_COUNSELLING_PROSPECT_QUALIFIED


def test_status_id_for_decline_outcomes():
    assert (
        status_id_for_registration(
            StudentRegistrationData(agrees_to_register=False, decline_outcome="follow_up")
        )
        == STATUS_COUNSELLING_FOLLOW_UP
    )
    assert (
        status_id_for_registration(
            StudentRegistrationData(agrees_to_register=False, decline_outcome="not_interested")
        )
        == STATUS_COUNSELLING_CANCELLED
    )
    assert (
        status_id_for_registration(
            StudentRegistrationData(agrees_to_register=False, decline_outcome="deferred")
        )
        == STATUS_COUNSELLING_DEFERRED
    )
    assert status_id_for_registration(StudentRegistrationData()) is None


def test_validate_yes_requires_core_fields():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException) as exc:
        validate_registration_decision(
            StudentRegistrationData(agrees_to_register=True),
            date_of_birth=date(2000, 1, 1),
            today=today,
        )
    assert exc.value.status_code == 400


def test_validate_yes_requires_parent_consent_under_18():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException) as exc:
        validate_registration_decision(
            StudentRegistrationData(
                agrees_to_register=True,
                agreement_date=today,
                agreement_method="in_session",
                assigned_account_manager_id=3,
                parent_consent=False,
            ),
            date_of_birth=today - timedelta(days=365 * 16),
            today=today,
        )
    assert "consent" in str(exc.value.detail).lower()


def test_validate_payment_requires_issued_invoice():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException) as exc:
        validate_registration_decision(
            StudentRegistrationData(
                agrees_to_register=True,
                agreement_date=today,
                agreement_method="in_session",
                assigned_account_manager_id=3,
                payment_received=True,
            ),
            date_of_birth=date(2000, 1, 1),
            today=today,
        )
    assert "invoice" in str(exc.value.detail).lower()


def test_validate_no_requires_decline_outcome():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException):
        validate_registration_decision(
            StudentRegistrationData(agrees_to_register=False),
            date_of_birth=None,
            today=today,
        )


def test_validate_yes_with_issued_invoice_and_payment():
    today = date(2026, 8, 12)
    result = validate_registration_decision(
        StudentRegistrationData(
            agrees_to_register=True,
            agreement_date=today,
            agreement_method="in_session",
            assigned_account_manager_id=3,
            payment_received=True,
            invoice_id="inv_1",
            invoice_number="INV-1",
            invoice_status="issued",
            payment_mode="upi",
            payment_plan="full",
            total_payable_inr=11800,
            amount_paid_inr=11800,
        ),
        date_of_birth=date(2000, 1, 1),
        today=today,
    )
    assert result.payment_received is True
    assert result.payment_confirmed_at is not None
    assert result.payment_mode == "upi"
    assert result.amount_paid_inr == 11800
    assert result.payment_plan == "full"
    assert result.payment_milestones == []


def test_validate_partial_payment_requires_next_date():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException) as exc:
        validate_registration_decision(
            StudentRegistrationData(
                agrees_to_register=True,
                agreement_date=today,
                agreement_method="in_session",
                assigned_account_manager_id=3,
                payment_received=True,
                invoice_id="inv_1",
                invoice_number="INV-1",
                invoice_status="issued",
                payment_mode="upi",
                payment_plan="advance",
                total_payable_inr=11800,
                amount_paid_inr=5000,
            ),
            date_of_birth=date(2000, 1, 1),
            today=today,
        )
    assert "next payment" in str(exc.value.detail).lower()


def test_validate_partial_payment_with_milestones():
    today = date(2026, 8, 12)
    result = validate_registration_decision(
        StudentRegistrationData(
            agrees_to_register=True,
            agreement_date=today,
            agreement_method="in_session",
            assigned_account_manager_id=3,
            payment_received=True,
            invoice_id="inv_1",
            invoice_number="INV-1",
            invoice_status="issued",
            payment_mode="neft_imps",
            total_payable_inr=11800,
            amount_paid_inr=5000,
            next_payment_date=today,
            payment_plan="fixed_emi",
            milestone_count=2,
            payment_milestones=[
                {
                    "id": "ms_1",
                    "due_date": today,
                    "amount_inr": 3400,
                    "payment_received": False,
                },
                {
                    "id": "ms_2",
                    "due_date": today + timedelta(days=30),
                    "amount_inr": 3400,
                    "payment_received": None,
                },
            ],
        ),
        date_of_birth=date(2000, 1, 1),
        today=today,
    )
    assert result.payment_plan == "fixed_emi"
    assert result.remaining_plan == "parts"
    assert result.milestone_split == "equal"
    assert len(result.payment_milestones) == 2
    assert result.payment_milestones[0].payment_received is False


def test_validate_keeps_payment_plan_draft_before_received():
    today = date(2026, 8, 12)
    result = validate_registration_decision(
        StudentRegistrationData(
            agrees_to_register=True,
            agreement_date=today,
            agreement_method="in_session",
            assigned_account_manager_id=3,
            payment_received=False,
            invoice_id="inv_1",
            invoice_number="EDT-26-27-0001",
            invoice_status="issued",
            payment_mode="upi",
            total_payable_inr=30000,
            amount_paid_inr=10000,
            payment_plan="fixed_emi",
            milestone_count=3,
            payment_milestones=[
                {"id": "ms_1", "due_date": today + timedelta(days=30), "amount_inr": 10000},
                {"id": "ms_2", "due_date": today + timedelta(days=60), "amount_inr": 10000},
            ],
        ),
        date_of_birth=date(2000, 1, 1),
        today=today,
    )
    assert result.payment_received is False
    assert result.payment_plan == "fixed_emi"
    assert result.milestone_count == 3
    assert result.amount_paid_inr == 10000
    assert len(result.payment_milestones) == 2

    today = date(2026, 8, 12)
    result = validate_registration_decision(
        StudentRegistrationData(
            agrees_to_register=True,
            agreement_date=today,
            agreement_method="in_session",
            assigned_account_manager_id=3,
            payment_received=True,
            invoice_id="inv_1",
            invoice_number="INV-1",
            invoice_status="issued",
            payment_mode="upi",
            payment_plan="full",
            total_payable_inr=11800,
            amount_paid_inr=11800,
        ),
        date_of_birth=date(2000, 1, 1),
        today=today,
    )
    assert result.payment_plan == "full"
    assert result.payment_milestones == []


def test_validate_legacy_remaining_plan_maps_to_advance():
    today = date(2026, 8, 12)
    result = validate_registration_decision(
        StudentRegistrationData(
            agrees_to_register=True,
            agreement_date=today,
            agreement_method="in_session",
            assigned_account_manager_id=3,
            payment_received=True,
            invoice_id="inv_1",
            invoice_number="INV-1",
            invoice_status="issued",
            payment_mode="cash",
            total_payable_inr=10000,
            amount_paid_inr=4000,
            next_payment_date=today,
            remaining_plan="full",
            payment_milestones=[
                {"id": "ms_1", "due_date": today, "amount_inr": 6000, "payment_received": None},
            ],
        ),
        date_of_birth=date(2000, 1, 1),
        today=today,
    )
    assert result.payment_plan == "advance"
    assert result.remaining_plan == "full"


def test_validate_milestones_require_chronological_due_dates():
    today = date(2026, 8, 12)
    with pytest.raises(HTTPException) as exc:
        validate_registration_decision(
            StudentRegistrationData(
                agrees_to_register=True,
                agreement_date=today,
                agreement_method="in_session",
                assigned_account_manager_id=3,
                payment_received=True,
                invoice_id="inv_1",
                invoice_number="INV-1",
                invoice_status="issued",
                payment_mode="upi",
                payment_plan="fixed_emi",
                milestone_count=3,
                total_payable_inr=9000,
                amount_paid_inr=3000,
                next_payment_date=today,
                payment_milestones=[
                    {"id": "ms_1", "due_date": today + timedelta(days=60), "amount_inr": 2000},
                    {"id": "ms_2", "due_date": today + timedelta(days=30), "amount_inr": 2000},
                    {"id": "ms_3", "due_date": today + timedelta(days=90), "amount_inr": 2000},
                ],
            ),
            date_of_birth=date(2000, 1, 1),
            today=today,
        )
    assert "chronological" in str(exc.value.detail).lower()
