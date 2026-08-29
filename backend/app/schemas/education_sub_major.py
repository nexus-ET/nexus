from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rich_text import OptionalRichText2000


def _strip_optional_text(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class EducationSubMajorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    major_id: int = Field(ge=1)
    sub_major_description: OptionalRichText2000 = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("sub_major_description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        return _strip_optional_text(value)


class EducationSubMajorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    major_id: int | None = Field(default=None, ge=1)
    sub_major_description: OptionalRichText2000 = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("sub_major_description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        return _strip_optional_text(value)


class SubMajorLevelProgramCount(BaseModel):
    level_id: int
    level_name: str
    count: int


class EducationSubMajorRead(BaseModel):
    id: int
    name: str
    sub_major_description: str | None = None
    major_id: int
    major_label: str | None = None
    major_color: str | None = None
    programs_by_level: list[SubMajorLevelProgramCount] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EducationSubMajorListResponse(BaseModel):
    items: list[EducationSubMajorRead]
    page: int
    page_size: int
    total: int
    total_pages: int
