from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class TargetProgram(Base):
    __tablename__ = "target_programs"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    courses = relationship(
        "TargetCourse",
        back_populates="program",
        cascade="all, delete-orphan",
    )
