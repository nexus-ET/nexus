from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SettingValueType = Literal["text", "number", "boolean", "time", "working_days", "timezone", "select"]


class SettingOption(BaseModel):
    value: str
    label: str


class DynamicSettingOut(BaseModel):
    key: str
    value: str
    updated_at: datetime | None = None
    updated_by_first_name: str | None = None
    updated_by_last_name: str | None = None
    label: str
    value_type: SettingValueType | str = "text"
    description: str = ""
    options: list[SettingOption] | None = None


class BusinessTimezoneResponse(BaseModel):
    timezone: str
    label: str


class WhatsAppOutreachConfigResponse(BaseModel):
    provider: str | None = None
    business_phone_number: str | None = None
    phone_number_id: str | None = None
    outreach_template: str | None = None
    ready: bool = False


class BusinessEmailDomainResponse(BaseModel):
    business_id: int
    email_domain: str | None = None


class DynamicSettingsResponse(BaseModel):
    settings: list[DynamicSettingOut]


class DynamicSettingUpdateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=0)


class BusinessProfileOut(BaseModel):
    business_id: int
    business_name: str
    business_domain: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    address_line3: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    office_phone_number: str | None = None
    office_mobile_number: str | None = None
    web_url: str | None = None
    email_domain: str | None = None
    has_logo: bool = False
    logo_url: str | None = None
    updated_at: datetime | None = None


class BusinessProfileUpdateRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_domain: str | None = Field(default=None, max_length=255)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    address_line3: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    zip_code: str | None = Field(default=None, max_length=30)
    office_phone_number: str | None = Field(default=None, max_length=50)
    office_mobile_number: str | None = Field(default=None, max_length=50)
    web_url: str | None = Field(default=None, max_length=500)
    email_domain: str | None = Field(default=None, max_length=255)


class PublicHolidayEntry(BaseModel):
    date: str
    name: str | None = None
    label: str
    is_private: bool


class PublicHolidaysResponse(BaseModel):
    holidays: list[PublicHolidayEntry]
    updated_at: datetime | None = None
    updated_by_first_name: str | None = None
    updated_by_last_name: str | None = None


class PublicHolidaySaveRequest(BaseModel):
    date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    name: str | None = Field(default=None, max_length=100)


class PublicHolidayRemoveRequest(BaseModel):
    date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PublicHolidayToggleRequest(BaseModel):
    date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PublicHolidayBulkSaveRequest(BaseModel):
    dates: list[str] = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=100)


class PublicHolidayBulkRemoveRequest(BaseModel):
    dates: list[str] = Field(min_length=1, max_length=100)
