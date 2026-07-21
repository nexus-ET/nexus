from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.academic_calendar import GlobalAcademicTemplate, ProgramIntakeAssignment
from app.models.academia_institution import Institution
from app.models.academia_wizard import InstitutionIntake
from app.models.program import Program
from app.schemas.academic_calendar import (
    GlobalAcademicTemplateRead,
    InstitutionIntakeCalendarResponse,
    InstitutionIntakeCreate,
    InstitutionIntakeRead,
    InstitutionIntakeUpdate,
    IntakeBulkUpdateItem,
    IntakeSetupRequest,
    IntakeRolloverRequest,
)


def _display_name(intake: InstitutionIntake) -> str:
    term = (intake.term_name or intake.name or "Term").strip()
    if intake.year:
        return f"{term} {intake.year}"
    return term


def intake_to_read(intake: InstitutionIntake) -> InstitutionIntakeRead:
    return InstitutionIntakeRead(
        id=intake.id,
        institution_id=intake.institution_id,
        campus_id=intake.campus_id,
        entity_type=intake.entity_type,
        entity_id=intake.entity_id,
        template_id=intake.template_id,
        parent_intake_id=intake.parent_intake_id,
        name=intake.name,
        term_name=intake.term_name,
        year=intake.year,
        intake_type=intake.intake_type,
        status=intake.status,
        intake_code=intake.intake_code,
        start_date=intake.start_date,
        end_date=intake.end_date,
        application_deadline=intake.application_deadline,
        check_in_date=intake.check_in_date,
        orientation_date=intake.orientation_date,
        class_start_date=intake.class_start_date,
        level_ids=intake.level_ids or [],
        is_overridden=intake.is_overridden,
        cascade_to_children=bool(getattr(intake, "cascade_to_children", False)),
        is_active=intake.is_active,
        sort_order=intake.sort_order,
        display_name=_display_name(intake),
    )


def _get_institution(db: Session, institution_id: int) -> Institution:
    institution = db.query(Institution).filter(Institution.id == institution_id).first()
    if not institution:
        raise HTTPException(status_code=404, detail="Institution not found.")
    return institution


def _get_template(db: Session, template_id: int) -> GlobalAcademicTemplate:
    template = (
        db.query(GlobalAcademicTemplate)
        .filter(GlobalAcademicTemplate.id == template_id, GlobalAcademicTemplate.is_active.is_(True))
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Academic template not found.")
    return template


def _validate_fixed_fields(
    *,
    intake_type: str,
    start_date: date | None,
    end_date: date | None,
    application_deadline: date | None,
) -> None:
    if intake_type != "Fixed":
        return
    if not start_date or not end_date or not application_deadline:
        raise HTTPException(
            status_code=400,
            detail="Fixed intakes require start_date, end_date, and application_deadline.",
        )
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")
    if application_deadline > end_date:
        raise HTTPException(
            status_code=400,
            detail="application_deadline must be on or before end_date.",
        )


def sync_intake_status(intake: InstitutionIntake, *, today: date | None = None) -> bool:
    """Apply Fixed/Rolling status rules. Returns True if status changed."""
    current = today or date.today()
    if intake.intake_type == "Fixed" and intake.end_date and intake.status != "Closed":
        if current > intake.end_date:
            intake.status = "Closed"
            intake.is_active = False
            return True
    return False


def sync_institution_intake_statuses(db: Session, institution_id: int) -> None:
    rows = (
        db.query(InstitutionIntake)
        .filter(InstitutionIntake.institution_id == institution_id)
        .all()
    )
    changed = any(sync_intake_status(row) for row in rows)
    if changed:
        db.commit()


def list_global_templates(db: Session) -> list[GlobalAcademicTemplateRead]:
    rows = (
        db.query(GlobalAcademicTemplate)
        .filter(GlobalAcademicTemplate.is_active.is_(True))
        .order_by(GlobalAcademicTemplate.sort_order.asc(), GlobalAcademicTemplate.name.asc())
        .all()
    )
    return [GlobalAcademicTemplateRead.model_validate(row) for row in rows]


def list_institution_intakes(
    db: Session, institution_id: int, *, year: int | None = None
) -> list[InstitutionIntakeRead]:
    _get_institution(db, institution_id)
    sync_institution_intake_statuses(db, institution_id)
    q = db.query(InstitutionIntake).filter(InstitutionIntake.institution_id == institution_id)
    if year is not None:
        q = q.filter(InstitutionIntake.year == year)
    rows = q.order_by(
        InstitutionIntake.year.desc(),
        InstitutionIntake.sort_order.asc(),
        InstitutionIntake.term_name.asc(),
    ).all()
    return [intake_to_read(row) for row in rows]


def get_institution_intake_calendar(
    db: Session, institution_id: int
) -> InstitutionIntakeCalendarResponse:
    intakes = list_institution_intakes(db, institution_id)
    years = sorted({item.year for item in intakes if item.year is not None}, reverse=True)
    grouped: dict[int, list[InstitutionIntakeRead]] = {}
    for intake in intakes:
        if intake.year is None:
            continue
        grouped.setdefault(intake.year, []).append(intake)
    return InstitutionIntakeCalendarResponse(
        institution_id=institution_id,
        years=years,
        intakes_by_year=grouped,
    )


def setup_institution_intakes_from_template(
    db: Session, institution_id: int, payload: IntakeSetupRequest
) -> list[InstitutionIntakeRead]:
    _get_institution(db, institution_id)
    template = _get_template(db, payload.template_id)
    year = payload.year or date.today().year
    configs = template.default_intake_configs or []
    if not configs:
        raise HTTPException(status_code=400, detail="Template has no intake configurations.")

    existing = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.template_id == template.id,
            InstitutionIntake.year == year,
        )
        .count()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Intakes for {template.name} ({year}) already exist. Use roll-over or edit instead.",
        )

    created: list[InstitutionIntake] = []
    for index, config in enumerate(configs):
        term_name = config["term_name"] if isinstance(config, dict) else config.term_name
        intake_type = config["intake_type"] if isinstance(config, dict) else config.intake_type
        record = InstitutionIntake(
            institution_id=institution_id,
            campus_id=None,
            entity_type="institution",
            entity_id=institution_id,
            template_id=template.id,
            term_name=term_name,
            year=year,
            name=f"{term_name} {year}",
            intake_type=intake_type,
            status="Draft",
            is_active=False,
            sort_order=index,
        )
        db.add(record)
        created.append(record)

    db.commit()
    for row in created:
        db.refresh(row)
    return [intake_to_read(row) for row in created]


def rollover_institution_intakes(
    db: Session, institution_id: int, payload: IntakeRolloverRequest
) -> list[InstitutionIntakeRead]:
    _get_institution(db, institution_id)
    all_intakes = (
        db.query(InstitutionIntake)
        .filter(InstitutionIntake.institution_id == institution_id)
        .order_by(InstitutionIntake.year.desc(), InstitutionIntake.sort_order.asc())
        .all()
    )
    if not all_intakes:
        raise HTTPException(status_code=400, detail="No intakes found to roll over.")

    source_year = payload.source_year
    if source_year is None:
        source_year = max(row.year for row in all_intakes if row.year is not None)
    target_year = payload.target_year or (source_year + 1)

    source_rows = [row for row in all_intakes if row.year == source_year]
    if not source_rows:
        raise HTTPException(status_code=404, detail=f"No intakes found for year {source_year}.")

    existing_target = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.year == target_year,
        )
        .count()
    )
    if existing_target:
        raise HTTPException(
            status_code=409,
            detail=f"Intakes for {target_year} already exist.",
        )

    cloned: list[InstitutionIntake] = []
    for row in source_rows:
        term_name = row.term_name or row.name
        clone = InstitutionIntake(
            institution_id=institution_id,
            campus_id=row.campus_id,
            template_id=row.template_id,
            parent_intake_id=row.id,
            term_name=term_name,
            year=target_year,
            name=f"{term_name} {target_year}",
            intake_type=row.intake_type,
            status="Draft",
            intake_code=row.intake_code,
            start_date=None,
            end_date=None,
            application_deadline=None,
            level_ids=list(row.level_ids or []),
            is_active=False,
            sort_order=row.sort_order,
        )
        db.add(clone)
        cloned.append(clone)

    db.commit()
    for row in cloned:
        db.refresh(row)
    return [intake_to_read(row) for row in cloned]


def bulk_update_institution_intakes(
    db: Session, institution_id: int, items: list[IntakeBulkUpdateItem]
) -> list[InstitutionIntakeRead]:
    _get_institution(db, institution_id)
    ids = [item.id for item in items]
    rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.id.in_(ids),
        )
        .all()
    )
    row_map = {row.id: row for row in rows}
    if len(row_map) != len(ids):
        raise HTTPException(status_code=404, detail="One or more intakes were not found.")

    updated: list[InstitutionIntake] = []
    for item in items:
        record = row_map[item.id]
        if item.start_date is not None:
            record.start_date = item.start_date
        if item.end_date is not None:
            record.end_date = item.end_date
        if item.application_deadline is not None:
            record.application_deadline = item.application_deadline
        if item.status is not None:
            record.status = item.status
            record.is_active = item.status == "Open"
        _validate_fixed_fields(
            intake_type=record.intake_type,
            start_date=record.start_date,
            end_date=record.end_date,
            application_deadline=record.application_deadline,
        )
        if record.status == "Open" and record.intake_type == "Fixed":
            sync_intake_status(record)
        record.name = _display_name(record)
        updated.append(record)

    db.commit()
    return [intake_to_read(row) for row in updated]


def create_institution_intake(
    db: Session, institution_id: int, payload: InstitutionIntakeCreate
) -> InstitutionIntakeRead:
    _get_institution(db, institution_id)
    _validate_fixed_fields(
        intake_type=payload.intake_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        application_deadline=payload.application_deadline,
    )
    status = payload.status
    if payload.intake_type == "Fixed" and payload.end_date and date.today() > payload.end_date:
        status = "Closed"

    record = InstitutionIntake(
        institution_id=institution_id,
        campus_id=payload.campus_id,
        entity_type=payload.entity_type or ("campus" if payload.campus_id else "institution"),
        entity_id=payload.entity_id or payload.campus_id or institution_id,
        template_id=payload.template_id,
        parent_intake_id=payload.parent_intake_id,
        term_name=payload.term_name.strip(),
        year=payload.year,
        name=f"{payload.term_name.strip()} {payload.year}",
        intake_type=payload.intake_type,
        status=status,
        intake_code=payload.intake_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        application_deadline=payload.application_deadline,
        level_ids=payload.level_ids,
        is_active=status == "Open",
        sort_order=payload.sort_order,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return intake_to_read(record)


def update_institution_intake(
    db: Session, institution_id: int, intake_id: int, payload: InstitutionIntakeUpdate
) -> InstitutionIntakeRead:
    record = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.id == intake_id,
            InstitutionIntake.institution_id == institution_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Intake not found.")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "level_ids":
            from sqlalchemy.orm.attributes import flag_modified

            record.level_ids = list(value or [])
            flag_modified(record, "level_ids")
        else:
            setattr(record, key, value)

    if record.term_name and record.year:
        record.name = f"{record.term_name.strip()} {record.year}"

    if record.status == "Closed":
        record.is_active = False
    elif record.status == "Open":
        record.is_active = True

    _validate_fixed_fields(
        intake_type=record.intake_type,
        start_date=record.start_date,
        end_date=record.end_date,
        application_deadline=record.application_deadline,
    )

    if record.intake_type == "Fixed" and record.status != "Closed":
        sync_intake_status(record)

    db.commit()
    db.refresh(record)
    return intake_to_read(record)


def delete_institution_intake(db: Session, institution_id: int, intake_id: int) -> None:
    record = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.id == intake_id,
            InstitutionIntake.institution_id == institution_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Intake not found.")

    # A cascaded calendar can have campus/college descendants. The database FK
    # does not consistently cascade in older installations, so remove the full
    # mapped subtree explicitly and clear self-references first.
    rows = (
        db.query(InstitutionIntake.id, InstitutionIntake.parent_intake_id)
        .filter(InstitutionIntake.institution_id == institution_id)
        .all()
    )
    descendants = {intake_id}
    changed = True
    while changed:
        changed = False
        for row_id, parent_id in rows:
            if parent_id in descendants and row_id not in descendants:
                descendants.add(row_id)
                changed = True

    db.query(InstitutionIntake).filter(
        InstitutionIntake.id.in_(descendants)
    ).update(
        {InstitutionIntake.parent_intake_id: None},
        synchronize_session=False,
    )
    db.query(InstitutionIntake).filter(
        InstitutionIntake.id.in_(descendants)
    ).delete(synchronize_session=False)
    db.commit()


def list_open_intakes_for_institution(
    db: Session, institution_id: int
) -> list[InstitutionIntakeRead]:
    sync_institution_intake_statuses(db, institution_id)
    rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.status == "Open",
        )
        .order_by(InstitutionIntake.year.desc(), InstitutionIntake.term_name.asc())
        .all()
    )
    return [intake_to_read(row) for row in rows]


def get_program_intake_ids(db: Session, program_id: uuid.UUID) -> list[int]:
    rows = (
        db.query(ProgramIntakeAssignment.institution_intake_id)
        .filter(ProgramIntakeAssignment.program_id == program_id)
        .all()
    )
    return [row[0] for row in rows]


def validate_program_intake_assignments(
    db: Session,
    *,
    program_id: uuid.UUID | None,
    institution_id: int | None,
    intake_ids: list[int] | None,
    is_active: bool,
) -> None:
    if not is_active or not institution_id:
        return
    if not intake_ids:
        raise HTTPException(
            status_code=400,
            detail="Active programs must be assigned at least one Open intake term.",
        )

    sync_institution_intake_statuses(db, institution_id)
    rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.id.in_(intake_ids),
            InstitutionIntake.institution_id == institution_id,
        )
        .all()
    )
    if len(rows) != len(set(intake_ids)):
        raise HTTPException(status_code=400, detail="One or more selected intakes are invalid.")

    open_rows = [row for row in rows if row.status == "Open"]
    if not open_rows:
        raise HTTPException(
            status_code=400,
            detail="At least one assigned intake must have status Open.",
        )


def replace_program_intake_assignments(
    db: Session,
    program_id: uuid.UUID,
    institution_id: int | None,
    intake_ids: list[int] | None,
) -> None:
    if institution_id is None:
        return

    db.query(ProgramIntakeAssignment).filter(
        ProgramIntakeAssignment.program_id == program_id
    ).delete(synchronize_session=False)

    if not intake_ids:
        db.flush()
        return

    rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.id.in_(intake_ids),
            InstitutionIntake.institution_id == institution_id,
        )
        .all()
    )
    if len(rows) != len(set(intake_ids)):
        raise HTTPException(status_code=400, detail="One or more selected intakes are invalid.")

    for intake_id in intake_ids:
        db.add(
            ProgramIntakeAssignment(
                program_id=program_id,
                institution_intake_id=intake_id,
            )
        )
    db.flush()


def enrich_degree_with_intakes(db: Session, program: Program) -> dict:
    intake_ids = get_program_intake_ids(db, program.id)
    institution_id = None
    if intake_ids:
        first = (
            db.query(InstitutionIntake.institution_id)
            .filter(InstitutionIntake.id == intake_ids[0])
            .scalar()
        )
        institution_id = first
    return {"institution_id": institution_id, "intake_ids": intake_ids}
