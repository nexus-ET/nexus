from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.orm import relationship

from app.db.database import Base


class ProgramEducationMajorMapping(Base):
    """Links a qualification program to a catalog education major and optional sub-major."""

    __tablename__ = "program_education_major_mappings"
    __table_args__ = (
        Index(
            "uq_pem_program_major_sub",
            "program_id",
            "education_major_id",
            "education_sub_major_id",
            unique=True,
            postgresql_where=text("education_sub_major_id IS NOT NULL"),
        ),
        Index(
            "uq_pem_program_major_null_sub",
            "program_id",
            "education_major_id",
            unique=True,
            postgresql_where=text("education_sub_major_id IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(
        Integer,
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    education_major_id = Column(
        Integer,
        ForeignKey("education_majors.id", ondelete="CASCADE"),
        nullable=False,
    )
    education_sub_major_id = Column(
        Integer,
        ForeignKey("education_sub_majors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    program = relationship("Program", backref="education_major_mappings")
    education_major = relationship("EducationMajor", backref="program_mappings")
    education_sub_major = relationship("EducationSubMajor")
