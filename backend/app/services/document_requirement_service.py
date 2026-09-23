from __future__ import annotations

from math import ceil

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.country import Country
from app.models.document_requirement import (
    DocumentRequirement,
    DocumentRequirementLevel,
    DocumentTemplate,
    document_requirement_countries,
)
from app.models.level import Level
from app.schemas.document_requirement import (
    PROGRAM_LEVEL_SORT_ORDER,
    DocumentRequirementCreate,
    DocumentRequirementUpdate,
    normalize_program_level_value,
    normalize_program_levels,
)
from app.services.document_template_storage import resolve_download_url
from app.services.levels import get_level_by_name


def _load_countries(db: Session, country_ids: list[int]) -> list[Country]:
    if not country_ids:
        return []
    rows = (
        db.query(Country)
        .filter(Country.id.in_(country_ids))
        .order_by(Country.sort_order.asc(), Country.name.asc())
        .all()
    )
    found = {row.id for row in rows}
    missing = [cid for cid in country_ids if cid not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown country id(s): {', '.join(str(x) for x in missing)}",
        )
    by_id = {row.id: row for row in rows}
    return [by_id[cid] for cid in country_ids]


def resolve_countries(db: Session, country_ids: list[int]) -> list[Country]:
    """Public wrapper: load countries by id or raise 400 for unknown ids."""
    return _load_countries(db, country_ids)


def _sync_countries(
    requirement: DocumentRequirement,
    *,
    is_global: bool,
    country_ids: list[int],
    db: Session,
) -> None:
    if is_global:
        requirement.countries = []
        return
    requirement.countries = _load_countries(db, country_ids)


def _ordered_levels(requirement: DocumentRequirement) -> list[str]:
    levels = [
        row.program_level
        for row in (requirement.level_rows or [])
        if row.program_level
    ]
    levels.sort(key=lambda level: PROGRAM_LEVEL_SORT_ORDER.get(level, 99))
    return levels


def _sync_levels(requirement: DocumentRequirement, program_levels: list[str]) -> None:
    levels = normalize_program_levels(program_levels)
    if not levels:
        raise HTTPException(
            status_code=400,
            detail="program_levels must include at least one level",
        )
    requirement.level_rows = [
        DocumentRequirementLevel(program_level=level) for level in levels
    ]


def serialize_requirement(requirement: DocumentRequirement) -> dict:
    template = requirement.template
    template_payload = None
    if template is not None:
        template_payload = {
            "id": template.id,
            "template_name": template.template_name,
            "file_url": template.file_url,
            "file_size": template.file_size,
            "uploaded_by": template.uploaded_by,
            "created_at": template.created_at,
            "download_url": resolve_download_url(
                template.file_url,
                filename=template.template_name,
            ),
        }
    program_levels = _ordered_levels(requirement)
    return {
        "id": requirement.id,
        "document_name": requirement.document_name,
        "description": requirement.description,
        "accepted_format": requirement.accepted_format,
        "program_levels": program_levels,
        "program_level": program_levels[0] if program_levels else None,
        "is_mandatory": bool(requirement.is_mandatory),
        "is_global": bool(requirement.is_global),
        "template_id": requirement.template_id,
        "created_at": requirement.created_at,
        "updated_at": requirement.updated_at,
        "countries": [
            {"id": c.id, "iso2": c.iso2, "name": c.name}
            for c in (requirement.countries or [])
        ],
        "template": template_payload,
    }


def list_document_requirements(
    db: Session,
    *,
    program_level: str | None = None,
    country_ids: list[int] | None = None,
    is_global: bool | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[DocumentRequirement], int]:
    query = db.query(DocumentRequirement).options(
        joinedload(DocumentRequirement.template),
        joinedload(DocumentRequirement.countries),
        joinedload(DocumentRequirement.level_rows),
    )

    if program_level:
        level_match = (
            db.query(DocumentRequirementLevel.requirement_id)
            .filter(DocumentRequirementLevel.program_level == program_level)
            .distinct()
            .subquery()
        )
        query = query.filter(DocumentRequirement.id.in_(level_match))

    if is_global is True:
        query = query.filter(DocumentRequirement.is_global.is_(True))
    elif is_global is False:
        query = query.filter(DocumentRequirement.is_global.is_(False))

    if country_ids:
        country_match = (
            db.query(document_requirement_countries.c.requirement_id)
            .filter(document_requirement_countries.c.country_id.in_(country_ids))
            .distinct()
            .subquery()
        )
        if is_global is False:
            query = query.filter(DocumentRequirement.id.in_(country_match))
        else:
            query = query.filter(
                or_(
                    DocumentRequirement.is_global.is_(True),
                    DocumentRequirement.id.in_(country_match),
                )
            )

    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                DocumentRequirement.document_name.ilike(needle),
                DocumentRequirement.description.ilike(needle),
            )
        )

    total = query.with_entities(func.count(DocumentRequirement.id)).scalar() or 0
    rows = (
        query.order_by(
            DocumentRequirement.created_at.asc(),
            DocumentRequirement.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, int(total)


def get_document_requirement(db: Session, requirement_id: int) -> DocumentRequirement:
    row = (
        db.query(DocumentRequirement)
        .options(
            joinedload(DocumentRequirement.template),
            joinedload(DocumentRequirement.countries),
            joinedload(DocumentRequirement.level_rows),
        )
        .filter(DocumentRequirement.id == requirement_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document requirement not found.")
    return row


def create_document_requirement(
    db: Session,
    payload: DocumentRequirementCreate,
) -> DocumentRequirement:
    row = DocumentRequirement(
        document_name=payload.document_name,
        description=payload.description,
        accepted_format=payload.accepted_format,
        is_mandatory=payload.is_mandatory,
        is_global=payload.is_global,
    )
    db.add(row)
    db.flush()
    _sync_levels(row, list(payload.program_levels))
    _sync_countries(
        row,
        is_global=payload.is_global,
        country_ids=payload.country_ids,
        db=db,
    )
    db.commit()
    return get_document_requirement(db, row.id)


def update_document_requirement(
    db: Session,
    requirement_id: int,
    payload: DocumentRequirementUpdate,
) -> DocumentRequirement:
    row = get_document_requirement(db, requirement_id)
    data = payload.model_dump(exclude_unset=True)

    if "document_name" in data and data["document_name"] is not None:
        row.document_name = data["document_name"]
    if "description" in data:
        row.description = data["description"]
    if "accepted_format" in data:
        row.accepted_format = data["accepted_format"]
    if "program_levels" in data and data["program_levels"] is not None:
        _sync_levels(row, list(data["program_levels"]))
    if "is_mandatory" in data and data["is_mandatory"] is not None:
        row.is_mandatory = data["is_mandatory"]

    next_is_global = data.get("is_global", row.is_global)
    if "is_global" in data and data["is_global"] is not None:
        row.is_global = bool(data["is_global"])

    if next_is_global:
        row.countries = []
    elif "country_ids" in data:
        country_ids = data.get("country_ids") or []
        if not country_ids:
            raise HTTPException(
                status_code=400,
                detail="country_ids are required when is_global is false",
            )
        _sync_countries(
            row,
            is_global=False,
            country_ids=country_ids,
            db=db,
        )
    elif not row.is_global and not row.countries:
        raise HTTPException(
            status_code=400,
            detail="country_ids are required when is_global is false",
        )

    db.commit()
    return get_document_requirement(db, row.id)


def delete_document_requirement(db: Session, requirement_id: int) -> None:
    row = get_document_requirement(db, requirement_id)
    db.delete(row)
    db.commit()


def attach_template(
    db: Session,
    *,
    requirement_id: int,
    template_name: str,
    file_url: str,
    file_size: int | None,
    uploaded_by: int | None,
) -> DocumentRequirement:
    row = get_document_requirement(db, requirement_id)
    template = DocumentTemplate(
        template_name=template_name[:150],
        file_url=file_url,
        file_size=file_size,
        uploaded_by=uploaded_by,
    )
    db.add(template)
    db.flush()
    row.template_id = template.id
    db.commit()
    return get_document_requirement(db, row.id)


def total_pages(total: int, page_size: int) -> int:
    if page_size <= 0:
        return 0
    return int(ceil(total / page_size)) if total else 0


def list_levels_with_requirements(db: Session) -> list[str]:
    """Distinct program levels that appear on at least one document requirement."""
    rows = (
        db.query(DocumentRequirementLevel.program_level)
        .filter(DocumentRequirementLevel.program_level.isnot(None))
        .filter(DocumentRequirementLevel.program_level != "")
        .distinct()
        .all()
    )
    levels = [str(row[0]).strip() for row in rows if row and row[0]]
    levels.sort(
        key=lambda level: (PROGRAM_LEVEL_SORT_ORDER.get(level, 99), level.lower())
    )
    return levels


def list_mapped_checklist_countries(db: Session) -> list[Country]:
    """Countries that appear in document_requirement_countries (at least one mapping)."""
    mapped_ids = (
        db.query(document_requirement_countries.c.country_id)
        .distinct()
        .subquery()
    )
    return (
        db.query(Country)
        .filter(Country.id.in_(mapped_ids))
        .order_by(Country.sort_order.asc(), Country.name.asc())
        .all()
    )


def checklist_scope_options(db: Session) -> dict:
    """Meta for the checklist popup: Country-Specific availability and mapped countries."""
    countries = list_mapped_checklist_countries(db)
    return {
        "country_specific_available": bool(countries),
        "countries": [
            {"id": c.id, "iso2": c.iso2, "name": c.name} for c in countries
        ],
    }


def has_country_mapped_requirement_for_level(
    db: Session,
    *,
    program_level: str,
    country_id: int,
) -> bool:
    """True when the level has at least one requirement linked to the country."""
    level_keys = _junction_keys_for_level(db, program_level)
    level_ids = (
        db.query(DocumentRequirementLevel.requirement_id)
        .filter(DocumentRequirementLevel.program_level.in_(level_keys))
        .distinct()
    )
    country_match = (
        db.query(document_requirement_countries.c.requirement_id)
        .filter(document_requirement_countries.c.country_id == country_id)
        .distinct()
    )
    return (
        db.query(DocumentRequirement.id)
        .filter(
            DocumentRequirement.id.in_(level_ids),
            DocumentRequirement.id.in_(country_match),
        )
        .first()
        is not None
    )


def list_catalog_levels_with_requirements(
    db: Session,
    *,
    scope: str = "global",
    country_id: int | None = None,
) -> list[str]:
    """Catalog level display names that have at least one requirement for the checklist scope.

    Global: levels with at least one is_global requirement.
    Country-Specific: levels with at least one country-mapped requirement for country_id
    (globals alone do not enable the level).
    """
    if scope == "country_specific":
        if country_id is None:
            return []
        _load_countries(db, [country_id])

    stored = list_levels_with_requirements(db)
    if not stored:
        return []

    stored_normalized: dict[str, str] = {}
    for value in stored:
        try:
            stored_normalized[normalize_program_level_value(value)] = value
        except ValueError:
            continue

    catalog_names: list[str] = []
    for level in db.query(Level).order_by(Level.id.asc()).all():
        name = (level.name or "").strip()
        if not name:
            continue
        try:
            normalized = normalize_program_level_value(name)
        except ValueError:
            normalized = name
        if not (
            name in stored
            or normalized in stored
            or normalized in stored_normalized
            or name in stored_normalized
        ):
            continue
        if scope == "country_specific":
            if has_country_mapped_requirement_for_level(
                db,
                program_level=name,
                country_id=int(country_id),
            ):
                catalog_names.append(name)
            continue
        if list_requirements_for_checklist(
            db,
            program_level=name,
            scope=scope,
            country_id=country_id,
        ):
            catalog_names.append(name)

    return catalog_names


def resolve_catalog_level(db: Session, program_level: str) -> Level:
    """Validate program_level against the academia levels catalog."""
    try:
        normalized = normalize_program_level_value(program_level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    level = get_level_by_name(db, normalized)
    if level is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown program level: {normalized}",
        )
    return level


def _junction_keys_for_level(db: Session, level_name: str) -> list[str]:
    """Stored junction program_level values that correspond to a catalog level name."""
    try:
        targets = {
            level_name,
            normalize_program_level_value(level_name),
        }
    except ValueError:
        targets = {level_name}

    keys: list[str] = []
    seen: set[str] = set()
    for stored in list_levels_with_requirements(db):
        try:
            normalized = normalize_program_level_value(stored)
        except ValueError:
            normalized = stored
        if stored in targets or normalized in targets:
            if stored not in seen:
                seen.add(stored)
                keys.append(stored)
    if level_name not in seen:
        keys.append(level_name)
    return keys


def list_requirements_for_checklist(
    db: Session,
    *,
    program_level: str,
    scope: str = "global",
    country_id: int | None = None,
) -> list[DocumentRequirement]:
    """Requirements for a checklist PDF, ordered like the list page.

    Global: is_global rows for the level.
    Country-Specific: country-linked rows for that country plus global rows for the
    same level (no duplicates). Callers must gate on at least one country-mapped
    requirement for the level before generating a country PDF.
    """
    level_keys = _junction_keys_for_level(db, program_level)
    level_ids = (
        db.query(DocumentRequirementLevel.requirement_id)
        .filter(DocumentRequirementLevel.program_level.in_(level_keys))
        .distinct()
    )
    query = (
        db.query(DocumentRequirement)
        .options(joinedload(DocumentRequirement.level_rows))
        .filter(DocumentRequirement.id.in_(level_ids))
    )

    if scope == "global":
        query = query.filter(DocumentRequirement.is_global.is_(True))
    elif scope == "country_specific":
        if country_id is None:
            raise HTTPException(
                status_code=400,
                detail="country_id is required when scope is country_specific",
            )
        _load_countries(db, [country_id])
        country_match = (
            db.query(document_requirement_countries.c.requirement_id)
            .filter(document_requirement_countries.c.country_id == country_id)
            .distinct()
        )
        query = query.filter(
            or_(
                DocumentRequirement.is_global.is_(True),
                DocumentRequirement.id.in_(country_match),
            )
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="scope must be 'global' or 'country_specific'",
        )

    return (
        query.order_by(
            DocumentRequirement.created_at.asc(),
            DocumentRequirement.id.asc(),
        )
        .all()
    )
