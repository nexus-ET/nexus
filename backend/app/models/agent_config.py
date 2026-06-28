from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.db.database import Base


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    system_prompt = Column(Text, nullable=False)
    ai_model = Column(String(100), nullable=False, default="ollama:llama3.1")
    escalation_threshold = Column(Integer, nullable=False, default=70)
    keywords_trigger = Column(String(500), nullable=False, default="human,advisor,agent,talk to,person")
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
