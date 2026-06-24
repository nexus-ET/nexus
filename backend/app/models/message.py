# app/models/message.py
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Point directly to your working app/database.py file
from app.db.database import Base

if TYPE_CHECKING:
    from app.models.lead import Lead 

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    sender: Mapped[str] = mapped_column(String, nullable=False) 
    text: Mapped[str] = mapped_column(String, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 📁 ATTACHMENT ASSET ENGINE SUPPORT
    media_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 🔗 RELATIONSHIPS
    lead = relationship("Lead", back_populates="messages")