from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.db.database import Base

JsonColumn = JSON().with_variant(JSONB, "postgresql")
# Use a separate type instance — MutableList.as_mutable() associates with the
# type object itself and would break shared JsonColumn dict/list fields.
MutableJsonList = MutableList.as_mutable(JSON().with_variant(JSONB, "postgresql"))


class InstitutionWizardDraft(Base):
    __tablename__ = "institution_wizard_drafts"

    id = Column(Integer, primary_key=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="Untitled Institution")
    status = Column(String(20), nullable=False, default="draft", index=True)
    current_step = Column(Integer, nullable=False, default=1)
    completed_steps = Column(JsonColumn, nullable=False, default=list)
    payload = Column(JsonColumn, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    institution = relationship("Institution", backref="wizard_drafts")


class InstitutionIntake(Base):
    __tablename__ = "institution_intakes"

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    campus_id = Column(Integer, ForeignKey("campuses.id"), nullable=True, index=True)
    entity_type = Column(String(20), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    template_id = Column(Integer, ForeignKey("global_academic_templates.id"), nullable=True, index=True)
    parent_intake_id = Column(Integer, ForeignKey("institution_intakes.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    term_name = Column(String(120), nullable=True)
    year = Column(Integer, nullable=True, index=True)
    intake_type = Column(String(20), nullable=False, default="Fixed")
    status = Column(String(20), nullable=False, default="Draft", index=True)
    intake_code = Column(String(50), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    application_deadline = Column(Date, nullable=True)
    check_in_date = Column(Date, nullable=True)
    orientation_date = Column(Date, nullable=True)
    class_start_date = Column(Date, nullable=True)
    level_ids = Column(MutableJsonList, nullable=False, default=list)
    is_overridden = Column(Boolean, default=False, nullable=False)
    cascade_to_children = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution = relationship("Institution", backref="intakes")
    campus = relationship("Campus", backref="intakes")
    template = relationship("GlobalAcademicTemplate", back_populates="institution_intakes")
    parent_intake = relationship("InstitutionIntake", remote_side=[id], backref="child_intakes")
    program_assignments = relationship(
        "ProgramIntakeAssignment",
        back_populates="institution_intake",
        cascade="all, delete-orphan",
    )


class InstitutionPicture(Base):
    __tablename__ = "institution_pictures"

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    campus_id = Column(Integer, ForeignKey("campuses.id"), nullable=True, index=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), nullable=True, index=True)
    url = Column(Text, nullable=False)
    # Stable R2/local object key. Multiple rows may share one storage_key (cascade links).
    storage_key = Column(String(500), nullable=True, index=True)
    caption = Column(String(255), nullable=True)
    picture_type = Column(String(40), nullable=False, default="gallery")
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution = relationship("Institution", backref="pictures")
    campus = relationship("Campus", backref="pictures")
    college = relationship("College", backref="pictures")


class InstitutionCourseOffering(Base):
    __tablename__ = "institution_course_offerings"
    __table_args__ = (
        Index(
            "ix_institution_course_offerings_inst_active_course",
            "institution_id",
            "is_active",
            "course_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    campus_id = Column(Integer, ForeignKey("campuses.id"), nullable=True, index=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), nullable=True, index=True)
    # Required FK. Program–institution links may point at a 1:1 program clone in
    # target_courses; hub course_count ignores those placeholders.
    course_id = Column(Integer, ForeignKey("target_courses.id"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution = relationship("Institution", backref="course_offerings")
    campus = relationship("Campus", backref="course_offerings")
    college = relationship("College", backref="course_offerings")
    course = relationship("TargetCourse", backref="institution_offerings")


class AcademiaAuditLog(Base):
    __tablename__ = "academia_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    action = Column(String(40), nullable=False, index=True)
    old_data = Column(JsonColumn, nullable=True)
    new_data = Column(JsonColumn, nullable=True)
    rollback_of_id = Column(Integer, ForeignKey("academia_audit_logs.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
