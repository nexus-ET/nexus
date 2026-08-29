from sqlalchemy import Boolean, Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class EducationSuperMajor(Base):
    """Top-level marketing cluster for catalog education majors."""

    __tablename__ = "education_super_majors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    code = Column(String(80), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    majors = relationship("EducationMajor", back_populates="super_major")
