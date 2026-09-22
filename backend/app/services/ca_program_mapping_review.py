from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.academia_institution import Institution
from app.models.country import Country
from app.schemas.program_major_mapping import (
    CaProgramMappingSuggestionsResponse,
    ProgramMappingBulkApplyItem,
    ProgramMappingBulkApplyResponse,
)
from app.services import program_mapping_review_shared as shared

# Historical CA-24 harvest/import institution set. Kept for offline audit/harvest
# scripts. CA Mapping Review + ca_scope_only bulk-apply use all iso2=CA institutions.
CA24_INSTITUTION_IDS = frozenset(
    {
        58,
        59,
        62,
        64,
        65,
        66,
        72,
        79,
        81,  # Université Laval
        91,
        92,
        94,
        99,
        104,
        111,
        112,
        113,
        114,
        116,
        117,
        118,
        120,
        167,
        170,
        173,
    }
)

_SUGGESTIONS_PATHS = (
    Path(__file__).resolve().parents[1] / "data" / "ca_unmapped_suggestions.json",
    Path(__file__).resolve().parents[2] / "scripts" / "_ca_unmapped_suggestions.json",
)


def _is_ca_institution(db: Session, institution_id: int) -> bool:
    row = (
        db.query(Country.iso2)
        .join(Institution, Institution.country_id == Country.id)
        .filter(Institution.id == institution_id)
        .first()
    )
    return bool(row and row[0] == "CA")


def _ca_scope_error(db: Session, institution_id: int) -> str | None:
    if not _is_ca_institution(db, institution_id):
        return "Program institution is outside Canada scope."
    return None


def list_ca_program_mapping_suggestions(db: Session) -> CaProgramMappingSuggestionsResponse:
    return CaProgramMappingSuggestionsResponse.model_validate(
        shared.list_program_mapping_suggestions(
            db,
            suggestions_paths=_SUGGESTIONS_PATHS,
        ).model_dump()
    )


def bulk_apply_program_mappings(
    db: Session,
    items: list[ProgramMappingBulkApplyItem],
    *,
    ca_scope_only: bool = True,
) -> ProgramMappingBulkApplyResponse:
    scope_validator = _ca_scope_error if ca_scope_only else None
    return shared.bulk_apply_program_mappings(
        db,
        items,
        scope_validator=scope_validator,
    )
