from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Legacy aliases kept so existing junction rows and older clients still round-trip.
LEGACY_PROGRAM_LEVEL_ALIASES = {
    "foundation": "Foundation",
    "ug": "Undergraduate",
    "undergraduate": "Undergraduate",
    "graduate": "Graduate",
    "pg": "Graduate",
    "postgraduate": "Graduate",
}
PROGRAM_LEVEL_SORT_ORDER = {
    "Foundation": 0,
    "Foundational": 0,
    "Undergraduate": 1,
    "Graduate": 2,
    "Doctoral": 3,
    "Integrated": 4,
}
# Retained for API filter alias docs / tests that import the name.
PROGRAM_LEVELS = ("Foundation", "Undergraduate", "Graduate")


def normalize_program_level_value(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("program_level cannot be empty")
    if len(raw) > 50:
        raise ValueError("program_level must be at most 50 characters")
    return LEGACY_PROGRAM_LEVEL_ALIASES.get(raw.lower(), raw)


def normalize_program_levels(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        raise ValueError("program_levels must be a list of program levels")

    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        level = normalize_program_level_value(item)
        if level in seen:
            continue
        seen.add(level)
        unique.append(level)
    unique.sort(
        key=lambda level: (PROGRAM_LEVEL_SORT_ORDER.get(level, 99), level.lower())
    )
    return unique


class DocumentTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_name: str
    file_url: str
    file_size: int | None = None
    uploaded_by: int | None = None
    created_at: datetime | None = None
    download_url: str | None = None


class DocumentRequirementCountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    iso2: str
    name: str


class DocumentRequirementBase(BaseModel):
    document_name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    accepted_format: str | None = None
    program_levels: list[str] = Field(default_factory=list)
    program_level: str | None = None
    is_mandatory: bool = True
    is_global: bool = False
    country_ids: list[int] = Field(default_factory=list)

    @field_validator("document_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("document_name is required")
        return cleaned

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("accepted_format")
    @classmethod
    def strip_accepted_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("program_levels", mode="before")
    @classmethod
    def coerce_program_levels(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @model_validator(mode="after")
    def validate_levels_and_countries(self) -> DocumentRequirementBase:
        levels = normalize_program_levels(self.program_levels)
        if not levels and self.program_level:
            levels = normalize_program_levels([self.program_level])
        if not levels:
            raise ValueError("program_levels must include at least one level")
        self.program_levels = levels
        self.program_level = levels[0]

        if self.is_global:
            self.country_ids = []
            return self
        if not self.country_ids:
            raise ValueError("country_ids are required when is_global is false")
        seen: set[int] = set()
        unique: list[int] = []
        for country_id in self.country_ids:
            if country_id in seen:
                continue
            seen.add(country_id)
            unique.append(int(country_id))
        self.country_ids = unique
        return self


class DocumentRequirementCreate(DocumentRequirementBase):
    pass


class DocumentRequirementUpdate(BaseModel):
    document_name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    accepted_format: str | None = None
    program_levels: list[str] | None = None
    program_level: str | None = None
    is_mandatory: bool | None = None
    is_global: bool | None = None
    country_ids: list[int] | None = None

    @field_validator("document_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("document_name cannot be empty")
        return cleaned

    @field_validator("accepted_format")
    @classmethod
    def strip_accepted_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("program_levels", mode="before")
    @classmethod
    def coerce_program_levels(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_program_levels(value)

    @field_validator("program_level", mode="before")
    @classmethod
    def normalize_single_level(cls, value: object) -> object:
        if value is None:
            return None
        return normalize_program_level_value(value)

    @model_validator(mode="after")
    def coalesce_levels(self) -> DocumentRequirementUpdate:
        if self.program_levels is None and self.program_level is not None:
            self.program_levels = [self.program_level]
        if self.program_levels is not None:
            if not self.program_levels:
                raise ValueError("program_levels must include at least one level")
            self.program_level = self.program_levels[0]
        return self


class DocumentRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_name: str
    description: str | None = None
    accepted_format: str | None = None
    program_levels: list[str] = Field(default_factory=list)
    program_level: str | None = None
    is_mandatory: bool
    is_global: bool
    template_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    countries: list[DocumentRequirementCountryRead] = Field(default_factory=list)
    template: DocumentTemplateRead | None = None


class DocumentRequirementListResponse(BaseModel):
    items: list[DocumentRequirementRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class DocumentTemplateDownloadResponse(BaseModel):
    template_id: int
    template_name: str
    file_url: str
    download_url: str
    file_size: int | None = None


class DocumentChecklistCreate(BaseModel):
    program_level: str = Field(..., min_length=1, max_length=50)
    scope: str = Field(default="global")
    country_id: int | None = None

    @field_validator("program_level", mode="before")
    @classmethod
    def normalize_checklist_level(cls, value: object) -> str:
        return normalize_program_level_value(value)

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_checklist_scope(cls, value: object) -> str:
        raw = str(value or "global").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "global": "global",
            "country_specific": "country_specific",
            "countryspecific": "country_specific",
            "country": "country_specific",
        }
        scope = aliases.get(raw)
        if scope is None:
            raise ValueError("scope must be 'global' or 'country_specific'")
        return scope


class DocumentChecklistLevelsResponse(BaseModel):
    """Program levels that have at least one document requirement for the checklist scope."""

    program_levels: list[str] = Field(default_factory=list)


class DocumentChecklistScopeResponse(BaseModel):
    """Whether Country-Specific is available and which countries have requirement mappings."""

    country_specific_available: bool = False
    countries: list[DocumentRequirementCountryRead] = Field(default_factory=list)
