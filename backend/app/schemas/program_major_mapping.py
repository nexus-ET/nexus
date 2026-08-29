from pydantic import BaseModel, ConfigDict, Field


class ProgramMajorMappingRead(BaseModel):
    id: int
    program_id: int
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
    program_ids: list[int] = Field(
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
    program_ids: list[int] = Field(default_factory=list)


class ProgramMappingBulkApplyItem(BaseModel):
    program_id: int = Field(..., ge=1)
    education_major_id: int = Field(..., ge=1)
    education_sub_major_id: int | None = Field(default=None, ge=1)


class ProgramMappingBulkApplyRequest(BaseModel):
    items: list[ProgramMappingBulkApplyItem] = Field(..., min_length=1)
    nz_scope_only: bool = Field(
        default=False,
        description="When true, reject programs whose institution is not in New Zealand.",
    )
    ca_scope_only: bool = Field(
        default=False,
        description="When true, reject programs whose institution is not in the CA-24 set.",
    )


class ProgramMappingBulkApplyRowError(BaseModel):
    program_id: int
    detail: str


class ProgramMappingBulkApplyResponse(BaseModel):
    applied: int = Field(
        description="Mappings newly inserted or replaced with a different selection",
    )
    skipped: int = Field(
        description="Total skipped rows (existing + duplicate-in-request)",
    )
    skipped_existing: int = Field(
        default=0,
        description="Rows skipped because the exact program/major/sub-major mapping already exists",
    )
    skipped_duplicate_in_request: int = Field(
        default=0,
        description="Rows skipped because the same mapping appeared more than once in the request",
    )
    errors: list[ProgramMappingBulkApplyRowError] = Field(default_factory=list)


class ProgramMappingSuggestionRead(BaseModel):
    institution_id: int
    institution_name: str
    program_id: int | None = None
    program_title: str
    suggested_major: str
    suggested_sub_major: str
    category: str
    status: str
    education_major_id: int | None = None
    education_sub_major_id: int | None = None
    current_education_major_id: int | None = Field(
        default=None,
        description="Live PEM major id for this program (if any).",
    )
    current_education_sub_major_id: int | None = Field(
        default=None,
        description="Live PEM sub-major id for this program (if any).",
    )
    current_major_label: str | None = Field(
        default=None,
        description="Live PEM major label for display.",
    )
    current_sub_major_label: str | None = Field(
        default=None,
        description="Live PEM sub-major label for display.",
    )
    already_mapped: bool = Field(
        default=False,
        description=(
            "True when the program already has a committed PEM that does not need "
            "a queue upgrade. The list endpoint excludes these rows; the flag is "
            "retained for internal classification. Major-only programs with a "
            "sub-major upgrade suggestion stay already_mapped=false."
        ),
    )
    applicable: bool = Field(
        description=(
            "True when major/sub-major IDs resolve and the suggested mapping can be "
            "applied as a new insert/upgrade (including major-only → sub upgrades)."
        ),
    )
    apply_note: str | None = Field(
        default=None,
        description=(
            "Extra context for the row (e.g. ambiguous, current live major-only pair)."
        ),
    )


class ProgramMappingSuggestionsResponse(BaseModel):
    generated_at: str | None = None
    revised_at: str | None = None
    total: int
    unmapped_count: int
    ambiguous_count: int
    applicable_count: int
    already_mapped_count: int = Field(
        default=0,
        description=(
            "Count of suggestion rows excluded because the program already has a "
            "committed PEM (not present in items)."
        ),
    )
    items: list[ProgramMappingSuggestionRead]


class NzProgramMappingSuggestionRead(ProgramMappingSuggestionRead):
    """NZ mapping review row (same shape as ProgramMappingSuggestionRead)."""


class NzProgramMappingSuggestionsResponse(ProgramMappingSuggestionsResponse):
    """NZ mapping review list response."""


class CaProgramMappingSuggestionRead(ProgramMappingSuggestionRead):
    """CA-24 mapping review row (same shape as ProgramMappingSuggestionRead)."""


class CaProgramMappingSuggestionsResponse(ProgramMappingSuggestionsResponse):
    """CA-24 mapping review list response."""
