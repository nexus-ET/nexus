from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.academia_hub import InstitutionProfileTextFields
from app.schemas.contact_entry import (
    CollegeWebLinkListFields,
    ContactListFields,
    EmailContactListMixin,
    FaxContactListFields,
    InstitutionWebLinkListFields,
    OptionalEmailContactListMixin,
    OptionalPhoneContactListMixin,
    PhoneContactListMixin,
    WebLinkListFields,
)


WIZARD_STEPS = [
    "institution",
    "campus",
    "colleges",
    "courses",
    "intakes",
    "pictures",
]


class WizardInstitutionStep(
    OptionalPhoneContactListMixin,
    OptionalEmailContactListMixin,
    FaxContactListFields,
    InstitutionWebLinkListFields,
    InstitutionProfileTextFields,
    BaseModel,
):
    name: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    dean_name: str | None = Field(default=None, max_length=255)
    country_id: int | None = None
    state_id: int | None = None
    city_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=200)
    institution_type_id: int | None = None
    company_affiliated: bool | None = None
    ranking_tier_global: str | None = Field(default=None, max_length=120)
    ad_promotion_flag: bool | None = None
    currency_type: str = Field(default="USD", max_length=10)
    students_count: str | None = Field(default=None, max_length=250)
    accreditation_details: str | None = Field(default=None, max_length=2500)
    short_description: str | None = Field(default=None, max_length=2500)
    long_description: str | None = Field(default=None, max_length=5000)


class WizardCampusStep(
    OptionalPhoneContactListMixin,
    OptionalEmailContactListMixin,
    FaxContactListFields,
    WebLinkListFields,
    BaseModel,
):
    id: int | None = None
    name: str = Field(min_length=1, max_length=250)
    location_id: int
    institution_id: int | None = None
    campus_type_id: int
    description: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=200)
    country_id: int | None = None
    state_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    is_residential: bool | None = None


class WizardCampusSyncStep(ContactListFields, FaxContactListFields, WebLinkListFields, BaseModel):
    """Lenient campus payload used while syncing in-progress wizard drafts."""

    id: int | None = None
    name: str = Field(min_length=1, max_length=250)
    location_id: int
    institution_id: int | None = None
    campus_type_id: int
    description: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=200)
    country_id: int | None = None
    state_id: int | None = None
    zipcode: str | None = Field(default=None, max_length=10)
    is_residential: bool | None = None


class WizardPayload(BaseModel):
    institution: WizardInstitutionStep | None = None
    campus: WizardCampusStep | None = None
    campuses: list[WizardCampusStep] = Field(default_factory=list)
    colleges: list[WizardCollegeItem] = Field(default_factory=list)
    courses: list[WizardCourseOfferingItem] = Field(default_factory=list)
    college_academic_overrides: list[str] = Field(default_factory=list)
    intakes: list[WizardIntakeItem] = Field(default_factory=list)
    pictures: list[WizardPictureItem] = Field(default_factory=list)
    college_picture_overrides: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_campus(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        campuses = data.get("campuses")
        legacy = data.get("campus")
        if (not campuses) and legacy:
            data = {**data, "campuses": [legacy] if legacy else []}
        return data

    @property
    def resolved_campuses(self) -> list[WizardCampusStep]:
        if self.campuses:
            return self.campuses
        if self.campus:
            return [self.campus]
        return []


class WizardCollegeCampusLink(BaseModel):
    campus_local_id: str | None = Field(default=None, max_length=64)
    campus_id: int | None = None
    name: str = Field(default="", max_length=255)
    address: str | None = Field(default=None, max_length=200)
    location_label: str | None = Field(default=None, max_length=255)


class WizardCollegeItem(
    PhoneContactListMixin,
    EmailContactListMixin,
    FaxContactListFields,
    CollegeWebLinkListFields,
    BaseModel,
):
    id: int | None = None
    local_id: str | None = Field(default=None, max_length=64)
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default="College", max_length=64)
    dean_name: str | None = Field(default=None, max_length=255)
    campus_id: int | None = None
    linked_campuses: list[WizardCollegeCampusLink] = Field(default_factory=list)
    long_description: str | None = Field(default=None, max_length=5000)
    accreditation: str | None = Field(default=None, max_length=500)


class WizardCollegeSyncItem(ContactListFields, FaxContactListFields, CollegeWebLinkListFields, BaseModel):
    """Lenient college payload used while syncing in-progress wizard drafts."""

    id: int | None = None
    local_id: str | None = Field(default=None, max_length=64)
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default="College", max_length=64)
    dean_name: str | None = Field(default=None, max_length=255)
    campus_id: int | None = None
    linked_campuses: list[WizardCollegeCampusLink] = Field(default_factory=list)
    long_description: str | None = Field(default=None, max_length=5000)
    accreditation: str | None = Field(default=None, max_length=500)


class WizardCourseOfferingItem(BaseModel):
    course_id: int | None = None
    campus_id: int | None = None
    college_id: int | None = None
    college_local_id: str | None = Field(default=None, max_length=64)
    level_id: int | None = Field(default=None, ge=1)
    program_id: int | None = None
    major_id: int | None = Field(default=None, ge=1)
    course_code: str | None = Field(default=None, max_length=50)
    credits: float | None = Field(default=None, ge=0, le=30)
    level: str | None = Field(default=None, max_length=40)
    syllabus_outline: str | None = Field(default=None, max_length=5000)
    display_label: str | None = Field(default=None, max_length=500)
    program_url: str | None = Field(default=None, max_length=2048)


class WizardIntakeItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    intake_code: str | None = Field(default=None, max_length=50)
    campus_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    enrollment_cap: int | None = Field(default=None, ge=1, le=100000)


class WizardPictureItem(BaseModel):
    id: int | None = None
    url: str = Field(min_length=1)
    caption: str | None = Field(default=None, max_length=255)
    campus_id: int | None = None
    college_id: int | None = None
    college_local_id: str | None = Field(default=None, max_length=80)
    storage_key: str | None = Field(default=None, max_length=500)
    picture_type: str = Field(default="gallery", max_length=40)
    file_name: str | None = Field(default=None, max_length=255)
    file_type: str | None = Field(default=None, max_length=100)
    file_size: int | None = Field(default=None, ge=0)


class WizardDraftCreate(BaseModel):
    title: str | None = Field(default="Untitled Institution", max_length=255)


class WizardDraftUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    current_step: int | None = Field(default=None, ge=1, le=6)
    completed_steps: list[int] | None = None
    payload: WizardPayload | None = None


class WizardDraftRead(BaseModel):
    id: int
    created_by_user_id: int
    institution_id: int | None = None
    title: str
    status: str
    current_step: int
    completed_steps: list[int]
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WizardStepSaveRequest(BaseModel):
    step: int = Field(ge=1, le=6)
    # Step 1 sends an institution object; steps 2–6 send arrays of step items.
    data: dict[str, Any] | list[Any]
    mark_complete: bool = True


class AcademiaAuditLogRead(BaseModel):
    id: int
    user_id: int | None = None
    entity_type: str
    entity_id: int
    action: str
    old_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    rollback_of_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InstitutionIntakeRead(BaseModel):
    id: int
    institution_id: int
    campus_id: int | None = None
    template_id: int | None = None
    parent_intake_id: int | None = None
    name: str
    term_name: str | None = None
    year: int | None = None
    intake_type: str = "Fixed"
    status: str = "Draft"
    intake_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    is_active: bool = True
    sort_order: int = 0
    display_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InstitutionPictureRead(BaseModel):
    id: int
    institution_id: int
    campus_id: int | None = None
    college_id: int | None = None
    storage_key: str | None = None
    url: str
    caption: str | None = None
    picture_type: str = "gallery"
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)
