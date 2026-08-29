from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.academia_institution import Institution
from app.models.country import Country
from app.schemas.program_major_mapping import (
    NzProgramMappingSuggestionsResponse,
    ProgramMappingBulkApplyItem,
    ProgramMappingBulkApplyResponse,
)
from app.services import program_mapping_review_shared as shared

_SUGGESTIONS_PATHS = (
    Path(__file__).resolve().parents[1] / "data" / "nz_unmapped_suggestions.json",
    Path(__file__).resolve().parents[2] / "scripts" / "_nz_unmapped_suggestions.json",
)


def _is_nz_institution(db: Session, institution_id: int) -> bool:
    row = (
        db.query(Country.iso2)
        .join(Institution, Institution.country_id == Country.id)
        .filter(Institution.id == institution_id)
        .first()
    )
    return bool(row and row[0] == "NZ")


def _nz_scope_error(db: Session, institution_id: int) -> str | None:
    if not _is_nz_institution(db, institution_id):
        return "Program institution is outside New Zealand scope."
    return None


def list_nz_program_mapping_suggestions(db: Session) -> NzProgramMappingSuggestionsResponse:
    return NzProgramMappingSuggestionsResponse.model_validate(
        shared.list_program_mapping_suggestions(
            db,
            suggestions_paths=_SUGGESTIONS_PATHS,
        ).model_dump()
    )


def bulk_apply_program_mappings(
    db: Session,
    items: list[ProgramMappingBulkApplyItem],
    *,
    nz_scope_only: bool = True,
    ca_scope_only: bool = False,
) -> ProgramMappingBulkApplyResponse:
    if ca_scope_only:
        from app.services import ca_program_mapping_review as ca_review

        return ca_review.bulk_apply_program_mappings(
            db,
            items,
            ca_scope_only=True,
        )
    scope_validator = _nz_scope_error if nz_scope_only else None
    return shared.bulk_apply_program_mappings(
        db,
        items,
        scope_validator=scope_validator,
    )
