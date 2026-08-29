"""FlowX country-first overseas education process models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

JOURNEY_STAGES = (
    "counselling",
    "college_finding",
    "document_submission",
    "tests",
    "admission_processing",
    "visa_processing",
    "predeparture_travel",
    "landing",
)

JOURNEY_STAGE_LABELS = {
    "counselling": "Counselling",
    "college_finding": "College finding",
    "document_submission": "Document readiness",
    "tests": "Tests",
    "admission_processing": "Admission processing",
    "visa_processing": "Visa processing",
    "predeparture_travel": "Pre-departure & travel",
    "landing": "Landing",
}

# Default track per stage (parallel workstreams mapped onto the journey).
STAGE_DEFAULT_TRACKS: dict[str, list[str]] = {
    "counselling": ["counselling_desk"],
    "college_finding": ["college_finder"],
    "document_submission": ["paperwork_studio"],
    "tests": ["exam_desk"],
    "admission_processing": ["college_finder", "paperwork_studio"],
    "visa_processing": ["visa_money"],
    "predeparture_travel": ["visa_money", "paperwork_studio"],
    "landing": ["visa_money"],
}

TRACK_LABELS = {
    "counselling_desk": "Counselling Desk",
    "college_finder": "College Finder",
    "paperwork_studio": "Paperwork Studio",
    "exam_desk": "Exam Desk",
    "visa_money": "Visa & Money",
}

ENROLLMENT_STATUSES = ("active", "paused", "completed", "dormant", "archived")
TRACK_STATUSES = ("not_started", "in_progress", "completed", "blocked")
KANBAN_STATUSES = ("todo", "in_progress", "in_review", "approved", "blocked")
SLA_STATUSES = ("on_track", "amber", "breached")
AUDIT_ACTIONS = ("waive_step", "add_custom_task", "fast_forward", "override_sla")
WORKFLOW_STATUSES = ("active", "archived")


class FlowxCountryWorkflow(Base):
    __tablename__ = "flowx_country_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_iso2: Mapped[str] = mapped_column(String(2), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stages = relationship(
        "FlowxStage", back_populates="workflow", cascade="all, delete-orphan", order_by="FlowxStage.position_index"
    )
    enrollments = relationship("FlowxEnrollment", back_populates="workflow")


class FlowxStage(Base):
    __tablename__ = "flowx_stages"
    __table_args__ = (UniqueConstraint("workflow_id", "stage_key", name="uq_flowx_stages_workflow_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_country_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workflow = relationship("FlowxCountryWorkflow", back_populates="stages")
    tracks = relationship(
        "FlowxTrack", back_populates="stage", cascade="all, delete-orphan", order_by="FlowxTrack.position_index"
    )


class FlowxTrack(Base):
    """Template track under a country workflow stage."""

    __tablename__ = "flowx_tracks"
    __table_args__ = (UniqueConstraint("stage_id", "track_name", name="uq_flowx_tracks_stage_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_stages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    track_name: Mapped[str] = mapped_column(String(64), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stage = relationship("FlowxStage", back_populates="tracks")
    task_templates = relationship(
        "FlowxTaskTemplate",
        back_populates="track",
        cascade="all, delete-orphan",
        order_by="FlowxTaskTemplate.position_index",
    )


class FlowxTaskTemplate(Base):
    __tablename__ = "flowx_task_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    is_country_specific: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_trigger_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overridden_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flowx_task_templates.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # When set, this country brick is a synced copy of a Master Workflow template.
    master_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flowx_task_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    track = relationship("FlowxTrack", back_populates="task_templates")
    parent = relationship(
        "FlowxTaskTemplate",
        remote_side="FlowxTaskTemplate.id",
        foreign_keys=[parent_template_id],
        uselist=False,
    )


class FlowxSubprocessLink(Base):
    """Dependency / related link between two sub-process (task template) bricks."""

    __tablename__ = "flowx_subprocess_links"
    __table_args__ = (
        UniqueConstraint("from_template_id", "to_template_id", "link_type", name="uq_flowx_subprocess_link"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_country_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_task_templates.id", ondelete="CASCADE"), nullable=False
    )
    to_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_task_templates.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="depends_on")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlowxPathwayRegistry(Base):
    """Self-learning registry of application pathway names by type."""

    __tablename__ = "flowx_pathway_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pathway_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pathway_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlowxEnrollment(Base):
    """Student application journey on a country workflow (optionally college-scoped)."""

    __tablename__ = "flowx_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country_workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flowx_country_workflows.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    institution_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    college_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("colleges.id", ondelete="SET NULL"), nullable=True, index=True
    )
    university_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campus_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    level_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("levels.id", ondelete="SET NULL"), nullable=True
    )
    qualification_program_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intake_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("institution_intakes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pathway_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pathway_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portal_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portal_password_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    institutional_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_status: Mapped[str] = mapped_column(String(64), nullable=False, default="drafting")
    fee_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_required")
    fee_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    internal_target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage_key: Mapped[str] = mapped_column(String(64), nullable=False, default="counselling")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workflow = relationship("FlowxCountryWorkflow", back_populates="enrollments")
    tracks = relationship(
        "FlowxEnrollmentTrack", back_populates="enrollment", cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "FlowxAuditLog", back_populates="enrollment", cascade="all, delete-orphan"
    )


class FlowxEnrollmentTrack(Base):
    __tablename__ = "flowx_enrollment_tracks"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "stage_key", "track_name", name="uq_flowx_enroll_track"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    track_name: Mapped[str] = mapped_column(String(64), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    enrollment = relationship("FlowxEnrollment", back_populates="tracks")
    tasks = relationship(
        "FlowxTask", back_populates="enrollment_track", cascade="all, delete-orphan"
    )


class FlowxTask(Base):
    __tablename__ = "flowx_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_track_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flowx_enrollment_tracks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kanban_status: Mapped[str] = mapped_column(String(32), nullable=False, default="todo")
    position_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_status: Mapped[str] = mapped_column(String(32), nullable=False, default="on_track")
    is_auto_added: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_trigger_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Activity checklist progress: checked flags + admin confirmation.
    checklist_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    enrollment_track = relationship("FlowxEnrollmentTrack", back_populates="tasks")


class FlowxAuditLog(Base):
    __tablename__ = "flowx_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flowx_enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    enrollment = relationship("FlowxEnrollment", back_populates="audit_logs")


class FlowxWorkflowRule(Base):
    __tablename__ = "flowx_workflow_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
