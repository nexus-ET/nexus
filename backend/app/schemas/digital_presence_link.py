from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DigitalPlatform(str, Enum):
    GITHUB = "GITHUB"
    LINKEDIN = "LINKEDIN"
    PERSONAL_PORTFOLIO = "PERSONAL_PORTFOLIO"
    GOOGLE_SCHOLAR = "GOOGLE_SCHOLAR"
    RESEARCHGATE = "RESEARCHGATE"
    BEHANCE = "BEHANCE"
    DRIBBBLE = "DRIBBBLE"
    KAGGLE = "KAGGLE"
    DEVPOST = "DEVPOST"
    OTHER = "OTHER"


class DigitalPresenceCategory(str, Enum):
    TECHNICAL = "TECHNICAL"
    PROFESSIONAL = "PROFESSIONAL"
    ACADEMIC = "ACADEMIC"
    CREATIVE = "CREATIVE"
    OTHER = "OTHER"


PLATFORM_LABELS: dict[DigitalPlatform, str] = {
    DigitalPlatform.GITHUB: "GitHub",
    DigitalPlatform.LINKEDIN: "LinkedIn",
    DigitalPlatform.PERSONAL_PORTFOLIO: "Personal Portfolio",
    DigitalPlatform.GOOGLE_SCHOLAR: "Google Scholar",
    DigitalPlatform.RESEARCHGATE: "ResearchGate",
    DigitalPlatform.BEHANCE: "Behance",
    DigitalPlatform.DRIBBBLE: "Dribbble",
    DigitalPlatform.KAGGLE: "Kaggle",
    DigitalPlatform.DEVPOST: "Devpost",
    DigitalPlatform.OTHER: "Other",
}

CATEGORY_LABELS: dict[DigitalPresenceCategory, str] = {
    DigitalPresenceCategory.TECHNICAL: "Technical",
    DigitalPresenceCategory.PROFESSIONAL: "Professional",
    DigitalPresenceCategory.ACADEMIC: "Academic",
    DigitalPresenceCategory.CREATIVE: "Creative",
    DigitalPresenceCategory.OTHER: "Other",
}

PLATFORM_DEFAULT_CATEGORY: dict[DigitalPlatform, DigitalPresenceCategory] = {
    DigitalPlatform.GITHUB: DigitalPresenceCategory.TECHNICAL,
    DigitalPlatform.KAGGLE: DigitalPresenceCategory.TECHNICAL,
    DigitalPlatform.DEVPOST: DigitalPresenceCategory.TECHNICAL,
    DigitalPlatform.LINKEDIN: DigitalPresenceCategory.PROFESSIONAL,
    DigitalPlatform.PERSONAL_PORTFOLIO: DigitalPresenceCategory.PROFESSIONAL,
    DigitalPlatform.GOOGLE_SCHOLAR: DigitalPresenceCategory.ACADEMIC,
    DigitalPlatform.RESEARCHGATE: DigitalPresenceCategory.ACADEMIC,
    DigitalPlatform.BEHANCE: DigitalPresenceCategory.CREATIVE,
    DigitalPlatform.DRIBBBLE: DigitalPresenceCategory.CREATIVE,
    DigitalPlatform.OTHER: DigitalPresenceCategory.OTHER,
}

CATEGORY_SORT_ORDER: dict[DigitalPresenceCategory, int] = {
    DigitalPresenceCategory.TECHNICAL: 1,
    DigitalPresenceCategory.PROFESSIONAL: 2,
    DigitalPresenceCategory.ACADEMIC: 3,
    DigitalPresenceCategory.CREATIVE: 4,
    DigitalPresenceCategory.OTHER: 5,
}

PLATFORM_SORT_ORDER: dict[DigitalPlatform, int] = {
    DigitalPlatform.GITHUB: 1,
    DigitalPlatform.LINKEDIN: 2,
    DigitalPlatform.PERSONAL_PORTFOLIO: 3,
    DigitalPlatform.GOOGLE_SCHOLAR: 4,
    DigitalPlatform.RESEARCHGATE: 5,
    DigitalPlatform.BEHANCE: 6,
    DigitalPlatform.DRIBBBLE: 7,
    DigitalPlatform.KAGGLE: 8,
    DigitalPlatform.DEVPOST: 9,
    DigitalPlatform.OTHER: 10,
}

_URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}|localhost)"
    r"(?::\d{2,5})?"
    r"(?:/[^\s]*)?$",
    re.IGNORECASE,
)


def normalize_web_url(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("URL is required.")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    if not _URL_PATTERN.match(cleaned):
        raise ValueError("Enter a valid web URL (include a domain such as example.com).")
    return cleaned


class DigitalPlatformOption(BaseModel):
    value: DigitalPlatform
    label: str
    default_category: DigitalPresenceCategory


class DigitalPresenceCategoryOption(BaseModel):
    value: DigitalPresenceCategory
    label: str


def list_platform_options() -> list[DigitalPlatformOption]:
    return [
        DigitalPlatformOption(
            value=platform,
            label=PLATFORM_LABELS[platform],
            default_category=PLATFORM_DEFAULT_CATEGORY[platform],
        )
        for platform in sorted(PLATFORM_SORT_ORDER, key=lambda item: PLATFORM_SORT_ORDER[item])
    ]


def list_category_options() -> list[DigitalPresenceCategoryOption]:
    return [
        DigitalPresenceCategoryOption(value=category, label=CATEGORY_LABELS[category])
        for category in sorted(CATEGORY_SORT_ORDER, key=lambda item: CATEGORY_SORT_ORDER[item])
    ]


class DigitalPresenceLinkInput(BaseModel):
    platform_name: DigitalPlatform | None = None
    url: str | None = Field(default=None, max_length=500)
    category: DigitalPresenceCategory | None = None
    admission_value_note: str | None = Field(default=None, max_length=1000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return normalize_web_url(stripped)

    @field_validator("admission_value_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DigitalPresenceLinkOut(BaseModel):
    id: int
    platform_name: DigitalPlatform | None
    platform_label: str | None
    url: str | None
    category: DigitalPresenceCategory | None
    category_label: str | None
    admission_value_note: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DigitalPresenceLinksResponse(BaseModel):
    booking_id: int | None = None
    lead_id: int | None
    platform_options: list[DigitalPlatformOption]
    category_options: list[DigitalPresenceCategoryOption]
    links: list[DigitalPresenceLinkOut]
    saved_at: datetime | None = None
