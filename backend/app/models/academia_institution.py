from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class CampusType(Base):
    __tablename__ = "campus_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)

    campuses = relationship("Campus", back_populates="campus_type_ref")


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    state_id = Column(Integer, ForeignKey("geography_states.id"), nullable=True, index=True)
    city_id = Column(Integer, ForeignKey("geography_cities.id"), nullable=True, index=True)
    zipcode = Column(String(10), nullable=True)
    address = Column(String(200), nullable=True)
    phone_numbers = Column(JSON, nullable=True)
    fax_numbers = Column(JSON, nullable=True)
    email_addresses = Column(JSON, nullable=True)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), nullable=True, index=True)
    dean_name = Column(String(255), nullable=True)
    institution_type = Column(String(80), nullable=True)
    company_affiliated = Column(Boolean, nullable=True)
    ranking_tier_global = Column(String(120), nullable=True)
    ad_promotion_flag = Column(Boolean, nullable=True)
    institution_web_url = Column(String(250), nullable=True)
    web_links = Column(JSON, nullable=True)
    currency_type = Column(String(10), nullable=False, default="USD")
    students_count = Column(String(250), nullable=True)
    accreditation_details = Column(Text, nullable=True)
    short_description = Column(String(2500), nullable=True)
    long_description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    publish_status = Column(String(20), nullable=False, default="pending", server_default="pending")
    last_publish_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_publish_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    country = relationship("Country", backref="institutions")
    state = relationship("GeographyState", backref="institutions")
    city = relationship("GeographyCity", backref="institutions")
    campuses = relationship("Campus", back_populates="institution", cascade="all, delete-orphan")
    colleges = relationship("College", back_populates="institution", cascade="all, delete-orphan")


class Campus(Base):
    __tablename__ = "campuses"

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("geography_cities.id"), nullable=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)
    state_id = Column(Integer, ForeignKey("geography_states.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    campus_type_id = Column(Integer, ForeignKey("campus_types.id"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    address = Column(String(200), nullable=True)
    zipcode = Column(String(10), nullable=True)
    phone_numbers = Column(JSON, nullable=True)
    fax_numbers = Column(JSON, nullable=True)
    email_addresses = Column(JSON, nullable=True)
    web_links = Column(JSON, nullable=True)
    is_residential = Column(Boolean, nullable=True)
    city = Column(String(120), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution = relationship("Institution", back_populates="campuses")
    location = relationship("GeographyCity", backref="campuses")
    country = relationship("Country", backref="campuses")
    state = relationship("GeographyState", backref="campuses")
    campus_type_ref = relationship("CampusType", back_populates="campuses")
    colleges = relationship("College", back_populates="campus", cascade="all, delete-orphan")


class College(Base):
    __tablename__ = "colleges"

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    campus_id = Column(Integer, ForeignKey("campuses.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), nullable=True)
    category = Column(String(64), nullable=True)
    dean_name = Column(String(255), nullable=True)
    web_url = Column(String(250), nullable=True)
    web_links = Column(JSON, nullable=True)
    phone_numbers = Column(JSON, nullable=True)
    email_addresses = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    institution = relationship("Institution", back_populates="colleges")
    campus = relationship("Campus", back_populates="colleges")
