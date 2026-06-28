from sqlalchemy import Boolean, Column, Integer, String

from app.db.database import Base


class EducationDegree(Base):
    __tablename__ = "education_degrees"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    is_other = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
