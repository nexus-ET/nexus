from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import StatusChangeReasonRead


class AgentConfigBase(BaseModel):
    system_prompt: str = Field(min_length=1)
    ai_model: str = Field(min_length=1, max_length=100)
    escalation_threshold: int = Field(ge=0, le=100)
    keywords_trigger: str = Field(min_length=1, max_length=500)
    is_active: bool = True


class AgentConfigRead(AgentConfigBase):
    id: int
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class AgentConfigUpdate(AgentConfigBase):
    pass


class StaffMemberRead(BaseModel):
    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    role_label: str
    is_active: bool = True
    lead_count: int = 0
    creation_reason: int | None = None
    creation_date: datetime | None = None
    deactivation_reason: int | None = None
    deactivation_date: datetime | None = None
    activation_reason: int | None = None
    activation_date: datetime | None = None
    deactivation_reason_detail: StatusChangeReasonRead | None = None

    class Config:
        from_attributes = True
