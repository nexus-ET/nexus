from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.education_major import EducationMajor
from app.models.education_sub_major import EducationSubMajor
from app.models.program import Program
from app.models.program_education_major_mapping import ProgramEducationMajorMapping
from app.schemas.program_major_mapping import (
    ProgramMappingBulkApplyItem,
    ProgramMappingBulkApplyResponse,
    ProgramMappingBulkApplyRowError,
    ProgramMappingSuggestionRead,
    ProgramMappingSuggestionsResponse,
)

_PLACEHOLDER_MAJORS = {"", "—", "-", "–"}
_AMBIGUOUS_SUB_FRAGMENTS = ("ambiguous", "needs manual review")


def load_suggestions_payload(paths: tuple[Path, ...]) -> dict:
    for path in paths:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise HTTPException(
        status_code=404,
        detail="Unmapped suggestions file not found. Run the build script for this region.",
    )


def is_valid_major_label(label: str) -> bool:
    return label.strip() not in _PLACEHOLDER_MAJORS


def sub_major_is_major_only(label: str) -> bool:
    normalized = label.strip().lower()
    return normalized in {"major-only", "major only", "—", "-", "–", ""}


def sub_major_is_ambiguous(label: str) -> bool:
    normalized = label.strip().lower()
    if not normalized:
        return False
    return any(fragment in normalized for fragment in _AMBIGUOUS_SUB_FRAGMENTS)


def program_institution_id(program: Program) -> int | None:
    description = program.description or ""
    match = re.search(r"institution_id=(\d+)", description)
    return int(match.group(1)) if match else None


def build_catalog_indexes(
    db: Session,
) -> tuple[
    dict[str, int],
    dict[tuple[int, str], int],
    dict[int, str],
    dict[int, str],
    set[int],
    set[int],
]:
    majors = (
        db.query(EducationMajor)
        .filter(
            EducationMajor.program_id.is_(None),
            EducationMajor.is_active.is_(True),
        )
        .all()
    )
    major_by_label = {major.label.strip(): int(major.id) for major in majors}
    major_label_by_id = {int(major.id): major.label for major in majors}
    valid_major_ids = set(major_label_by_id)

    sub_majors = db.query(EducationSubMajor).all()
    sub_by_parent_name: dict[tuple[int, str], int] = {}
    sub_label_by_id: dict[int, str] = {}
    valid_sub_ids: set[int] = set()
    for sub in sub_majors:
        sid = int(sub.id)
        valid_sub_ids.add(sid)
        sub_label_by_id[sid] = sub.name
        sub_by_parent_name[(int(sub.major_id), sub.name.strip())] = sid
    return (
        major_by_label,
        sub_by_parent_name,
        major_label_by_id,
        sub_label_by_id,
        valid_major_ids,
        valid_sub_ids,
    )


def resolve_suggestion_ids(
    *,
    suggested_major: str,
    suggested_sub_major: str,
    major_by_label: dict[str, int],
    sub_by_parent_name: dict[tuple[int, str], int],
) -> tuple[int | None, int | None, bool, str | None]:
    if not is_valid_major_label(suggested_major):
        return None, None, False, "No catalog major suggested."

    major_id = major_by_label.get(suggested_major.strip())
    if major_id is None:
        return None, None, False, f"Major not found in catalog: {suggested_major}"

    if sub_major_is_ambiguous(suggested_sub_major):
        return major_id, None, False, "Sub-major suggestion is ambiguous."

    if sub_major_is_major_only(suggested_sub_major):
        return major_id, None, True, None

    sub_id = sub_by_parent_name.get((major_id, suggested_sub_major.strip()))
    if sub_id is None:
        return (
            major_id,
            None,
            False,
            f"Sub-major not found under {suggested_major}: {suggested_sub_major}",
        )
    return major_id, sub_id, True, None


def existing_mapping_keys(
    db: Session,
    program_ids: list[int],
) -> set[tuple[int, int, int | None]]:
    if not program_ids:
        return set()
    rows = (
        db.query(
            ProgramEducationMajorMapping.program_id,
            ProgramEducationMajorMapping.education_major_id,
            ProgramEducationMajorMapping.education_sub_major_id,
        )
        .filter(ProgramEducationMajorMapping.program_id.in_(program_ids))
        .all()
    )
    return {
        (int(program_id), int(major_id), int(sub_id) if sub_id is not None else None)
        for program_id, major_id, sub_id in rows
    }


def existing_mappings_by_program(
    db: Session,
    program_ids: list[int],
) -> dict[int, list[tuple[int, int | None]]]:
    if not program_ids:
        return {}
    grouped: dict[int, list[tuple[int, int | None]]] = {}
    rows = (
        db.query(
            ProgramEducationMajorMapping.program_id,
            ProgramEducationMajorMapping.education_major_id,
            ProgramEducationMajorMapping.education_sub_major_id,
        )
        .filter(ProgramEducationMajorMapping.program_id.in_(program_ids))
        .all()
    )
    for program_id, major_id, sub_id in rows:
        pid = int(program_id)
        grouped.setdefault(pid, []).append(
            (int(major_id), int(sub_id) if sub_id is not None else None)
        )
    return grouped


def pick_display_mapping(
    mappings: list[tuple[int, int | None]],
) -> tuple[int, int | None] | None:
    if not mappings:
        return None
    with_sub = [mapping for mapping in mappings if mapping[1] is not None]
    if with_sub:
        return with_sub[0]
    return mappings[0]


def resolve_row_ids(
    *,
    raw: dict,
    major_by_label: dict[str, int],
    sub_by_parent_name: dict[tuple[int, str], int],
    valid_major_ids: set[int],
    valid_sub_ids: set[int],
) -> tuple[int | None, int | None, bool, str | None]:
    label_major_id, label_sub_id, label_applicable, label_note = resolve_suggestion_ids(
        suggested_major=str(raw.get("suggested_major") or ""),
        suggested_sub_major=str(raw.get("suggested_sub_major") or ""),
        major_by_label=major_by_label,
        sub_by_parent_name=sub_by_parent_name,
    )
    if label_major_id is not None:
        return label_major_id, label_sub_id, label_applicable, label_note

    baked_major = raw.get("education_major_id")
    baked_sub = raw.get("education_sub_major_id")
    if baked_major is None:
        return None, None, False, label_note or "No catalog major suggested."

    try:
        major_id = int(baked_major)
    except (TypeError, ValueError):
        return None, None, False, label_note or "Invalid baked major id."

    if major_id not in valid_major_ids:
        return None, None, False, f"Major id {major_id} not found in live catalog."

    if baked_sub is None:
        if "applicable" in raw:
            return major_id, None, bool(raw.get("applicable")), raw.get("apply_note")
        return major_id, None, True, None

    try:
        sub_id = int(baked_sub)
    except (TypeError, ValueError):
        return major_id, None, False, "Invalid baked sub-major id."

    if sub_id not in valid_sub_ids:
        return (
            major_id,
            None,
            False,
            f"Sub-major id {sub_id} not found in live catalog.",
        )

    parent_ok = any(
        sid == sub_id and mid == major_id for (mid, _name), sid in sub_by_parent_name.items()
    )
    if not parent_ok:
        if "applicable" in raw:
            return (
                major_id,
                sub_id,
                bool(raw.get("applicable")),
                raw.get("apply_note"),
            )
        return major_id, None, False, "Baked sub-major parent does not match major."

    if "applicable" in raw:
        return major_id, sub_id, bool(raw.get("applicable")), raw.get("apply_note")
    return major_id, sub_id, True, None


def list_program_mapping_suggestions(
    db: Session,
    *,
    suggestions_paths: tuple[Path, ...],
) -> ProgramMappingSuggestionsResponse:
    payload = load_suggestions_payload(suggestions_paths)
    (
        major_by_label,
        sub_by_parent_name,
        major_label_by_id,
        sub_label_by_id,
        valid_major_ids,
        valid_sub_ids,
    ) = build_catalog_indexes(db)

    resolved: list[dict] = []
    program_ids: list[int] = []
    for raw in payload.get("suggestions", []):
        major_id, sub_id, applicable, apply_note = resolve_row_ids(
            raw=raw,
            major_by_label=major_by_label,
            sub_by_parent_name=sub_by_parent_name,
            valid_major_ids=valid_major_ids,
            valid_sub_ids=valid_sub_ids,
        )

        program_id = int(raw["program_id"]) if raw.get("program_id") else None
        if program_id is not None:
            program_ids.append(program_id)

        resolved.append(
            {
                "raw": raw,
                "program_id": program_id,
                "major_id": major_id,
                "sub_id": sub_id,
                "applicable": bool(applicable),
                "apply_note": apply_note,
            }
        )

    existing_keys = existing_mapping_keys(db, program_ids)
    mappings_by_program = existing_mappings_by_program(db, program_ids)

    items: list[ProgramMappingSuggestionRead] = []
    for row in resolved:
        raw = row["raw"]
        program_id = row["program_id"]
        major_id = row["major_id"]
        sub_id = row["sub_id"]
        applicable = row["applicable"]
        apply_note = row["apply_note"]
        status = str(raw.get("status") or "")

        already_mapped = False
        display_major_id = major_id
        display_sub_id = sub_id
        current_major_id: int | None = None
        current_sub_id: int | None = None
        if program_id is not None:
            live_mappings = mappings_by_program.get(int(program_id), [])
            display_mapping = pick_display_mapping(live_mappings)
            if display_mapping is not None:
                current_major_id, current_sub_id = display_mapping

            suggested_key = (
                (
                    int(program_id),
                    int(major_id),
                    int(sub_id) if sub_id is not None else None,
                )
                if major_id is not None
                else None
            )
            exact_exists = bool(suggested_key and suggested_key in existing_keys)
            has_any_sub = any(sid is not None for _mid, sid in live_mappings)
            major_only_live = bool(live_mappings) and not has_any_sub

            current_label = None
            if current_major_id is not None:
                major_name = major_label_by_id.get(current_major_id) or f"#{current_major_id}"
                if current_sub_id is not None:
                    sub_name = sub_label_by_id.get(current_sub_id) or f"#{current_sub_id}"
                    current_label = f"{major_name} / {sub_name}"
                else:
                    current_label = f"{major_name} / (major only)"

            if exact_exists:
                already_mapped = True
                applicable = False
                apply_note = (
                    "Already mapped — edit major/sub-major and re-apply to replace."
                )
                if display_mapping is not None:
                    display_major_id, display_sub_id = display_mapping
                if status in {"unmapped", "upgrade", "major_only"}:
                    status = "mapped"
            elif applicable and major_id is not None and sub_id is not None:
                suggested_label = (
                    f"{major_label_by_id.get(major_id) or raw.get('suggested_major') or major_id}"
                    f" / {sub_label_by_id.get(sub_id) or raw.get('suggested_sub_major') or sub_id}"
                )
                if major_only_live:
                    apply_note = (
                        f"Currently {current_label}. Applying will set "
                        f"{suggested_label} (replaces existing PEM)."
                    )
                    if status == "unmapped":
                        status = "major_only"
                elif has_any_sub:
                    already_mapped = True
                    applicable = False
                    if display_mapping is not None:
                        display_major_id, display_sub_id = display_mapping
                    apply_note = (
                        f"Mapped as {current_label}. Catalog suggestion differs: "
                        f"{suggested_label} — edit dropdowns and re-apply to change."
                    )
                    if status in {"unmapped", "upgrade", "major_only"}:
                        status = "mapped"
            elif live_mappings and not applicable:
                already_mapped = has_any_sub or major_only_live
                if display_mapping is not None:
                    display_major_id, display_sub_id = display_mapping
                if already_mapped and not apply_note:
                    apply_note = (
                        "Already mapped — edit major/sub-major and re-apply to replace."
                    )
                if status == "unmapped" and already_mapped:
                    status = "mapped"
            elif live_mappings and applicable and sub_id is None:
                already_mapped = True
                applicable = False
                apply_note = (
                    "Already mapped — edit major/sub-major and re-apply to replace."
                )
                if display_mapping is not None:
                    display_major_id, display_sub_id = display_mapping
                if status == "unmapped":
                    status = "mapped"

        items.append(
            ProgramMappingSuggestionRead(
                institution_id=int(raw["institution_id"]),
                institution_name=str(raw.get("institution_name") or ""),
                program_id=program_id,
                program_title=str(raw.get("program_title") or ""),
                suggested_major=str(raw.get("suggested_major") or ""),
                suggested_sub_major=str(raw.get("suggested_sub_major") or ""),
                category=str(raw.get("category") or ""),
                status=status,
                education_major_id=display_major_id,
                education_sub_major_id=display_sub_id,
                current_education_major_id=current_major_id,
                current_education_sub_major_id=current_sub_id,
                current_major_label=(
                    major_label_by_id.get(current_major_id) if current_major_id else None
                ),
                current_sub_major_label=(
                    sub_label_by_id.get(current_sub_id) if current_sub_id else None
                ),
                already_mapped=already_mapped,
                applicable=applicable,
                apply_note=apply_note,
            )
        )

    already_mapped_count = sum(1 for item in items if item.already_mapped)
    queue_items = [item for item in items if not item.already_mapped]
    return ProgramMappingSuggestionsResponse(
        generated_at=payload.get("generated_at"),
        revised_at=payload.get("revised_at"),
        total=len(queue_items),
        unmapped_count=sum(1 for item in queue_items if item.status == "unmapped"),
        ambiguous_count=sum(1 for item in queue_items if item.status == "ambiguous"),
        applicable_count=sum(1 for item in queue_items if item.applicable),
        already_mapped_count=already_mapped_count,
        items=queue_items,
    )


def bulk_apply_program_mappings(
    db: Session,
    items: list[ProgramMappingBulkApplyItem],
    *,
    scope_validator: Callable[[Session, int], str | None] | None = None,
) -> ProgramMappingBulkApplyResponse:
    """Apply mappings. scope_validator returns an error detail when out of scope."""
    applied = 0
    skipped_existing = 0
    skipped_duplicate_in_request = 0
    errors: list[ProgramMappingBulkApplyRowError] = []
    seen: set[tuple[int, int, int | None]] = set()

    for item in items:
        key = (item.program_id, item.education_major_id, item.education_sub_major_id)
        if key in seen:
            skipped_duplicate_in_request += 1
            continue
        seen.add(key)

        program = (
            db.query(Program)
            .options(joinedload(Program.level))
            .filter(Program.id == item.program_id)
            .first()
        )
        if not program:
            errors.append(
                ProgramMappingBulkApplyRowError(
                    program_id=item.program_id,
                    detail="Program not found.",
                )
            )
            continue

        institution_id = program_institution_id(program)
        if scope_validator is not None:
            if institution_id is None:
                errors.append(
                    ProgramMappingBulkApplyRowError(
                        program_id=item.program_id,
                        detail="Program is not linked to an institution.",
                    )
                )
                continue
            scope_error = scope_validator(db, institution_id)
            if scope_error:
                errors.append(
                    ProgramMappingBulkApplyRowError(
                        program_id=item.program_id,
                        detail=scope_error,
                    )
                )
                continue

        major = (
            db.query(EducationMajor)
            .filter(
                EducationMajor.id == item.education_major_id,
                EducationMajor.program_id.is_(None),
                EducationMajor.is_active.is_(True),
            )
            .first()
        )
        if not major:
            errors.append(
                ProgramMappingBulkApplyRowError(
                    program_id=item.program_id,
                    detail=f"Invalid or inactive catalog major {item.education_major_id}.",
                )
            )
            continue

        sub_major_id = item.education_sub_major_id
        if sub_major_id is not None:
            sub_major = (
                db.query(EducationSubMajor)
                .filter(EducationSubMajor.id == sub_major_id)
                .first()
            )
            if not sub_major:
                errors.append(
                    ProgramMappingBulkApplyRowError(
                        program_id=item.program_id,
                        detail=f"Sub-major {sub_major_id} not found.",
                    )
                )
                continue
            if int(sub_major.major_id) != int(item.education_major_id):
                errors.append(
                    ProgramMappingBulkApplyRowError(
                        program_id=item.program_id,
                        detail="Sub-major parent does not match selected major.",
                    )
                )
                continue

        existing_rows = (
            db.query(ProgramEducationMajorMapping)
            .filter(ProgramEducationMajorMapping.program_id == item.program_id)
            .order_by(ProgramEducationMajorMapping.id.asc())
            .all()
        )

        def _row_matches(row: ProgramEducationMajorMapping) -> bool:
            if int(row.education_major_id) != int(item.education_major_id):
                return False
            row_sub = (
                int(row.education_sub_major_id)
                if row.education_sub_major_id is not None
                else None
            )
            return row_sub == (
                int(sub_major_id) if sub_major_id is not None else None
            )

        if any(_row_matches(row) for row in existing_rows):
            skipped_existing += 1
            continue

        if existing_rows:
            for row in existing_rows:
                db.delete(row)
            db.flush()
            db.add(
                ProgramEducationMajorMapping(
                    program_id=item.program_id,
                    education_major_id=item.education_major_id,
                    education_sub_major_id=sub_major_id,
                )
            )
            applied += 1
            continue

        db.add(
            ProgramEducationMajorMapping(
                program_id=item.program_id,
                education_major_id=item.education_major_id,
                education_sub_major_id=sub_major_id,
            )
        )
        applied += 1

    if applied:
        db.commit()
    else:
        db.rollback()

    skipped = skipped_existing + skipped_duplicate_in_request
    return ProgramMappingBulkApplyResponse(
        applied=applied,
        skipped=skipped,
        skipped_existing=skipped_existing,
        skipped_duplicate_in_request=skipped_duplicate_in_request,
        errors=errors,
    )
