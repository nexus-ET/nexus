from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProgramMajorMappingRead(BaseModel):
    id: int
    program_id: UUID
    education_major_id: int
    major_label: str
    major_code: str | None = None
    major_color: str | None = None
    program_name: str | None = None
    level_id: int | None = None
    level_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProgramMajorMappingListResponse(BaseModel):
    items: list[ProgramMajorMappingRead]


class EducationMajorBulkAssignRequest(BaseModel):
    major_id: int = Field(..., ge=1, description="Catalog major to assign to programs")
    program_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Qualification programs (programs.id) to receive the major mapping",
    )


class EducationMajorBulkAssignResponse(BaseModel):
    assigned: int = Field(description="Programs newly linked to the major")
    overwritten: int = Field(
        default=0,
        description="Legacy field; mappings are additive and this stays 0",
    )
    skipped: int = Field(description="Programs already linked to this major")
    program_ids: list[UUID] = Field(default_factory=list)
