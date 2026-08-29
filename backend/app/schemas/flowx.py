"""Pydantic schemas for country-first FlowX."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

StageKey = Literal[
    "counselling",
    "college_finding",
    "document_submission",
    "tests",
    "admission_processing",
    "visa_processing",
    "predeparture_travel",
    "landing",
]
EnrollmentStatus = Literal["active", "paused", "completed", "dormant", "archived"]
KanbanStatus = Literal["todo", "in_progress", "in_review", "approved", "blocked"]
SlaStatus = Literal["on_track", "amber", "breached"]
AuditAction = Literal["waive_step", "add_custom_task", "fast_forward", "override_sla"]
TrackStatus = Literal["not_started", "in_progress", "completed", "blocked"]
TemplateOverrideAction = Literal["waive", "make_optional", "force_required", "clear"]
SubprocessLinkType = Literal["depends_on", "related"]


class FlowxTaskTemplateRead(BaseModel):
    id: UUID
    track_id: UUID
    stage_id: UUID | None = None
    stage_key: StageKey | None = None
    track_name: str | None = None
    track_label: str | None = None
    title: str
    description: str | None = None
    action_steps: list[str] = Field(default_factory=list)
    position_index: int
    sla_days: int = 7
    is_country_specific: bool = False
    auto_trigger_source: str | None = None
    is_active: bool = True
    is_optional: bool = False
    override_action: str | None = None
    override_reason: str | None = None
    link_count: int = 0
    parent_template_id: UUID | None = None
    master_template_id: UUID | None = None
    children: list["FlowxTaskTemplateRead"] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FlowxSubprocessLinkRead(BaseModel):
    id: UUID
    workflow_id: UUID
    from_template_id: UUID
    to_template_id: UUID
    from_title: str | None = None
    to_title: str | None = None
    link_type: SubprocessLinkType
    created_at: datetime | None = None


class FlowxEnrollmentLinkRead(BaseModel):
    """Country-workflow subprocess link resolved onto a student journey's tasks."""

    id: UUID
    workflow_id: UUID
    from_template_id: UUID
    to_template_id: UUID
    from_task_id: UUID | None = None
    to_task_id: UUID | None = None
    from_title: str | None = None
    to_title: str | None = None
    link_type: SubprocessLinkType
    created_at: datetime | None = None


class FlowxTrackTemplateRead(BaseModel):
    id: UUID
    stage_id: UUID
    track_name: str
    track_label: str
    position_index: int
    task_templates: list[FlowxTaskTemplateRead] = Field(default_factory=list)


class FlowxStageRead(BaseModel):
    id: UUID
    workflow_id: UUID
    stage_key: StageKey
    label: str
    position_index: int
    is_hidden: bool = False
    tracks: list[FlowxTrackTemplateRead] = Field(default_factory=list)
    bricks: list[FlowxTaskTemplateRead] = Field(default_factory=list)


class FlowxCountryWorkflowSummary(BaseModel):
    id: UUID
    country_iso2: str
    country_name: str
    name: str
    status: str
    stage_count: int = 0
    template_task_count: int = 0
    enrollment_count: int = 0
    institution_count: int = 0
    college_count: int = 0
    students_processed: int = 0
    students_in_process: int = 0
    updated_at: datetime | None = None


class FlowxCountryWorkflowDetail(BaseModel):
    id: UUID
    country_iso2: str
    country_name: str
    name: str
    status: str
    stages: list[FlowxStageRead] = Field(default_factory=list)
    links: list[FlowxSubprocessLinkRead] = Field(default_factory=list)
    unlinked_bricks: list[FlowxTaskTemplateRead] = Field(default_factory=list)
    enrollment_count: int = 0
    institution_count: int = 0
    college_count: int = 0
    students_processed: int = 0
    students_in_process: int = 0
    is_master: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlowxTemplateMoveRequest(BaseModel):
    target_stage_id: UUID
    position_index: int = 0
    track_name: str | None = None


class FlowxSubprocessLinkCreate(BaseModel):
    from_template_id: UUID
    to_template_id: UUID
    link_type: SubprocessLinkType = "depends_on"


class FlowxTemplateOverrideRequest(BaseModel):
    action: TemplateOverrideAction
    reason: str


class FlowxTemplateRelinkRequest(BaseModel):
    target_stage_id: UUID
    track_name: str | None = None
    position_index: int = 0


class FlowxTaskRead(BaseModel):
    id: UUID
    enrollment_track_id: UUID
    title: str
    description: str | None = None
    kanban_status: KanbanStatus
    position_index: int
    sla_due_at: datetime | None = None
    sla_status: SlaStatus
    progress_percentage: int = 0
    is_auto_added: bool = False
    is_optional: bool = False
    auto_trigger_source: str | None = None
    assigned_to: int | None = None
    action_steps: list[str] = Field(default_factory=list)
    checklist_state: dict | None = None
    # Matching country-workflow template (for nesting / sync).
    template_id: UUID | None = None
    parent_template_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlowxEnrollmentStageMeta(BaseModel):
    """Country-workflow stage row mirrored onto a student journey."""

    stage_key: StageKey
    label: str
    position_index: int
    is_hidden: bool = False


class FlowxEnrollmentTrackRead(BaseModel):
    id: UUID
    enrollment_id: UUID
    stage_key: StageKey
    track_name: str
    track_label: str
    position_index: int = 0
    track_status: TrackStatus
    progress_percentage: int
    tasks: list[FlowxTaskRead] = Field(default_factory=list)


class FlowxEnrollmentTrackMoveRequest(BaseModel):
    position_index: int = 0
    updated_at: datetime | None = None


class FlowxIntakeBookingRead(BaseModel):
    """Latest counselling booking context for Intake Session (sub-process 1.1)."""

    id: int | None = None
    lead_id: int | None = None
    candidate_name: str = "Candidate"
    status_definition_id: int | None = None
    status_stage_name: str | None = None
    status_category: str | None = None
    booking_status: str | None = None
    date_label: str | None = None
    time_label: str | None = None


class FlowxEnrollmentRead(BaseModel):
    id: UUID
    lead_id: int
    lead_name: str | None = None
    lead_phone: str | None = None
    preferred_country: str | None = None
    country_iso2: str
    country_name: str
    country_workflow_id: UUID
    institution_id: int | None = None
    institution_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    university_name: str | None = None
    campus_id: int | None = None
    campus_name: str | None = None
    level_id: int | None = None
    level_name: str | None = None
    qualification_program_id: int | None = None
    program_name: str | None = None
    intake_id: int | None = None
    intake_name: str | None = None
    pathway_type: str | None = None
    pathway_name: str | None = None
    portal_url: str | None = None
    portal_username: str | None = None
    portal_password_hint: str | None = None
    institutional_app_id: str | None = None
    application_status: str = "drafting"
    fee_status: str = "not_required"
    fee_amount: float | None = None
    fee_currency: str = "USD"
    internal_target_date: datetime | None = None
    official_deadline: datetime | None = None
    submitted_at: datetime | None = None
    current_stage_key: StageKey
    status: EnrollmentStatus
    sla_health: SlaStatus = "on_track"
    stages: list[FlowxEnrollmentStageMeta] = Field(default_factory=list)
    tracks: list[FlowxEnrollmentTrackRead] = Field(default_factory=list)
    links: list[FlowxEnrollmentLinkRead] = Field(default_factory=list)
    intake_booking: FlowxIntakeBookingRead | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlowxEnrollmentListItem(BaseModel):
    id: UUID
    lead_id: int
    lead_name: str
    country_iso2: str
    country_name: str
    institution_id: int | None = None
    institution_name: str | None = None
    college_id: int | None = None
    college_name: str | None = None
    university_name: str | None = None
    campus_name: str | None = None
    program_name: str | None = None
    intake_name: str | None = None
    pathway_name: str | None = None
    application_status: str = "drafting"
    current_stage_key: StageKey
    status: EnrollmentStatus
    sla_health: SlaStatus
    updated_at: datetime | None = None


class FlowxEnrollmentListResponse(BaseModel):
    items: list[FlowxEnrollmentListItem]
    total: int


class FlowxDestinationCollege(BaseModel):
    id: int
    name: str
    institution_id: int


class FlowxDestinationInstitution(BaseModel):
    id: int
    name: str
    state_id: int | None = None
    city_id: int | None = None
    colleges: list[FlowxDestinationCollege] = Field(default_factory=list)


class FlowxCountryDestinationsResponse(BaseModel):
    country_iso2: str
    institutions: list[FlowxDestinationInstitution] = Field(default_factory=list)


class FlowxGeographyItem(BaseModel):
    id: int
    name: str
    state_id: int | None = None


class FlowxCountryGeographyResponse(BaseModel):
    country_iso2: str
    country_id: int
    states: list[FlowxGeographyItem] = Field(default_factory=list)
    cities: list[FlowxGeographyItem] = Field(default_factory=list)


class FlowxJourneyTestSeedResponse(BaseModel):
    lead_id: int
    lead_name: str | None = None
    enrollments_cleared: int = 0
    academia_cleared: dict | None = None
    applications: list[dict] = Field(default_factory=list)
    total: int = 0


class FlowxJourneyTestResetResponse(BaseModel):
    lead_id: int
    lead_name: str | None = None
    enrollments_deleted: int = 0
    academia: dict = Field(default_factory=dict)


class FlowxBoardCard(BaseModel):
    enrollment_id: UUID
    lead_id: int
    lead_name: str
    country_iso2: str
    country_name: str
    institution_name: str | None = None
    college_name: str | None = None
    current_stage_key: StageKey
    status: EnrollmentStatus
    sla_health: SlaStatus


class FlowxBoardColumn(BaseModel):
    stage_key: StageKey
    label: str
    cards: list[FlowxBoardCard] = Field(default_factory=list)


class FlowxBoardResponse(BaseModel):
    country_iso2: str | None = None
    columns: list[FlowxBoardColumn]


class FlowxOpsBottleneck(BaseModel):
    country_iso2: str
    country_name: str
    stage_key: StageKey
    stage_label: str
    delayed_count: int
    at_risk_count: int = 0


class FlowxOpsCountryCard(BaseModel):
    country_iso2: str
    country_name: str
    active_applications: int = 0
    delayed_count: int = 0
    at_risk_count: int = 0
    on_track_count: int = 0
    students_processed: int = 0
    students_in_process: int = 0
    institution_count: int = 0
    college_count: int = 0
    top_stage_key: StageKey | None = None
    top_stage_label: str | None = None


class FlowxOpsOverviewResponse(BaseModel):
    total_active: int = 0
    total_delayed: int = 0
    total_at_risk: int = 0
    total_on_track: int = 0
    visas_in_process: int = 0
    landed_candidates: int = 0
    countries: list[FlowxOpsCountryCard] = Field(default_factory=list)
    bottlenecks: list[FlowxOpsBottleneck] = Field(default_factory=list)


class FlowxEnrollRequest(BaseModel):
    lead_id: int
    institution_id: int | None = None
    college_id: int | None = None
    campus_id: int | None = None
    level_id: int | None = None
    qualification_program_id: int | None = None
    intake_id: int | None = None
    pathway_type: str | None = None
    pathway_name: str | None = None
    custom_pathway_name: str | None = None
    portal_url: str | None = None
    portal_username: str | None = None
    portal_password_hint: str | None = None
    institutional_app_id: str | None = None
    application_status: str | None = "drafting"
    fee_status: str | None = "not_required"
    fee_amount: float | None = None
    fee_currency: str | None = "USD"
    internal_target_date: datetime | None = None
    official_deadline: datetime | None = None


class FlowxPathwayRead(BaseModel):
    id: UUID
    pathway_type: str
    pathway_name: str
    is_custom: bool = False


class FlowxPathwayCreate(BaseModel):
    pathway_type: str
    pathway_name: str


class FlowxLookupItem(BaseModel):
    id: int | str
    name: str
    code: str | None = None
    extra: dict | None = None


class FlowxApplicationLookupsResponse(BaseModel):
    campuses: list[FlowxLookupItem] = Field(default_factory=list)
    colleges: list[FlowxLookupItem] = Field(default_factory=list)
    levels: list[FlowxLookupItem] = Field(default_factory=list)
    programs: list[FlowxLookupItem] = Field(default_factory=list)
    intakes: list[FlowxLookupItem] = Field(default_factory=list)


class FlowxStageUpdate(BaseModel):
    current_stage_key: StageKey
    updated_at: datetime | None = None


class FlowxTaskMoveRequest(BaseModel):
    kanban_status: KanbanStatus
    position_index: int = 0
    updated_at: datetime | None = None


class FlowxTaskReorderRequest(BaseModel):
    """Reorder a child process within its parent sub-process (track)."""

    position_index: int = 0
    updated_at: datetime | None = None


class FlowxTaskChecklistUpdate(BaseModel):
    """Persist activity checklist checkmarks + admin confirmation on a journey task."""

    checked: list[bool] = Field(default_factory=list)
    confirmed_complete: bool = False
    steps: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class FlowxTaskCreate(BaseModel):
    title: str
    description: str | None = None
    kanban_status: KanbanStatus = "todo"
    sla_due_at: datetime | None = None
    assigned_to: int | None = None


class FlowxOverrideRequest(BaseModel):
    action_type: AuditAction
    target_entity: str
    reason: str
    evidence_url: str | None = None
    track_name: str | None = None
    stage_key: StageKey | None = None
    title: str | None = None
    description: str | None = None


class FlowxAuditLogRead(BaseModel):
    id: UUID
    enrollment_id: UUID
    actor_id: int | None = None
    action_type: str
    target_entity: str
    reason: str
    evidence_url: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class FlowxTaskTemplateCreate(BaseModel):
    title: str
    description: str | None = None
    action_steps: list[str] = Field(default_factory=list)
    sla_days: int = 7
    parent_template_id: UUID | None = None


class FlowxTaskTemplateRenameRequest(BaseModel):
    """Update sub-process title and/or short definition (description). At least one required."""

    title: str | None = None
    description: str | None = None
    action_steps: list[str] | None = None


class FlowxProcessLabelUpdateRequest(BaseModel):
    stage_key: StageKey
    label: str


class FlowxProcessLabelUpdateResponse(BaseModel):
    stage_key: StageKey
    label: str
    countries_updated: int
    stages_updated: int


class FlowxWorkflowRuleCreate(BaseModel):
    rule_name: str
    trigger_condition: dict
    action_payload: dict
    is_active: bool = True


class FlowxWorkflowRuleRead(BaseModel):
    id: UUID
    rule_name: str
    trigger_condition: dict
    action_payload: dict
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
