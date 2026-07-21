import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class ProgramEducationMajorMapping(Base):
    """Links a qualification program to a catalog education major."""

    __tablename__ = "program_education_major_mappings"
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "education_major_id",
            name="uq_program_education_major_mappings_program_major",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    education_major_id = Column(
        Integer,
        ForeignKey("education_majors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    program = relationship("Program", backref="education_major_mappings")
    education_major = relationship("EducationMajor", backref="program_mappings")
