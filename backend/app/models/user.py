from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    phone_number = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    admin_role_id = Column(Integer, ForeignKey("admin_roles.id"), nullable=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True, default=1)
    fcm_tokens = Column(Text, nullable=True)

    creation_reason = Column(Integer, ForeignKey("status_change_reason.id"), nullable=True)
    creation_date = Column(DateTime, nullable=True)
    deactivation_reason = Column(Integer, ForeignKey("status_change_reason.id"), nullable=True)
    deactivation_date = Column(DateTime, nullable=True)
    activation_reason = Column(Integer, ForeignKey("status_change_reason.id"), nullable=True)
    activation_date = Column(DateTime, nullable=True)

    admin_role_ref = relationship("AdminRole", foreign_keys=[admin_role_id])
    creation_reason_ref = relationship(
        "StatusChangeReason",
        foreign_keys=[creation_reason],
    )
    deactivation_reason_ref = relationship(
        "StatusChangeReason",
        foreign_keys=[deactivation_reason],
    )
    activation_reason_ref = relationship(
        "StatusChangeReason",
        foreign_keys=[activation_reason],
    )
    clients = relationship("Client", back_populates="owner")
