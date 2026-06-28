from sqlalchemy import Boolean, Column, Integer, String

from app.db.database import Base


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    iso2 = Column(String(2), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    dial_code = Column(String(6), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
