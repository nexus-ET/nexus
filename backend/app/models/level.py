from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class Level(Base):
    __tablename__ = "levels"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    education_degrees = relationship("EducationDegree", back_populates="level")
    programs = relationship("Program", back_populates="level")
