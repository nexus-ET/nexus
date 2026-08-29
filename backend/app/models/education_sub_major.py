from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.database import Base


class EducationSubMajor(Base):
    """Sub-department / concentration under a catalog education major."""

    __tablename__ = "education_sub_majors"
    __table_args__ = (
        UniqueConstraint(
            "major_id",
            "name",
            name="uq_education_sub_majors_major_id_name",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    sub_major_description = Column(Text, nullable=True)
    major_id = Column(
        Integer,
        ForeignKey("education_majors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    major = relationship("EducationMajor", back_populates="sub_majors")
