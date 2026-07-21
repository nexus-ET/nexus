from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class GeographyState(Base):
    __tablename__ = "geography_states"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    region_code = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    country = relationship("Country", backref="states")
    cities = relationship("GeographyCity", back_populates="state", cascade="all, delete-orphan")


class GeographyCity(Base):
    __tablename__ = "geography_cities"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    state_id = Column(Integer, ForeignKey("geography_states.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    time_zone = Column(String(64), nullable=True)
    postal_code_prefix = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    country = relationship("Country", backref="cities")
    state = relationship("GeographyState", back_populates="cities")
