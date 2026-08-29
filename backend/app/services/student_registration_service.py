from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.lead import Lead
from app.models.students_master import StudentsMaster
from app.schemas.student_registration import (
    StudentRegistrationData,
    StudentRegistrationSaveRequest,
)
from app.services.student_aspirations_service import (
    find_students_master_for_booking,
    resolve_students_master_for_booking,
)
from app.services.status_definition_service import (
    STATUS_COUNSELLING_CANCELLED,
    STATUS_COUNSELLING_DEFERRED,
    STATUS_COUNSELLING_FOLLOW_UP,
    STATUS_COUNSELLING_PROSPECT_QUALIFIED,
    STATUS_DOCUMENT_IN_PREPARATION,
)
from app.utils.timezone import office_today, utc_now


def age_from_dob(dob: date | None, today: date) -> int | None:
    if dob is None:
        return None
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def status_id_for_registration(registration: StudentRegistrationData) -> int | None:
    if registration.agrees_to_register is True:
        if registration.payment_received is True:
            return STATUS_COUNSELLING_PROSPECT_QUALIFIED
        return None
    if registration.agrees_to_register is False:
        if registration.decline_outcome == "follow_up":
            return STATUS_COUNSELLING_FOLLOW_UP
        if registration.decline_outcome == "not_interested":
            return STATUS_COUNSELLING_CANCELLED
        if registration.decline_outcome == "deferred":
            return STATUS_COUNSELLING_DEFERRED
        return None
    return None


def _money(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(float(value) + 1e-12, 2)


def _resolve_payment_plan(registration: StudentRegistrationData) -> str | None:
    if registration.payment_plan:
        return registration.payment_plan
    # Older registration JSON used remaining_plan / milestone_split.
    if registration.remaining_plan == "full":
        return "advance"
    if registration.remaining_plan == "parts":
        return "fixed_cost" if registration.milestone_split == "fixed" else "fixed_emi"
    return None


def _legacy_remaining_fields(plan: str | None) -> dict:
    if plan == "advance":
        return {"remaining_plan": "full", "milestone_split": None}
    if plan == "fixed_cost":
        return {"remaining_plan": "parts", "milestone_split": "fixed"}
    if plan == "fixed_emi":
        return {"remaining_plan": "parts", "milestone_split": "equal"}
    return {"remaining_plan": None, "milestone_split": None}


def _validate_payment_collection(registration: StudentRegistrationData, *, today: date) -> None:
    if not registration.payment_mode:
        raise HTTPException(status_code=400, detail="Select the payment mode.")
    total = _money(registration.total_payable_inr)
    if registration.total_payable_inr is None or total <= 0:
        raise HTTPException(status_code=400, detail="Total payable is required.")
    paid = _money(registration.amount_paid_inr)
    if registration.amount_paid_inr is None or paid <= 0:
        raise HTTPException(status_code=400, detail="Enter the amount paid.")
    if paid > total + 0.009:
        raise HTTPException(status_code=400, detail="Amount paid cannot exceed total payable.")
    balance = _money(max(0.0, total - paid))
    plan = _resolve_payment_plan(registration)
    if not plan:
        raise HTTPException(status_code=400, detail="Select a payment plan.")
    if plan == "full":
        if balance >= 0.01:
            raise HTTPException(
                status_code=400,
                detail="Full payment must cover the total payable.",
            )
        return
    if plan == "advance" and balance < 0.01:
        raise HTTPException(
            status_code=400,
            detail="Part payment must be less than the total payable.",
        )
    if balance < 0.01:
        return
    if not registration.next_payment_date:
        raise HTTPException(status_code=400, detail="Select the next payment date.")
    if registration.next_payment_date < today:
        raise HTTPException(status_code=400, detail="Next payment date cannot be in the past.")
    if plan == "fixed_emi":
        count = registration.milestone_count or 0
        if count < 2 or count > 3:
            raise HTTPException(
                status_code=400,
                detail="Use between 2 and 3 remaining instalments.",
            )
    if plan == "fixed_cost":
        fixed = _money(registration.milestone_fixed_amount_inr)
        if registration.milestone_fixed_amount_inr is None or fixed < 0.01:
            raise HTTPException(status_code=400, detail="Enter a fixed instalment amount.")
    milestones = registration.payment_milestones or []
    if not milestones:
        raise HTTPException(status_code=400, detail="Define the remaining payment schedule.")
    if plan in {"fixed_cost", "fixed_emi"} and len(milestones) > 3:
        raise HTTPException(
            status_code=400,
            detail="Use at most 3 part payments for this plan.",
        )
    if any(not row.due_date for row in milestones):
        raise HTTPException(status_code=400, detail="Each remaining payment needs a due date.")
    if any(row.due_date and row.due_date < today for row in milestones):
        raise HTTPException(status_code=400, detail="Payment due dates cannot be in the past.")
    for index in range(1, len(milestones)):
        previous = milestones[index - 1].due_date
        current = milestones[index].due_date
        if previous and current and current < previous:
            raise HTTPException(
                status_code=400,
                detail="Payment due dates must be in chronological order.",
            )
    scheduled = _money(sum(_money(row.amount_inr) for row in milestones))
    if abs(scheduled - balance) > 0.05:
        raise HTTPException(
            status_code=400,
            detail="Remaining payment milestones must add up to the balance.",
        )


def validate_registration_decision(
    registration: StudentRegistrationData,
    *,
    date_of_birth: date | None,
    today: date,
) -> StudentRegistrationData:
    notes = (registration.notes or "").strip()
    if registration.agrees_to_register is True:
        if not registration.agreement_date:
            raise HTTPException(status_code=400, detail="Agreement date is required.")
        if registration.agreement_date > today:
            raise HTTPException(status_code=400, detail="Agreement date cannot be in the future.")
        if not registration.agreement_method:
            raise HTTPException(status_code=400, detail="Select how the student agreed to register.")
        if not registration.assigned_account_manager_id:
            raise HTTPException(
                status_code=400,
                detail="Assigned account manager is required when the student agrees to register.",
            )
        age = age_from_dob(date_of_birth, today)
        if age is not None and age < 18 and registration.parent_consent is not True:
            raise HTTPException(
                status_code=400,
                detail="Parent or guardian consent is required for students under 18.",
            )
        payment_received = registration.payment_received is True
        payment_confirmed_at = registration.payment_confirmed_at
        if payment_received:
            invoice_status = (registration.invoice_status or "").strip().lower()
            if invoice_status != "issued":
                raise HTTPException(
                    status_code=400,
                    detail="Payment can only be confirmed against an issued invoice.",
                )
            if not (registration.invoice_id or registration.invoice_number):
                raise HTTPException(
                    status_code=400,
                    detail="Select the issued invoice before confirming payment.",
                )
            _validate_payment_collection(registration, today=today)
            if payment_confirmed_at is None:
                payment_confirmed_at = utc_now()
        else:
            payment_confirmed_at = None
        total = _money(registration.total_payable_inr)
        paid_amount = _money(registration.amount_paid_inr)
        balance = _money(max(0.0, total - paid_amount))
        plan = _resolve_payment_plan(registration)
        has_payment_draft = bool(
            plan
            or registration.payment_mode
            or registration.amount_paid_inr is not None
            or registration.payment_milestones
        )
        # Keep payment-plan drafts even before Payment Received is confirmed,
        # so EMI / instalment selections survive agreement-only saves.
        if payment_received:
            legacy = _legacy_remaining_fields(plan if balance >= 0.01 else None)
            return registration.model_copy(
                update={
                    "notes": notes,
                    "decline_outcome": None,
                    "payment_received": True,
                    "payment_confirmed_at": payment_confirmed_at,
                    "payment_mode": registration.payment_mode,
                    "total_payable_inr": registration.total_payable_inr,
                    "amount_paid_inr": registration.amount_paid_inr,
                    "payment_due_date": registration.payment_due_date,
                    "payment_paid_on": registration.payment_paid_on,
                    "next_payment_date": registration.next_payment_date
                    if balance >= 0.01
                    else None,
                    "payment_plan": plan,
                    "remaining_plan": legacy["remaining_plan"],
                    "milestone_split": legacy["milestone_split"],
                    "milestone_count": registration.milestone_count
                    if balance >= 0.01 and plan == "fixed_emi"
                    else None,
                    "milestone_fixed_amount_inr": registration.milestone_fixed_amount_inr
                    if balance >= 0.01 and plan == "fixed_cost"
                    else None,
                    "payment_milestones": registration.payment_milestones
                    if balance >= 0.01
                    else [],
                }
            )
        legacy = _legacy_remaining_fields(plan if has_payment_draft and balance >= 0.01 else None)
        return registration.model_copy(
            update={
                "notes": notes,
                "decline_outcome": None,
                "payment_received": False,
                "payment_confirmed_at": None,
                "payment_mode": registration.payment_mode if has_payment_draft else None,
                "total_payable_inr": registration.total_payable_inr if has_payment_draft else None,
                "amount_paid_inr": registration.amount_paid_inr if has_payment_draft else None,
                "payment_due_date": registration.payment_due_date if has_payment_draft else None,
                "payment_paid_on": registration.payment_paid_on if has_payment_draft else None,
                "next_payment_date": registration.next_payment_date
                if has_payment_draft and balance >= 0.01
                else None,
                "payment_plan": plan if has_payment_draft else None,
                "remaining_plan": legacy["remaining_plan"],
                "milestone_split": legacy["milestone_split"],
                "milestone_count": registration.milestone_count
                if has_payment_draft and plan == "fixed_emi"
                else None,
                "milestone_fixed_amount_inr": registration.milestone_fixed_amount_inr
                if has_payment_draft and plan == "fixed_cost"
                else None,
                "payment_milestones": registration.payment_milestones if has_payment_draft else [],
            }
        )

    if registration.agrees_to_register is False:
        if not registration.decline_outcome:
            raise HTTPException(
                status_code=400,
                detail="Select Follow-up, Not interested, or Deferred when the student does not register.",
            )
        return registration.model_copy(update={"notes": notes})

    return registration.model_copy(update={"notes": notes})


def _stage_name(db: Session, status_id: int | None) -> str | None:
    if not status_id:
        return None
    from app.models.status_definition import StatusDefinition

    row = db.query(StatusDefinition).filter(StatusDefinition.id == status_id).first()
    return row.stage_name if row else None


def _serialize_registration(
    db: Session,
    record: StudentsMaster | None,
    *,
    booking_id: int | None = None,
    lead: Lead | None = None,
    stage_name: str | None = None,
) -> dict:
    raw = record.registration_data if record and isinstance(record.registration_data, dict) else {}
    registration = StudentRegistrationData.model_validate(raw or {})
    status_id = lead.status_definition_id if lead else None
    complete = (
        registration.agrees_to_register is True
        and registration.payment_received is True
        and status_id == STATUS_COUNSELLING_PROSPECT_QUALIFIED
    ) or (status_id is not None and status_id >= STATUS_DOCUMENT_IN_PREPARATION)
    return {
        "students_master_id": record.id if record else None,
        "booking_id": booking_id,
        "lead_id": lead.id if lead else (record.lead_id if record else None),
        "status_definition_id": status_id,
        "status_stage_name": stage_name,
        "completes_as_status_definition_id": STATUS_COUNSELLING_PROSPECT_QUALIFIED,
        "completes_as_status_stage_name": _stage_name(db, STATUS_COUNSELLING_PROSPECT_QUALIFIED)
        or "Counselling: Prospect Qualified",
        "future_status_definition_id": STATUS_DOCUMENT_IN_PREPARATION,
        "future_status_stage_name": _stage_name(db, STATUS_DOCUMENT_IN_PREPARATION)
        or "Document: In Preparation",
        "registration": registration,
        "saved_at": record.updated_at if record else None,
        "registration_complete": complete,
    }


def get_booking_registration(db: Session, booking, lead: Lead | None) -> dict:
    from app.models.status_definition import StatusDefinition

    record = find_students_master_for_booking(db, booking, lead)
    stage_name = None
    if lead and lead.status_definition_id:
        definition = (
            db.query(StatusDefinition)
            .filter(StatusDefinition.id == lead.status_definition_id)
            .first()
        )
        stage_name = definition.stage_name if definition else None
    return _serialize_registration(
        db,
        record,
        booking_id=booking.id,
        lead=lead,
        stage_name=stage_name,
    )


def save_booking_registration(
    db: Session,
    booking,
    lead: Lead | None,
    user_id: int,
    payload: StudentRegistrationSaveRequest,
    *,
    commit: bool = False,
) -> tuple[StudentsMaster, StudentRegistrationData]:
    today = office_today(db)
    record = resolve_students_master_for_booking(
        db,
        booking,
        lead,
        updated_by_user_id=user_id,
    )
    registration = validate_registration_decision(
        payload.registration,
        date_of_birth=record.date_of_birth,
        today=today,
    )
    record.registration_data = registration.model_dump(mode="json")
    flag_modified(record, "registration_data")
    record.updated_by_user_id = user_id
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()
    return record, registration
