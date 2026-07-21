from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.db.database import Base

JsonColumn = JSON().with_variant(JSONB, "postgresql")


class GlobalAcademicTemplate(Base):
    __tablename__ = "global_academic_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    default_intake_configs = Column(JsonColumn, nullable=False, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution_intakes = relationship("InstitutionIntake", back_populates="template")


class ProgramIntakeAssignment(Base):
    __tablename__ = "program_intake_assignments"
    __table_args__ = (
        UniqueConstraint("program_id", "institution_intake_id", name="uq_program_intake"),
    )

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_intake_id = Column(
        Integer, ForeignKey("institution_intakes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    program = relationship("Program", back_populates="intake_assignments")
    institution_intake = relationship("InstitutionIntake", back_populates="program_assignments")
