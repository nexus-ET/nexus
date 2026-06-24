from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Any, Optional
from datetime import datetime
from enum import Enum

# 🎯 Match the database model naming and uppercase string values exactly
class LeadStage(str, Enum):
    AI_ACTIVE = "AI_ACTIVE"
    HANDOFF = "HANDOFF"
    ARCHIVE = "ARCHIVE"

class LeadChannel(str, Enum):
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    GOOGLE_ADS = "GOOGLE_ADS"
    OFFLINE = "OFFLINE"


class LeadSource(str, Enum):
    FACEBOOK_LEAD = "FACEBOOK_LEAD"
    INSTAGRAM_LEAD = "INSTAGRAM_LEAD"

class LeadBase(BaseModel):
    full_name: str
    # 🎯 Marked as Optional to prevent validation crashes since the DB allows nulls
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    channel: LeadChannel = LeadChannel.WHATSAPP
    source: Optional[LeadSource] = None
    preferred_country: Optional[str] = None
    budget_tier: Optional[str] = None
    test_scores: Optional[str] = None
    academic_summary: Optional[str] = None

class LeadCreate(LeadBase):
    pass

class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    channel: Optional[LeadChannel] = None
    source: Optional[LeadSource] = None
    preferred_country: Optional[str] = None
    budget_tier: Optional[str] = None
    test_scores: Optional[str] = None
    academic_summary: Optional[str] = None
    ml_conversion_score: Optional[float] = None
    is_human_locked: Optional[bool] = None
    stage: Optional[LeadStage] = None
    calendar_booking_id: Optional[str] = None
    audit_report_url: Optional[str] = None
    resolution_reason: Optional[str] = None

class LeadResponse(LeadBase):
    id: int
    stage: LeadStage
    is_human_locked: bool
    ml_conversion_score: float
    calendar_booking_id: Optional[str] = None
    audit_report_url: Optional[str] = None
    resolution_reason: Optional[str] = None
    additional_data: Optional[dict[str, Any]] = None
    meta_campaign_name: Optional[str] = None
    meta_form_id: Optional[str] = None
    meta_ad_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    # Allows Pydantic to read SQLAlchemy lazy-loaded attributes naturally
    model_config = ConfigDict(from_attributes=True)