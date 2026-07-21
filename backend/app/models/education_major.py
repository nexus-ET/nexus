import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class EducationMajor(Base):
    """Major / discipline under a qualification program (LPMC: child of Program)."""

    __tablename__ = "education_majors"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=True, index=True)
    label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id"), nullable=True, index=True
    )
    is_other = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    color = Column(String(7), nullable=True)

    program = relationship("Program", back_populates="education_majors")
    level_links = relationship(
        "EducationMajorLevel",
        backref="education_major",
        cascade="all, delete-orphan",
    )
    education_courses = relationship(
        "EducationCourse",
        back_populates="education_major",
        cascade="all, delete-orphan",
    )
