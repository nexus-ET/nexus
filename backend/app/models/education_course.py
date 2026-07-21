from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class EducationCourse(Base):
    """Academic framework course linked directly to a qualification program."""

    __tablename__ = "education_courses"

    id = Column(Integer, primary_key=True, index=True)
    education_major_id = Column(
        Integer, ForeignKey("education_majors.id"), nullable=True, index=True
    )
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True)
    level_id = Column(Integer, ForeignKey("levels.id"), nullable=True, index=True)
    code = Column(String(50), unique=True, nullable=True, index=True)
    label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    course_level = Column(String(40), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    education_major = relationship("EducationMajor", back_populates="education_courses")
    program = relationship("Program", back_populates="education_courses")
    level = relationship("Level")
    education_major_mappings = relationship(
        "CourseEducationMajorMapping",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
