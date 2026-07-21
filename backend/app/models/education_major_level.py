from sqlalchemy import Column, ForeignKey, Integer

from app.db.database import Base


class EducationMajorLevel(Base):
    __tablename__ = "education_major_levels"

    education_major_id = Column(
        Integer,
        ForeignKey("education_majors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    level_id = Column(
        Integer,
        ForeignKey("levels.id", ondelete="CASCADE"),
        primary_key=True,
    )
