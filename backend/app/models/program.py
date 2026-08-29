from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class Program(Base):
    """Framework qualification program under a level (LPMC: child of Level)."""

    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    level_id = Column(Integer, ForeignKey("levels.id"), nullable=False, index=True)
    description = Column(Text, nullable=True)
    program_url = Column(String(2048), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    level = relationship("Level", back_populates="programs")
    education_majors = relationship(
        "EducationMajor",
        back_populates="program",
        cascade="all, delete-orphan",
    )
    majors = relationship(
        "TargetProgram",
        back_populates="program",
        cascade="all, delete-orphan",
    )
    education_courses = relationship(
        "EducationCourse",
        back_populates="program",
        cascade="all, delete-orphan",
    )
    intake_assignments = relationship(
        "ProgramIntakeAssignment",
        back_populates="program",
        cascade="all, delete-orphan",
    )
