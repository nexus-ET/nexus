from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class TargetCourse(Base):
    __tablename__ = "target_courses"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, ForeignKey("target_programs.id"), nullable=False, index=True)
    education_major_id = Column(
        Integer, ForeignKey("education_majors.id"), nullable=True, index=True
    )
    qualification_program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True
    )
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    level = Column(String(40), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    program = relationship("TargetProgram", back_populates="courses")
    education_major = relationship("EducationMajor")
    qualification_program = relationship("Program")