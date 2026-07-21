from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class CourseEducationMajorMapping(Base):
    """Links an education course to one or more catalog education majors."""

    __tablename__ = "course_education_major_mappings"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "education_major_id",
            name="uq_course_education_major_mappings_course_major",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(
        Integer,
        ForeignKey("education_courses.id", ondelete="CASCADE"),
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

    course = relationship("EducationCourse", back_populates="education_major_mappings")
    education_major = relationship("EducationMajor", backref="course_mappings")
