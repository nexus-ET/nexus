from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rich_text import OptionalRichText5000


class EducationMajorCreate(BaseModel):
    program_id: UUID | None = Field(
        default=None,
        description="Optional parent qualification program; use Academic Mapping to assign later",
    )
    code: str | None = Field(default=None, max_length=50)
    label: str = Field(min_length=1, max_length=255)
    description: OptionalRichText5000 = None
    is_other: bool = False
    sort_order: int = 0
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_create_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class EducationMajorUpdate(BaseModel):
    program_id: UUID | None = Field(
        default=None, description="Parent qualification program (programs.id)"
    )
    code: str | None = Field(default=None, max_length=50)
    label: str | None = Field(default=None, min_length=1, max_length=255)
    description: OptionalRichText5000 = None
    is_other: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_update_code(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class MajorLevelProgramCount(BaseModel):
    level_id: int
    level_name: str
    program_count: int


class EducationMajorRead(BaseModel):
    id: int
    code: str | None = None
    label: str
    description: str | None = None
    program_id: UUID | None = None
    program_name: str | None = None
    level_id: int | None = None
    level_name: str | None = None
    is_other: bool
    sort_order: int
    is_active: bool = True
    color: str | None = None
    level_ids: list[int] = Field(default_factory=list)
    level_names: list[str] = Field(default_factory=list)
    level_program_counts: list[MajorLevelProgramCount] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EducationMajorListResponse(BaseModel):
    items: list[EducationMajorRead]
    page: int
    page_size: int
    total: int
    total_pages: int
