from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.database import Base


class FullTimeStudyYear(Base):
    """Lookup for Full-Time Study Years used on profiles and leads.

    The same ``code`` may exist under multiple levels (e.g. 12/13 for both
    Foundational and Integrated Degree).
    """

    __tablename__ = "full_time_study_years"
    __table_args__ = (
        UniqueConstraint("code", "level_id", name="uq_full_time_study_years_code_level_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    level_id = Column(Integer, ForeignKey("levels.id"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    level = relationship("Level")
