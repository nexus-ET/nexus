from pydantic import BaseModel, ConfigDict, Field


class QualificationProgramMajorRead(BaseModel):
    """Catalog major linked to a qualification program."""

    id: int
    code: str | None = None
    label: str

    model_config = ConfigDict(from_attributes=True)


class QualificationProgramRead(BaseModel):
    """Public read model for framework qualification programs (`programs` table)."""

    id: str
    code: str
    name: str
    label: str
    level_id: int
    level_code: str | None = None
    level_name: str | None = None
    sort_order: int = 0
    majors: list[QualificationProgramMajorRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
