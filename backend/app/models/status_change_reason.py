from sqlalchemy import Boolean, Column, Integer, String, Text

from app.db.database import Base


class StatusChangeReason(Base):
    __tablename__ = "status_change_reason"

    id = Column(Integer, primary_key=True, index=True)
    reason_type = Column(String(50), nullable=False, index=True)
    reason = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
