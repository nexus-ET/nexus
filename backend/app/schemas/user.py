import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal, Optional

StatusChangeReasonType = Literal["Create", "Activate", "Deactivate"]

PHONE_LOCAL_PATTERN = re.compile(r"^\d{10}$")
PHONE_REQUIREMENTS_MESSAGE = "Mobile number must be exactly 10 numeric digits."
PHONE_COUNTRY_CODE_MESSAGE = "Please select a country code."
PHONE_INCOMPLETE_MESSAGE = (
    "Mobile number must include a country code followed by exactly 10 numeric digits."
)


def validate_password_strength(password: str | None) -> str | None:
    if password is None:
        return None
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    has_lower = re.search(r"[a-z]", password) is not None
    has_upper = re.search(r"[A-Z]", password) is not None
    has_digit = re.search(r"\d", password) is not None
    has_special = re.search(r"[^A-Za-z0-9]", password) is not None
    if not (has_lower and has_upper and has_digit and has_special):
        raise ValueError(
            "Password must include uppercase, lowercase, numbers, and special characters."
        )
    return password


def validate_phone_number(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    if cleaned.startswith("+"):
        digits = re.sub(r"\D", "", cleaned[1:])
    else:
        digits = re.sub(r"\D", "", cleaned)
        if PHONE_LOCAL_PATTERN.match(digits):
            raise ValueError(PHONE_COUNTRY_CODE_MESSAGE)
        raise ValueError(PHONE_REQUIREMENTS_MESSAGE)

    if len(digits) < 11:
        raise ValueError(PHONE_INCOMPLETE_MESSAGE)

    local = digits[-10:]
    country = digits[:-10]
    if not PHONE_LOCAL_PATTERN.match(local):
        raise ValueError(PHONE_REQUIREMENTS_MESSAGE)
    if not country:
        raise ValueError(PHONE_COUNTRY_CODE_MESSAGE)

    return f"+{country}{local}"


class StatusChangeReasonRead(BaseModel):
    id: int
    reason_type: str
    reason: str
    description: str

    class Config:
        from_attributes = True


class AdminRoleRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_superuser: bool = False
    is_active: bool = True
    sort_order: int = 0

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    is_superuser: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    admin_role_id: Optional[int] = None
    admin_role: Optional[AdminRoleRead] = None
    role: Optional[str] = None
    creation_reason: Optional[int] = None
    creation_date: Optional[datetime] = None
    deactivation_reason: Optional[int] = None
    deactivation_date: Optional[datetime] = None
    activation_reason: Optional[int] = None
    activation_date: Optional[datetime] = None
    creation_reason_detail: Optional[StatusChangeReasonRead] = None
    deactivation_reason_detail: Optional[StatusChangeReasonRead] = None
    activation_reason_detail: Optional[StatusChangeReasonRead] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    phone_number: str = Field(min_length=1, max_length=50)
    is_active: Optional[bool] = True
    admin_role_id: int

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_phone_number(value) or value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value) or value

    @field_validator("admin_role_id")
    @classmethod
    def validate_admin_role_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("A valid admin role must be selected.")
        return value


class User(UserBase):
    id: int

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    admin_role_id: Optional[int] = None
    password: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return validate_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return validate_password_strength(value)

    @field_validator("admin_role_id")
    @classmethod
    def validate_admin_role_id(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValueError("A valid admin role must be selected.")
        return value


class UserStatusChange(BaseModel):
    status_change_reason_id: int

    @field_validator("status_change_reason_id")
    @classmethod
    def validate_reason_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("A valid status change reason must be selected.")
        return value


class UserProfileUpdate(BaseModel):
    phone_number: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return validate_phone_number(value)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_strength(value) or value
