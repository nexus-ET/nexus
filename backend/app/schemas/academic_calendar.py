from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IntakeType = Literal["Fixed", "Rolling"]
IntakeStatus = Literal["Draft", "Open", "Closed"]
EntityType = Literal["institution", "campus", "college"]


class TemplateIntakeConfig(BaseModel):
    term_name: str = Field(min_length=1, max_length=120)
    intake_type: IntakeType = "Fixed"
    expected_duration_months: int = Field(default=4, ge=1, le=24)


class GlobalAcademicTemplateRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    default_intake_configs: list[TemplateIntakeConfig]
    is_active: bool = True
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)

    @field_validator("default_intake_configs", mode="before")
    @classmethod
    def parse_configs(cls, value: object) -> list[TemplateIntakeConfig]:
        if not value:
            return []
        if isinstance(value, list):
            return [TemplateIntakeConfig.model_validate(item) for item in value]
        return []


class InstitutionIntakeRead(BaseModel):
    id: int
    institution_id: int
    campus_id: int | None = None
    entity_type: EntityType | None = None
    entity_id: int | None = None
    template_id: int | None = None
    parent_intake_id: int | None = None
    name: str
    term_name: str | None = None
    year: int | None = None
    intake_type: IntakeType = "Fixed"
    status: IntakeStatus = "Draft"
    intake_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    check_in_date: date | None = None
    orientation_date: date | None = None
    class_start_date: date | None = None
    level_ids: list[int] = Field(default_factory=list)
    is_overridden: bool = False
    cascade_to_children: bool = False
    is_active: bool = True
    sort_order: int = 0
    display_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InstitutionIntakeCreate(BaseModel):
    term_name: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=2000, le=2100)
    intake_type: IntakeType = "Fixed"
    status: IntakeStatus = "Draft"
    campus_id: int | None = None
    entity_type: EntityType | None = None
    entity_id: int | None = None
    template_id: int | None = None
    parent_intake_id: int | None = None
    intake_code: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    level_ids: list[int] = Field(default_factory=list)
    sort_order: int = 0

    @model_validator(mode="after")
    def validate_fixed_requirements(self) -> "InstitutionIntakeCreate":
        if self.intake_type == "Fixed":
            missing = [
                field
                for field, value in (
                    ("start_date", self.start_date),
                    ("end_date", self.end_date),
                    ("application_deadline", self.application_deadline),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"Fixed intakes require start_date, end_date, and application_deadline."
                )
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        if (
            self.application_deadline
            and self.end_date
            and self.application_deadline > self.end_date
        ):
            raise ValueError("application_deadline must be on or before end_date.")
        return self


class InstitutionIntakeUpdate(BaseModel):
    term_name: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=2000, le=2100)
    intake_type: IntakeType | None = None
    status: IntakeStatus | None = None
    campus_id: int | None = None
    intake_code: str | None = Field(default=None, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    check_in_date: date | None = None
    orientation_date: date | None = None
    class_start_date: date | None = None
    level_ids: list[int] | None = Field(default=None, min_length=1)
    sort_order: int | None = None
    is_active: bool | None = None
    cascade_to_children: bool | None = None

    @model_validator(mode="after")
    def validate_date_order(self) -> "InstitutionIntakeUpdate":
        validate_intake_date_sequence(
            application_deadline=self.application_deadline,
            orientation_date=self.orientation_date,
            class_start_date=self.class_start_date,
            check_in_date=self.check_in_date,
            require_mandatory=False,
        )
        return self


class IntakeSetupRequest(BaseModel):
    template_id: int = Field(ge=1)
    year: int | None = Field(default=None, ge=2000, le=2100)


class IntakeRolloverRequest(BaseModel):
    source_year: int | None = Field(default=None, ge=2000, le=2100)
    target_year: int | None = Field(default=None, ge=2000, le=2100)


class IntakeBulkUpdateItem(BaseModel):
    id: int = Field(ge=1)
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    status: IntakeStatus | None = None


class IntakeBulkUpdateRequest(BaseModel):
    items: list[IntakeBulkUpdateItem] = Field(min_length=1)


class InstitutionIntakeCalendarResponse(BaseModel):
    institution_id: int
    years: list[int]
    intakes_by_year: dict[int, list[InstitutionIntakeRead]]


def validate_intake_date_sequence(
    *,
    application_deadline: date | None,
    orientation_date: date | None,
    class_start_date: date | None,
    check_in_date: date | None = None,
    require_mandatory: bool = True,
) -> None:
    if require_mandatory:
        if application_deadline is None:
            raise ValueError("Application deadline is required.")
        if orientation_date is None:
            raise ValueError("Orientation date is required.")
        if check_in_date is None:
            raise ValueError("Check-in date is required.")
        if class_start_date is None:
            raise ValueError("Class start date is required.")
    # Chronological order:
    # Application Deadline < Orientation Date <= Check-in Date <= Class Start Date
    if application_deadline and orientation_date and application_deadline >= orientation_date:
        raise ValueError("Application Deadline must be earlier than Orientation Date.")
    if orientation_date and check_in_date and orientation_date > check_in_date:
        raise ValueError("Check-in Date cannot be earlier than Orientation Date.")
    if check_in_date and class_start_date and check_in_date > class_start_date:
        raise ValueError("Check-in Date cannot be later than Class Start Date.")


class IntakeEntityConfigureRequest(BaseModel):
    entity_type: EntityType
    entity_id: int = Field(ge=1)
    template_id: int = Field(ge=1)
    level_ids: list[int] = Field(min_length=1)
    term_names: list[str] | None = Field(default=None, min_length=1)
    year: int | None = Field(default=None, ge=2000, le=2100)
    cascade_to_children: bool = False

    @field_validator("level_ids")
    @classmethod
    def normalize_level_ids(cls, value: list[int]) -> list[int]:
        normalized = list(dict.fromkeys(value))
        if any(level_id < 1 for level_id in normalized):
            raise ValueError("Level IDs must be positive integers.")
        return normalized

    @field_validator("term_names")
    @classmethod
    def normalize_term_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(name.strip() for name in value if name.strip()))
        if not normalized:
            raise ValueError("At least one term name is required.")
        return normalized


class IntakeHierarchyEntityNode(BaseModel):
    entity_type: EntityType
    entity_id: int
    name: str
    parent_entity_type: EntityType | None = None
    parent_entity_id: int | None = None
    is_overridden: bool = False
    intake_count: int = 0
    children: list["IntakeHierarchyEntityNode"] = Field(default_factory=list)


IntakeHierarchyEntityNode.model_rebuild()


class InstitutionIntakeHierarchyResponse(BaseModel):
    institution_id: int
    institution_name: str
    root: IntakeHierarchyEntityNode


class CalendarIntakeAlertRead(BaseModel):
    id: int
    institution_id: int
    institution_name: str
    entity_type: EntityType
    entity_id: int
    entity_name: str
    term_name: str
    year: int
    class_start_date: date | None = None
    days_until_start: int | None = None
    alert_type: str = "missing_intake"
    alerted_at: str | None = None
    link_path: str | None = None
