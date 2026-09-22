from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.academia_institution import Institution
from app.models.country import Country
from app.schemas.program_major_mapping import (
    DeProgramMappingSuggestionsResponse,
    ProgramMappingBulkApplyItem,
    ProgramMappingBulkApplyResponse,
)
from app.services import program_mapping_review_shared as shared

_SUGGESTIONS_PATHS = (
    Path(__file__).resolve().parents[1] / "data" / "de_unmapped_suggestions.json",
    Path(__file__).resolve().parents[2] / "scripts" / "_de_unmapped_suggestions.json",
)


def _is_de_institution(db: Session, institution_id: int) -> bool:
    row = (
        db.query(Country.iso2)
        .join(Institution, Institution.country_id == Country.id)
        .filter(Institution.id == institution_id)
        .first()
    )
    return bool(row and row[0] == "DE")


def _de_scope_error(db: Session, institution_id: int) -> str | None:
    if not _is_de_institution(db, institution_id):
        return "Program institution is outside Germany scope."
    return None


def list_de_program_mapping_suggestions(db: Session) -> DeProgramMappingSuggestionsResponse:
    return DeProgramMappingSuggestionsResponse.model_validate(
        shared.list_program_mapping_suggestions(
            db,
            suggestions_paths=_SUGGESTIONS_PATHS,
        ).model_dump()
    )


def bulk_apply_program_mappings(
    db: Session,
    items: list[ProgramMappingBulkApplyItem],
    *,
    de_scope_only: bool = True,
) -> ProgramMappingBulkApplyResponse:
    scope_validator = _de_scope_error if de_scope_only else None
    return shared.bulk_apply_program_mappings(
        db,
        items,
        scope_validator=scope_validator,
    )
