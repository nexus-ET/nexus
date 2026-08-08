from __future__ import annotations

from datetime import date, datetime, timedelta
from app.utils.timezone import utc_now

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.academia_institution import Campus, College, Institution
from app.models.academia_wizard import InstitutionIntake
from app.models.calendar_intake_alert import CalendarIntakeAlertLog
from app.models.level import Level
from app.schemas.academic_calendar import (
    CalendarIntakeAlertRead,
    InstitutionIntakeHierarchyResponse,
    InstitutionIntakeRead,
    IntakeEntityConfigureRequest,
    IntakeHierarchyEntityNode,
    validate_intake_date_sequence,
)
from app.services.academic_calendar_service import (
    _display_name,
    _get_institution,
    _get_template,
    intake_to_read,
    sync_intake_status,
)
from app.services.settings_service import get_int_setting

ENTITY_TYPES = ("institution", "campus", "college")
CALENDAR_INTAKE_ADVANCE_DAYS_KEY = "CALENDAR_INTAKE_ADVANCE_DAYS"
DEFAULT_ADVANCE_DAYS = 60


def _normalize_level_ids(level_ids: list[int] | None) -> frozenset[int]:
    return frozenset(int(value) for value in (level_ids or []) if value is not None)


def _entity_campus_id(entity_type: str, entity_id: int) -> int | None:
    if entity_type == "campus":
        return entity_id
    if entity_type == "college":
        return None
    return None


def _resolve_entity(
    db: Session, institution_id: int, entity_type: str, entity_id: int
) -> tuple[str, int, str]:
    institution = _get_institution(db, institution_id)
    if entity_type == "institution":
        if entity_id != institution.id:
            raise HTTPException(status_code=400, detail="Invalid institution entity.")
        return entity_type, entity_id, institution.name

    if entity_type == "campus":
        campus = (
            db.query(Campus)
            .filter(Campus.id == entity_id, Campus.institution_id == institution_id)
            .first()
        )
        if not campus:
            raise HTTPException(status_code=404, detail="Campus not found.")
        return entity_type, entity_id, campus.name

    if entity_type == "college":
        college = (
            db.query(College)
            .filter(College.id == entity_id, College.institution_id == institution_id)
            .first()
        )
        if not college:
            raise HTTPException(status_code=404, detail="College not found.")
        return entity_type, entity_id, college.name

    raise HTTPException(status_code=400, detail="Invalid entity_type.")


def _list_child_entities(
    db: Session, institution_id: int, entity_type: str, entity_id: int
) -> list[tuple[str, int, str, str | None, int | None]]:
    """Return (entity_type, entity_id, name, parent_type, parent_id) tuples."""
    if entity_type == "institution":
        # Colleges always appear under the university. Campuses linked to a
        # college are shown under that college; unlinked campuses stay as direct
        # university children so they remain visible and cascadeable.
        colleges = (
            db.query(College)
            .filter(College.institution_id == institution_id)
            .order_by(College.sort_order.asc(), College.name.asc())
            .all()
        )
        linked_campus_ids = {college.campus_id for college in colleges if college.campus_id}
        children: list[tuple[str, int, str, str | None, int | None]] = [
            ("college", college.id, college.name, "institution", institution_id)
            for college in colleges
        ]
        campus_query = db.query(Campus).filter(Campus.institution_id == institution_id)
        if linked_campus_ids:
            campus_query = campus_query.filter(~Campus.id.in_(linked_campus_ids))
        unlinked_campuses = campus_query.order_by(
            Campus.sort_order.asc(), Campus.name.asc()
        ).all()
        children.extend(
            ("campus", campus.id, campus.name, "institution", institution_id)
            for campus in unlinked_campuses
        )
        return children

    if entity_type == "college":
        college = (
            db.query(College)
            .filter(College.id == entity_id, College.institution_id == institution_id)
            .first()
        )
        if not college or not college.campus_id:
            return []
        campus = (
            db.query(Campus)
            .filter(
                Campus.id == college.campus_id,
                Campus.institution_id == institution_id,
            )
            .first()
        )
        if not campus:
            return []
        return [("campus", campus.id, campus.name, "college", college.id)]

    return []


def _list_descendant_entities(
    db: Session, institution_id: int, entity_type: str, entity_id: int
) -> list[tuple[str, int, str, str | None, int | None]]:
    """Return all linked descendants used by calendar cascade."""
    if entity_type == "institution":
        # Cascade must reach every college and every campus for the university,
        # including campuses that are not linked to a college.
        colleges = _list_child_entities(db, institution_id, entity_type, entity_id)
        college_nodes = [row for row in colleges if row[0] == "college"]
        campuses = (
            db.query(Campus)
            .filter(Campus.institution_id == institution_id)
            .order_by(Campus.sort_order.asc(), Campus.name.asc())
            .all()
        )
        campus_nodes = [
            ("campus", campus.id, campus.name, "institution", institution_id)
            for campus in campuses
        ]
        return [*college_nodes, *campus_nodes]

    return _list_child_entities(db, institution_id, entity_type, entity_id)


def _intakes_for_entity(
    db: Session, institution_id: int, entity_type: str, entity_id: int
) -> list[InstitutionIntake]:
    return (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.entity_type == entity_type,
            InstitutionIntake.entity_id == entity_id,
        )
        .order_by(InstitutionIntake.year.desc(), InstitutionIntake.sort_order.asc())
        .all()
    )


def _entity_has_override(db: Session, institution_id: int, entity_type: str, entity_id: int) -> bool:
    return (
        db.query(InstitutionIntake.id)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.entity_type == entity_type,
            InstitutionIntake.entity_id == entity_id,
            InstitutionIntake.is_overridden.is_(True),
        )
        .first()
        is not None
    )


def _build_hierarchy_node(
    db: Session,
    institution_id: int,
    entity_type: str,
    entity_id: int,
    name: str,
    *,
    parent_entity_type: str | None = None,
    parent_entity_id: int | None = None,
) -> IntakeHierarchyEntityNode:
    intakes = _intakes_for_entity(db, institution_id, entity_type, entity_id)
    child_specs = _list_child_entities(db, institution_id, entity_type, entity_id)
    children = [
        _build_hierarchy_node(
            db,
            institution_id,
            child_type,
            child_id,
            child_name,
            parent_entity_type=parent_type,
            parent_entity_id=parent_id,
        )
        for child_type, child_id, child_name, parent_type, parent_id in child_specs
    ]
    return IntakeHierarchyEntityNode(
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        name=name,
        parent_entity_type=parent_entity_type,  # type: ignore[arg-type]
        parent_entity_id=parent_entity_id,
        is_overridden=_entity_has_override(db, institution_id, entity_type, entity_id),
        intake_count=len(intakes),
        children=children,
    )


def get_institution_intake_hierarchy(
    db: Session, institution_id: int
) -> InstitutionIntakeHierarchyResponse:
    institution = _get_institution(db, institution_id)
    root = _build_hierarchy_node(
        db, institution_id, "institution", institution.id, institution.name
    )
    return InstitutionIntakeHierarchyResponse(
        institution_id=institution.id,
        institution_name=institution.name,
        root=root,
    )


def _create_intake_from_template_config(
    db: Session,
    *,
    institution_id: int,
    entity_type: str,
    entity_id: int,
    template_id: int,
    year: int,
    config: dict | object,
    level_ids: list[int],
    parent_intake_id: int | None,
    sort_order: int,
) -> InstitutionIntake:
    term_name = config["term_name"] if isinstance(config, dict) else config.term_name
    intake_type = config["intake_type"] if isinstance(config, dict) else config.intake_type
    campus_id = _entity_campus_id(entity_type, entity_id)
    record = InstitutionIntake(
        institution_id=institution_id,
        campus_id=campus_id,
        entity_type=entity_type,
        entity_id=entity_id,
        template_id=template_id,
        parent_intake_id=parent_intake_id,
        term_name=term_name,
        year=year,
        name=f"{term_name} {year}",
        intake_type=intake_type,
        level_ids=list(level_ids),
        status="Draft",
        is_active=False,
        is_overridden=False,
        sort_order=sort_order,
    )
    db.add(record)
    flag_modified(record, "level_ids")
    return record


def configure_entity_intakes(
    db: Session, institution_id: int, payload: IntakeEntityConfigureRequest
) -> list[InstitutionIntakeRead]:
    _resolve_entity(db, institution_id, payload.entity_type, payload.entity_id)
    template = _get_template(db, payload.template_id)
    year = payload.year or date.today().year
    all_configs = template.default_intake_configs or []
    if not all_configs:
        raise HTTPException(status_code=400, detail="Template has no intake configurations.")
    requested_terms = set(payload.term_names or [])
    configs = [
        (index, config)
        for index, config in enumerate(all_configs)
        if not requested_terms
        or (config["term_name"] if isinstance(config, dict) else config.term_name)
        in requested_terms
    ]
    configured_terms = {
        config["term_name"] if isinstance(config, dict) else config.term_name
        for _, config in configs
    }
    if requested_terms and configured_terms != requested_terms:
        raise HTTPException(
            status_code=400,
            detail="One or more selected terms are not part of this template.",
        )
    valid_level_ids = {
        row[0]
        for row in db.query(Level.id).filter(Level.id.in_(payload.level_ids)).all()
    }
    if valid_level_ids != set(payload.level_ids):
        raise HTTPException(status_code=400, detail="One or more selected levels are invalid.")

    requested_levels = _normalize_level_ids(payload.level_ids)

    # Different templates may coexist in the same year when they cover different levels
    # (e.g. Semester for Undergraduate + Trimester for Graduate). Block only when the
    # selected levels already use another template for this entity/year.
    other_template_rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.entity_type == payload.entity_type,
            InstitutionIntake.entity_id == payload.entity_id,
            InstitutionIntake.year == year,
            InstitutionIntake.template_id.isnot(None),
            InstitutionIntake.template_id != template.id,
        )
        .all()
    )
    other_template_overlap = [
        row
        for row in other_template_rows
        if _normalize_level_ids(row.level_ids) & requested_levels
    ]
    if other_template_overlap:
        conflict_levels = sorted(
            {
                int(level_id)
                for row in other_template_overlap
                for level_id in (row.level_ids or [])
                if level_id is not None and int(level_id) in requested_levels
            }
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Year {year} already has intake calendars from a different academic template "
                f"for level_ids={conflict_levels}. The same level cannot use two calendar "
                "systems in one year. Choose different levels, or replace that level's "
                "existing calendar before configuring another template."
            ),
        )

    existing_rows = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.entity_type == payload.entity_type,
            InstitutionIntake.entity_id == payload.entity_id,
            InstitutionIntake.template_id == template.id,
            InstitutionIntake.year == year,
            InstitutionIntake.term_name.in_(configured_terms),
        )
        .all()
    )
    exact_rows = [
        row
        for row in existing_rows
        if _normalize_level_ids(row.level_ids) == requested_levels
    ]
    partial_overlap = [
        row
        for row in existing_rows
        if (_normalize_level_ids(row.level_ids) & requested_levels)
        and _normalize_level_ids(row.level_ids) != requested_levels
    ]
    if partial_overlap:
        conflict_levels = sorted(
            {
                int(level_id)
                for row in partial_overlap
                for level_id in (row.level_ids or [])
                if level_id is not None
            }
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Intakes for this entity, template, and overlapping level(s) ({year}) "
                f"already exist (conflicting level_ids={conflict_levels}). "
                "Use different levels for a separate calendar, delete the shared calendar "
                "first, or update the existing intake dates."
            ),
        )

    # Idempotent: reuse exact level-set rows; only create missing terms.
    existing_by_term = {
        (row.term_name or "").strip(): row
        for row in exact_rows
        if (row.term_name or "").strip()
    }
    created: list[InstitutionIntake] = []
    parent_by_term: dict[str, InstitutionIntake] = dict(existing_by_term)
    configs_to_create = [
        (index, config)
        for index, config in configs
        if (
            (config["term_name"] if isinstance(config, dict) else config.term_name) or ""
        ).strip()
        not in parent_by_term
    ]

    for index, config in configs_to_create:
        term_name = config["term_name"] if isinstance(config, dict) else config.term_name
        parent = _create_intake_from_template_config(
            db,
            institution_id=institution_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            template_id=template.id,
            year=year,
            config=config,
            level_ids=payload.level_ids,
            parent_intake_id=None,
            sort_order=index,
        )
        created.append(parent)
        parent_by_term[term_name] = parent
        parent.cascade_to_children = bool(payload.cascade_to_children)

    db.flush()

    if payload.cascade_to_children:
        child_entities = _list_descendant_entities(
            db, institution_id, payload.entity_type, payload.entity_id
        )
        for child_type, child_id, _name, _parent_type, _parent_id in child_entities:
            for index, config in configs:
                term_name = config["term_name"] if isinstance(config, dict) else config.term_name
                parent_intake = parent_by_term[term_name]
                parent_levels = _normalize_level_ids(parent_intake.level_ids)
                child_candidates = (
                    db.query(InstitutionIntake)
                    .filter(
                        InstitutionIntake.institution_id == institution_id,
                        InstitutionIntake.entity_type == child_type,
                        InstitutionIntake.entity_id == child_id,
                        InstitutionIntake.template_id == template.id,
                        InstitutionIntake.year == year,
                        InstitutionIntake.term_name == term_name,
                    )
                    .all()
                )
                existing_child = next(
                    (
                        row
                        for row in child_candidates
                        if _normalize_level_ids(row.level_ids) == parent_levels
                    ),
                    None,
                )
                if existing_child:
                    if existing_child.parent_intake_id != parent_intake.id:
                        existing_child.parent_intake_id = parent_intake.id
                    continue
                child = _create_intake_from_template_config(
                    db,
                    institution_id=institution_id,
                    entity_type=child_type,
                    entity_id=child_id,
                    template_id=template.id,
                    year=year,
                    config=config,
                    level_ids=payload.level_ids,
                    parent_intake_id=parent_intake.id,
                    sort_order=index,
                )
                created.append(child)

    db.commit()
    # Prefer stable order matching template config order; include cascade children.
    ordered: list[InstitutionIntake] = []
    seen_ids: set[int] = set()
    for _index, config in configs:
        term_name = config["term_name"] if isinstance(config, dict) else config.term_name
        row = parent_by_term.get(term_name)
        if row and row.id not in seen_ids:
            ordered.append(row)
            seen_ids.add(row.id)
    for row in created:
        if row.id not in seen_ids:
            ordered.append(row)
            seen_ids.add(row.id)
    for row in ordered:
        db.refresh(row)
    return [intake_to_read(row) for row in ordered]


def _parent_entity(entity_type: str, entity_id: int, institution_id: int) -> tuple[str, int] | None:
    if entity_type == "college":
        return ("campus", entity_id)
    if entity_type == "campus":
        return ("institution", institution_id)
    return None


def reset_intake_to_parent(
    db: Session, institution_id: int, intake_id: int
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
    if not record.parent_intake_id:
        raise HTTPException(status_code=400, detail="This intake has no parent template to reset from.")

    parent = (
        db.query(InstitutionIntake)
        .filter(InstitutionIntake.id == record.parent_intake_id)
        .first()
    )
    if not parent:
        raise HTTPException(status_code=404, detail="Parent intake not found.")

    record.application_deadline = parent.application_deadline
    record.check_in_date = parent.check_in_date
    record.orientation_date = parent.orientation_date
    record.class_start_date = parent.class_start_date
    record.level_ids = list(parent.level_ids or [])
    flag_modified(record, "level_ids")
    record.start_date = parent.start_date
    record.end_date = parent.end_date
    record.intake_type = parent.intake_type
    record.status = parent.status
    record.is_active = parent.is_active
    record.is_overridden = False
    record.name = _display_name(record)
    db.commit()
    db.refresh(record)
    return intake_to_read(record)


def _copy_calendar_fields_from_parent(parent: InstitutionIntake, child: InstitutionIntake) -> None:
    child.application_deadline = parent.application_deadline
    child.check_in_date = parent.check_in_date
    child.orientation_date = parent.orientation_date
    child.class_start_date = parent.class_start_date
    child.start_date = parent.start_date or parent.class_start_date
    child.end_date = parent.end_date
    child.intake_type = parent.intake_type
    child.status = parent.status
    child.is_active = parent.is_active
    child.level_ids = list(parent.level_ids or [])
    flag_modified(child, "level_ids")
    child.is_overridden = False
    child.name = _display_name(child)


def _cascade_intake_dates_to_children(
    db: Session, institution_id: int, parent: InstitutionIntake
) -> None:
    if not parent.entity_type or parent.entity_id is None:
        return

    descendants = _list_descendant_entities(
        db, institution_id, parent.entity_type, parent.entity_id
    )
    if not descendants:
        return

    existing_children = (
        db.query(InstitutionIntake)
        .filter(
            InstitutionIntake.institution_id == institution_id,
            InstitutionIntake.parent_intake_id == parent.id,
        )
        .all()
    )
    child_by_entity = {
        (row.entity_type, row.entity_id): row for row in existing_children
    }

    for child_type, child_id, _name, _parent_type, _parent_id in descendants:
        child = child_by_entity.get((child_type, child_id))
        if child is None:
            candidates = (
                db.query(InstitutionIntake)
                .filter(
                    InstitutionIntake.institution_id == institution_id,
                    InstitutionIntake.entity_type == child_type,
                    InstitutionIntake.entity_id == child_id,
                    InstitutionIntake.template_id == parent.template_id,
                    InstitutionIntake.year == parent.year,
                    InstitutionIntake.term_name == parent.term_name,
                )
                .all()
            )
            parent_levels = _normalize_level_ids(parent.level_ids)
            child = next(
                (
                    row
                    for row in candidates
                    if _normalize_level_ids(row.level_ids) == parent_levels
                ),
                None,
            )
            if child:
                child.parent_intake_id = parent.id

        if child is None:
            child = InstitutionIntake(
                institution_id=institution_id,
                campus_id=_entity_campus_id(child_type, child_id),
                entity_type=child_type,
                entity_id=child_id,
                template_id=parent.template_id,
                parent_intake_id=parent.id,
                term_name=parent.term_name,
                year=parent.year,
                name=_display_name(parent),
                intake_type=parent.intake_type or "Fixed",
                status=parent.status or "Draft",
                is_active=False,
                is_overridden=False,
                sort_order=parent.sort_order or 0,
                level_ids=list(parent.level_ids or []),
            )
            db.add(child)

        # Keep explicit child customizations; still ensure parent link above.
        if child.is_overridden:
            continue

        _copy_calendar_fields_from_parent(parent, child)


def update_hierarchical_intake(
    db: Session,
    institution_id: int,
    intake_id: int,
    payload: dict,
) -> InstitutionIntakeRead:
    from app.schemas.academic_calendar import InstitutionIntakeUpdate

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

    update = InstitutionIntakeUpdate.model_validate(payload)
    cascade_to_children = bool(update.cascade_to_children) if update.cascade_to_children is not None else None
    if update.level_ids is not None:
        valid_level_ids = {
            row[0]
            for row in db.query(Level.id).filter(Level.id.in_(update.level_ids)).all()
        }
        if valid_level_ids != set(update.level_ids):
            raise HTTPException(status_code=400, detail="One or more selected levels are invalid.")
    parent_id = record.parent_intake_id
    for field, value in update.model_dump(exclude_unset=True).items():
        if field == "cascade_to_children":
            continue
        if field == "level_ids":
            record.level_ids = list(value or [])
            flag_modified(record, "level_ids")
        else:
            setattr(record, field, value)

    if cascade_to_children is not None:
        record.cascade_to_children = cascade_to_children

    if record.class_start_date and not record.start_date:
        record.start_date = record.class_start_date

    merged_deadline = record.application_deadline
    merged_orientation = record.orientation_date
    merged_class_start = record.class_start_date or record.start_date
    merged_check_in = record.check_in_date
    if merged_deadline or merged_orientation or merged_class_start:
        validate_intake_date_sequence(
            application_deadline=merged_deadline,
            orientation_date=merged_orientation,
            class_start_date=merged_class_start,
            check_in_date=merged_check_in,
            require_mandatory=False,
        )

    if parent_id:
        parent = db.query(InstitutionIntake).filter(InstitutionIntake.id == parent_id).first()
        if parent:
            date_changed = any(
                getattr(record, field) != getattr(parent, field)
                for field in (
                    "application_deadline",
                    "check_in_date",
                    "orientation_date",
                    "class_start_date",
                    "start_date",
                    "end_date",
                    "intake_type",
                    "status",
                )
            )
            level_changed = set(record.level_ids or []) != set(parent.level_ids or [])
            record.is_overridden = date_changed or level_changed
        else:
            record.is_overridden = True
    elif any(
        value is not None
        for value in (
            record.application_deadline,
            record.orientation_date,
            record.class_start_date,
            record.check_in_date,
        )
    ):
        record.is_overridden = False

    if record.status == "Open":
        sync_intake_status(record)
    record.name = _display_name(record)

    if cascade_to_children:
        _cascade_intake_dates_to_children(db, institution_id, record)

    db.commit()
    db.refresh(record)
    return intake_to_read(record)


def list_intakes_for_entity(
    db: Session,
    institution_id: int,
    entity_type: str,
    entity_id: int,
    *,
    year: int | None = None,
) -> list[InstitutionIntakeRead]:
    _resolve_entity(db, institution_id, entity_type, entity_id)
    rows = _intakes_for_entity(db, institution_id, entity_type, entity_id)
    if year is not None:
        rows = [row for row in rows if row.year == year]
    return [intake_to_read(row) for row in rows]


def _entity_display_name(db: Session, entity_type: str, entity_id: int) -> str:
    if entity_type == "institution":
        row = db.query(Institution).filter(Institution.id == entity_id).first()
        return row.name if row else f"Institution #{entity_id}"
    if entity_type == "campus":
        row = db.query(Campus).filter(Campus.id == entity_id).first()
        return row.name if row else f"Campus #{entity_id}"
    row = db.query(College).filter(College.id == entity_id).first()
    return row.name if row else f"College #{entity_id}"


def _next_term_window_start(db: Session, advance_days: int) -> date:
    return date.today() + timedelta(days=advance_days)


def _collect_entity_targets(db: Session, institution: Institution) -> list[tuple[str, int, str]]:
    targets: list[tuple[str, int, str]] = [( "institution", institution.id, institution.name)]
    campuses = db.query(Campus).filter(Campus.institution_id == institution.id).all()
    for campus in campuses:
        targets.append(("campus", campus.id, campus.name))
        colleges = db.query(College).filter(College.campus_id == campus.id).all()
        for college in colleges:
            targets.append(("college", college.id, college.name))
    return targets


def process_calendar_intake_reminders(db: Session) -> int:
    advance_days = get_int_setting(db, CALENDAR_INTAKE_ADVANCE_DAYS_KEY, DEFAULT_ADVANCE_DAYS)
    today = date.today()
    alerts_created = 0

    institutions = db.query(Institution).order_by(Institution.id.asc()).all()
    for institution in institutions:
        inst_intakes = _intakes_for_entity(db, institution.id, "institution", institution.id)
        upcoming = sorted(
            [
                row
                for row in inst_intakes
                if row.class_start_date and row.class_start_date > today
            ],
            key=lambda row: row.class_start_date,
        )
        if not upcoming:
            continue

        next_term = upcoming[0]
        if not next_term.class_start_date:
            continue
        days_until = (next_term.class_start_date - today).days
        if days_until > advance_days:
            continue

        term_name = (next_term.term_name or next_term.name or "Term").strip()
        year = next_term.year or next_term.class_start_date.year

        for entity_type, entity_id, _entity_name in _collect_entity_targets(db, institution):
            entity_intakes = _intakes_for_entity(db, institution.id, entity_type, entity_id)
            has_complete_term = any(
                (row.term_name or row.name) == term_name
                and row.year == year
                and row.application_deadline is not None
                and row.class_start_date is not None
                for row in entity_intakes
            )
            if has_complete_term:
                continue

            existing_alert = (
                db.query(CalendarIntakeAlertLog)
                .filter(
                    CalendarIntakeAlertLog.institution_id == institution.id,
                    CalendarIntakeAlertLog.entity_type == entity_type,
                    CalendarIntakeAlertLog.entity_id == entity_id,
                    CalendarIntakeAlertLog.term_name == term_name,
                    CalendarIntakeAlertLog.year == year,
                    CalendarIntakeAlertLog.alert_type == "missing_intake",
                )
                .first()
            )
            if existing_alert:
                continue

            db.add(
                CalendarIntakeAlertLog(
                    institution_id=institution.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    term_name=term_name,
                    year=year,
                    alert_type="missing_intake",
                    alerted_at=utc_now(),
                )
            )
            alerts_created += 1

    if alerts_created:
        db.commit()
    return alerts_created


def list_calendar_intake_alerts(db: Session, *, limit: int = 20) -> list[CalendarIntakeAlertRead]:
    advance_days = get_int_setting(db, CALENDAR_INTAKE_ADVANCE_DAYS_KEY, DEFAULT_ADVANCE_DAYS)
    today = date.today()
    rows = (
        db.query(CalendarIntakeAlertLog, Institution)
        .join(Institution, Institution.id == CalendarIntakeAlertLog.institution_id)
        .order_by(CalendarIntakeAlertLog.alerted_at.desc())
        .limit(limit)
        .all()
    )
    alerts: list[CalendarIntakeAlertRead] = []
    for log, institution in rows:
        entity_name = _entity_display_name(db, log.entity_type, log.entity_id)
        intake = (
            db.query(InstitutionIntake)
            .filter(
                InstitutionIntake.institution_id == log.institution_id,
                InstitutionIntake.entity_type == log.entity_type,
                InstitutionIntake.entity_id == log.entity_id,
                InstitutionIntake.term_name == log.term_name,
                InstitutionIntake.year == log.year,
            )
            .order_by(InstitutionIntake.class_start_date.asc().nullslast())
            .first()
        )
        class_start = intake.class_start_date if intake else None
        days_until = (class_start - today).days if class_start else None
        if days_until is not None and days_until > advance_days:
            continue
        alerts.append(
            CalendarIntakeAlertRead(
                id=log.id,
                institution_id=institution.id,
                institution_name=institution.name,
                entity_type=log.entity_type,  # type: ignore[arg-type]
                entity_id=log.entity_id,
                entity_name=entity_name,
                term_name=log.term_name,
                year=log.year,
                class_start_date=class_start,
                days_until_start=days_until,
                alert_type=log.alert_type,
                alerted_at=log.alerted_at.isoformat() if log.alerted_at else None,
                link_path=f"/academia/institutions/edit/{institution.id}",
            )
        )
    return alerts
