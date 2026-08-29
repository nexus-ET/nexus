from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AgreementMethod = Literal["in_session", "phone", "email", "parent_present"]
DeclineOutcome = Literal["follow_up", "not_interested", "deferred"]
PaymentMode = Literal["upi", "neft_imps", "rtgs", "card", "cash", "cheque", "other"]
PaymentPlan = Literal["full", "advance", "fixed_cost", "fixed_emi"]
RemainingPaymentPlan = Literal["full", "parts"]
MilestoneSplit = Literal["equal", "fixed"]

AGREEMENT_METHODS: tuple[str, ...] = ("in_session", "phone", "email", "parent_present")
DECLINE_OUTCOMES: tuple[str, ...] = ("follow_up", "not_interested", "deferred")
PAYMENT_MODES: tuple[str, ...] = ("upi", "neft_imps", "rtgs", "card", "cash", "cheque", "other")
PAYMENT_PLANS: tuple[str, ...] = ("full", "advance", "fixed_cost", "fixed_emi")


class PaymentMilestone(BaseModel):
    id: str = Field(default="", max_length=40)
    due_date: date | None = None
    paid_on: date | None = None
    amount_inr: float = Field(default=0, ge=0)
    payment_mode: PaymentMode | None = None
    payment_received: bool | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, value: object) -> str:
        return str(value or "").strip()[:40]

    @field_validator("payment_mode", mode="before")
    @classmethod
    def empty_payment_mode_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("due_date", "paid_on", mode="before")
    @classmethod
    def empty_milestone_date_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class StudentRegistrationData(BaseModel):
    agrees_to_register: bool | None = None
    agreement_date: date | None = None
    agreement_method: AgreementMethod | None = None
    parent_consent: bool | None = None
    assigned_account_manager_id: int | None = Field(default=None, ge=1)
    package_id: str | None = Field(default=None, max_length=64)
    service_ids: list[str] = Field(default_factory=list, max_length=40)
    bill_now: bool = False
    notes: str = Field(default="", max_length=500)
    decline_outcome: DeclineOutcome | None = None
    invoice_id: str | None = Field(default=None, max_length=80)
    invoice_number: str | None = Field(default=None, max_length=80)
    invoice_status: str | None = Field(default=None, max_length=20)
    invoice_amount_inr: float | None = None
    invoice_date: date | None = None
    payment_received: bool = False
    payment_confirmed_at: datetime | None = None
    payment_mode: PaymentMode | None = None
    total_payable_inr: float | None = None
    amount_paid_inr: float | None = None
    payment_due_date: date | None = None
    payment_paid_on: date | None = None
    next_payment_date: date | None = None
    payment_plan: PaymentPlan | None = None
    remaining_plan: RemainingPaymentPlan | None = None
    milestone_split: MilestoneSplit | None = None
    milestone_count: int | None = Field(default=None, ge=2, le=3)
    milestone_fixed_amount_inr: float | None = None
    payment_milestones: list[PaymentMilestone] = Field(default_factory=list, max_length=12)

    @field_validator(
        "invoice_id",
        "invoice_number",
        "invoice_status",
        "payment_mode",
        "payment_plan",
        "remaining_plan",
        "milestone_split",
        mode="before",
    )
    @classmethod
    def empty_invoice_text_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("package_id", mode="before")
    @classmethod
    def empty_package_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "agreement_date",
        "invoice_date",
        "next_payment_date",
        "payment_due_date",
        "payment_paid_on",
        mode="before",
    )
    @classmethod
    def empty_date_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def coerce_notes(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("service_ids", mode="before")
    @classmethod
    def normalize_service_ids(cls, value: object) -> list[str]:
        if not value:
            return []
        if not isinstance(value, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token[:64])
        return out


class StudentRegistrationSaveRequest(BaseModel):
    registration: StudentRegistrationData


class StudentRegistrationResponse(BaseModel):
    students_master_id: int | None = None
    booking_id: int | None = None
    lead_id: int | None = None
    status_definition_id: int | None = None
    status_stage_name: str | None = None
    future_status_definition_id: int | None = None
    future_status_stage_name: str | None = None
    completes_as_status_definition_id: int | None = None
    completes_as_status_stage_name: str | None = None
    registration: StudentRegistrationData
    saved_at: datetime | None = None
    registration_complete: bool = False

    model_config = ConfigDict(from_attributes=True)
