from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rich_text import OptionalRichText4000


class EducationSuperMajorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=80)
    description: OptionalRichText4000 = None
    sort_order: int = 0
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip().upper()
            return stripped or None
        return value

class EducationSuperMajorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=80)
    description: OptionalRichText4000 = None
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip().upper()
            return stripped or None
        return value

class EducationSuperMajorRead(BaseModel):
    id: int
    name: str
    code: str
    description: str | None = None
    sort_order: int
    is_active: bool = True
    major_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class EducationSuperMajorListResponse(BaseModel):
    items: list[EducationSuperMajorRead]
    page: int
    page_size: int
    total: int
    total_pages: int
