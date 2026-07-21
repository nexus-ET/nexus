from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_academia_admin
from app.db.database import get_db
from app.models.user import User
from app.schemas.academic_calendar import (
    CalendarIntakeAlertRead,
    GlobalAcademicTemplateRead,
    InstitutionIntakeCalendarResponse,
    InstitutionIntakeCreate,
    InstitutionIntakeHierarchyResponse,
    InstitutionIntakeRead,
    InstitutionIntakeUpdate,
    IntakeBulkUpdateRequest,
    IntakeEntityConfigureRequest,
    IntakeRolloverRequest,
    IntakeSetupRequest,
)
from app.services import academic_calendar_service as calendar_service
from app.services import hierarchical_intake_service as hierarchy_service

router = APIRouter()


@router.get("/academia/academic-templates", response_model=list[GlobalAcademicTemplateRead])
def list_academic_templates(
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.list_global_templates(db)


@router.get(
    "/academia/institutions/{institution_id}/intakes/calendar",
    response_model=InstitutionIntakeCalendarResponse,
)
def get_institution_intake_calendar(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.get_institution_intake_calendar(db, institution_id)


@router.get(
    "/academia/institutions/{institution_id}/intakes",
    response_model=list[InstitutionIntakeRead],
)
def list_institution_intakes(
    institution_id: int,
    year: int | None = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.list_institution_intakes(db, institution_id, year=year)


@router.get(
    "/academia/institutions/{institution_id}/intakes/open",
    response_model=list[InstitutionIntakeRead],
)
def list_open_institution_intakes(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.list_open_intakes_for_institution(db, institution_id)


@router.post(
    "/academia/institutions/{institution_id}/intakes/setup",
    response_model=list[InstitutionIntakeRead],
)
def setup_institution_intakes(
    institution_id: int,
    payload: IntakeSetupRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.setup_institution_intakes_from_template(db, institution_id, payload)


@router.post(
    "/academia/institutions/{institution_id}/intakes/rollover",
    response_model=list[InstitutionIntakeRead],
)
def rollover_institution_intakes(
    institution_id: int,
    payload: IntakeRolloverRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.rollover_institution_intakes(db, institution_id, payload)


@router.put(
    "/academia/institutions/{institution_id}/intakes/bulk",
    response_model=list[InstitutionIntakeRead],
)
def bulk_update_institution_intakes(
    institution_id: int,
    payload: IntakeBulkUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.bulk_update_institution_intakes(db, institution_id, payload.items)


@router.post(
    "/academia/institutions/{institution_id}/intakes",
    response_model=InstitutionIntakeRead,
)
def create_institution_intake(
    institution_id: int,
    payload: InstitutionIntakeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return calendar_service.create_institution_intake(db, institution_id, payload)


@router.put(
    "/academia/institutions/{institution_id}/intakes/{intake_id}",
    response_model=InstitutionIntakeRead,
)
def update_institution_intake(
    institution_id: int,
    intake_id: int,
    payload: InstitutionIntakeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.update_hierarchical_intake(
        db, institution_id, intake_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/academia/institutions/{institution_id}/intakes/{intake_id}")
def delete_institution_intake(
    institution_id: int,
    intake_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    calendar_service.delete_institution_intake(db, institution_id, intake_id)
    return {"ok": True}


@router.get(
    "/academia/institutions/{institution_id}/intakes/hierarchy",
    response_model=InstitutionIntakeHierarchyResponse,
)
def get_institution_intake_hierarchy(
    institution_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.get_institution_intake_hierarchy(db, institution_id)


@router.get(
    "/academia/institutions/{institution_id}/intakes/by-entity",
    response_model=list[InstitutionIntakeRead],
)
def list_entity_intakes(
    institution_id: int,
    entity_type: str = Query(..., pattern="^(institution|campus|college)$"),
    entity_id: int = Query(..., ge=1),
    year: int | None = Query(None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.list_intakes_for_entity(
        db, institution_id, entity_type, entity_id, year=year
    )


@router.post(
    "/academia/institutions/{institution_id}/intakes/configure",
    response_model=list[InstitutionIntakeRead],
)
def configure_entity_intakes(
    institution_id: int,
    payload: IntakeEntityConfigureRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.configure_entity_intakes(db, institution_id, payload)


@router.post(
    "/academia/institutions/{institution_id}/intakes/{intake_id}/reset",
    response_model=InstitutionIntakeRead,
)
def reset_intake_to_parent(
    institution_id: int,
    intake_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.reset_intake_to_parent(db, institution_id, intake_id)


@router.get("/dashboard/calendar-alerts", response_model=list[CalendarIntakeAlertRead])
def list_calendar_alerts(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_academia_admin),
):
    return hierarchy_service.list_calendar_intake_alerts(db, limit=limit)
