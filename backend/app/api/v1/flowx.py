"""FlowX API — country workflows, enrollments, board."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.flowx import (
    FlowxApplicationLookupsResponse,
    FlowxAuditLogRead,
    FlowxBoardResponse,
    FlowxOpsOverviewResponse,
    FlowxCountryDestinationsResponse,
    FlowxCountryGeographyResponse,
    FlowxCountryWorkflowDetail,
    FlowxCountryWorkflowSummary,
    FlowxEnrollRequest,
    FlowxEnrollmentListResponse,
    FlowxEnrollmentRead,
    FlowxJourneyTestResetResponse,
    FlowxJourneyTestSeedResponse,
    FlowxOverrideRequest,
    FlowxPathwayCreate,
    FlowxPathwayRead,
    FlowxProcessLabelUpdateRequest,
    FlowxProcessLabelUpdateResponse,
    FlowxStageUpdate,
    FlowxSubprocessLinkCreate,
    FlowxEnrollmentTrackMoveRequest,
    FlowxTaskCreate,
    FlowxTaskChecklistUpdate,
    FlowxTaskMoveRequest,
    FlowxTaskReorderRequest,
    FlowxTaskTemplateCreate,
    FlowxTaskTemplateRenameRequest,
    FlowxTemplateMoveRequest,
    FlowxTemplateOverrideRequest,
    FlowxTemplateRelinkRequest,
    FlowxWorkflowRuleCreate,
    FlowxWorkflowRuleRead,
)
from app.services import flowx as service
from app.services import flowx_journey_test_seed as journey_test_seed

router = APIRouter(prefix="/flowx", tags=["FlowX"])


@router.get("/countries", response_model=list[FlowxCountryWorkflowSummary])
def list_countries(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    return [FlowxCountryWorkflowSummary(**row) for row in service.list_country_workflows(db)]


@router.get("/ops/overview", response_model=FlowxOpsOverviewResponse)
def ops_overview(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    """Tier-1 global ops dashboard: KPIs, country cards, SLA bottlenecks."""
    return FlowxOpsOverviewResponse(**service.get_ops_overview(db))


@router.get("/master", response_model=FlowxCountryWorkflowDetail)
def get_master_workflow(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_super_admin),
):
    try:
        return FlowxCountryWorkflowDetail(**service.get_master_workflow(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/master/process-labels", response_model=FlowxCountryWorkflowDetail)
def master_rename_process(
    body: FlowxProcessLabelUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_super_admin),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.master_rename_process_label(
                db, stage_key=body.stage_key, label=body.label
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/master/tracks/{track_id}/templates", response_model=FlowxCountryWorkflowDetail)
def master_add_template(
    track_id: UUID,
    body: FlowxTaskTemplateCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_super_admin),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.master_add_task_template(
                db,
                track_id,
                title=body.title,
                description=body.description,
                action_steps=body.action_steps,
                sla_days=body.sla_days,
                parent_template_id=body.parent_template_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/master/templates/{template_id}", response_model=FlowxCountryWorkflowDetail)
def master_rename_template(
    template_id: UUID,
    body: FlowxTaskTemplateRenameRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_super_admin),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.master_update_task_template(
                db,
                template_id,
                title=body.title,
                description=body.description,
                action_steps=body.action_steps,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/master/templates/{template_id}", response_model=FlowxCountryWorkflowDetail)
def master_delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_super_admin),
):
    try:
        return FlowxCountryWorkflowDetail(**service.master_delete_task_template(db, template_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/countries/{iso2}/ensure", response_model=FlowxCountryWorkflowDetail)
def ensure_country(
    iso2: str,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        workflow = service.ensure_country_workflow(db, iso2)
        return FlowxCountryWorkflowDetail(**service.workflow_to_detail(db, workflow))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/countries/{iso2}", response_model=FlowxCountryWorkflowSummary)
def remove_country(
    iso2: str,
    force: bool = Query(False, description="Archive open student journeys and remove anyway"),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowSummary(
            **service.archive_country_workflow(db, iso2, force=force)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/countries/{iso2}", response_model=FlowxCountryWorkflowDetail)
def get_country(
    iso2: str,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(**service.get_country_workflow(db, iso2))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/countries/{iso2}/enroll", response_model=FlowxEnrollmentRead)
def enroll_student(
    iso2: str,
    body: FlowxEnrollRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.enroll_lead(
                db,
                country_hint=iso2,
                lead_id=body.lead_id,
                institution_id=body.institution_id,
                college_id=body.college_id,
                campus_id=body.campus_id,
                level_id=body.level_id,
                qualification_program_id=body.qualification_program_id,
                intake_id=body.intake_id,
                pathway_type=body.pathway_type,
                pathway_name=body.pathway_name,
                custom_pathway_name=body.custom_pathway_name,
                portal_url=body.portal_url,
                portal_username=body.portal_username,
                portal_password_hint=body.portal_password_hint,
                institutional_app_id=body.institutional_app_id,
                application_status=body.application_status,
                fee_status=body.fee_status,
                fee_amount=body.fee_amount,
                fee_currency=body.fee_currency,
                internal_target_date=body.internal_target_date,
                official_deadline=body.official_deadline,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/countries/{iso2}/destinations", response_model=FlowxCountryDestinationsResponse)
def country_destinations(
    iso2: str,
    state_id: int | None = Query(None, ge=1),
    city_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryDestinationsResponse(
            **service.list_country_destinations(
                db, iso2, state_id=state_id, city_id=city_id
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/countries/{iso2}/geography", response_model=FlowxCountryGeographyResponse)
def country_geography(
    iso2: str,
    state_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryGeographyResponse(
            **service.list_country_geography(db, iso2, state_id=state_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/journey-test-data/seed", response_model=FlowxJourneyTestSeedResponse)
def seed_journey_test_data(
    lead_id: int = Query(27, ge=1, description="Lead to attach US/CA/GB demo applications"),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_internal_admin),
):
    try:
        return FlowxJourneyTestSeedResponse(**journey_test_seed.seed_journey_test_data(db, lead_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/journey-test-data/reset", response_model=FlowxJourneyTestResetResponse)
def reset_journey_test_data(
    lead_id: int = Query(27, ge=1, description="Lead whose demo applications / FXTEST data to remove"),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_internal_admin),
):
    try:
        return FlowxJourneyTestResetResponse(**journey_test_seed.reset_journey_test_data(db, lead_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/application-lookups", response_model=FlowxApplicationLookupsResponse)
def application_lookups(
    institution_id: int | None = Query(None, ge=1),
    campus_id: int | None = Query(None, ge=1),
    college_id: int | None = Query(None, ge=1),
    level_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    return FlowxApplicationLookupsResponse(
        **service.application_lookups(
            db,
            institution_id=institution_id,
            campus_id=campus_id,
            college_id=college_id,
            level_id=level_id,
        )
    )


@router.get("/pathways", response_model=list[FlowxPathwayRead])
def list_pathways(
    pathway_type: str | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    return [FlowxPathwayRead(**row) for row in service.list_pathways(db, pathway_type=pathway_type)]


@router.post("/pathways", response_model=FlowxPathwayRead)
def create_pathway(
    body: FlowxPathwayCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxPathwayRead(
            **service.create_custom_pathway(
                db, pathway_type=body.pathway_type, pathway_name=body.pathway_name
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tracks/{track_id}/templates", response_model=FlowxCountryWorkflowDetail)
def add_template(
    track_id: UUID,
    body: FlowxTaskTemplateCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.add_task_template(
                db,
                track_id,
                title=body.title,
                description=body.description,
                action_steps=body.action_steps,
                sla_days=body.sla_days,
                parent_template_id=body.parent_template_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/templates/{template_id}", response_model=FlowxCountryWorkflowDetail)
def rename_template(
    template_id: UUID,
    body: FlowxTaskTemplateRenameRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.rename_task_template(
                db,
                template_id,
                title=body.title,
                description=body.description,
                action_steps=body.action_steps,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/process-labels", response_model=FlowxProcessLabelUpdateResponse)
def rename_process_label(
    body: FlowxProcessLabelUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxProcessLabelUpdateResponse(
            **service.rename_global_process_label(
                db, stage_key=body.stage_key, label=body.label
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/templates/{template_id}/move", response_model=FlowxCountryWorkflowDetail)
def move_template(
    template_id: UUID,
    body: FlowxTemplateMoveRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.move_task_template(
                db,
                template_id,
                target_stage_id=body.target_stage_id,
                position_index=body.position_index,
                track_name=body.track_name,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/templates/{template_id}/unlink", response_model=FlowxCountryWorkflowDetail)
def unlink_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(**service.unlink_task_template(db, template_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/templates/{template_id}", response_model=FlowxCountryWorkflowDetail)
def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(**service.delete_task_template(db, template_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates/{template_id}/usage")
def template_usage(
    template_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        count = service.count_template_student_usage(db, template_id)
        return {"template_id": str(template_id), "student_task_count": count, "in_use": count > 0}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/templates/{template_id}/relink", response_model=FlowxCountryWorkflowDetail)
def relink_template(
    template_id: UUID,
    body: FlowxTemplateRelinkRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.relink_task_template(
                db,
                template_id,
                target_stage_id=body.target_stage_id,
                track_name=body.track_name,
                position_index=body.position_index,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/templates/{template_id}/override", response_model=FlowxCountryWorkflowDetail)
def override_template(
    template_id: UUID,
    body: FlowxTemplateOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.override_task_template(
                db,
                template_id,
                actor_id=current_user.id,
                action=body.action,
                reason=body.reason,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/links", response_model=FlowxCountryWorkflowDetail)
def create_subprocess_link(
    workflow_id: UUID,
    body: FlowxSubprocessLinkCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(
            **service.link_subprocesses(
                db,
                workflow_id=workflow_id,
                from_template_id=body.from_template_id,
                to_template_id=body.to_template_id,
                link_type=body.link_type,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/links/{link_id}", response_model=FlowxCountryWorkflowDetail)
def delete_subprocess_link(
    link_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxCountryWorkflowDetail(**service.unlink_subprocess_link(db, link_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/enrollments", response_model=FlowxEnrollmentListResponse)
def list_enrollments(
    db: Session = Depends(get_db),
    country: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None),
    lead_id: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(deps.get_current_user),
):
    items, total = service.list_enrollments(
        db, country_iso2=country, status=status, q=q, lead_id=lead_id, limit=limit
    )
    return FlowxEnrollmentListResponse(items=items, total=total)


@router.get("/enrollments/{enrollment_id}", response_model=FlowxEnrollmentRead)
def get_enrollment(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(**service.get_enrollment(db, enrollment_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/enrollments/{enrollment_id}/stage", response_model=FlowxEnrollmentRead)
def patch_stage(
    enrollment_id: UUID,
    body: FlowxStageUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.update_enrollment_stage(
                db,
                enrollment_id,
                stage_key=body.current_stage_key,
                client_updated_at=body.updated_at,
            )
        )
    except ValueError as exc:
        code = 409 if "another session" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.patch("/enrollment-tracks/{track_id}/move", response_model=FlowxEnrollmentRead)
def move_enrollment_track(
    track_id: UUID,
    body: FlowxEnrollmentTrackMoveRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.move_enrollment_track(
                db,
                track_id,
                position_index=body.position_index,
                client_updated_at=body.updated_at,
            )
        )
    except ValueError as exc:
        code = 409 if "another session" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/enrollment-tracks/{track_id}/tasks", response_model=FlowxEnrollmentRead)
def add_task(
    track_id: UUID,
    body: FlowxTaskCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.create_enrollment_task(
                db,
                track_id,
                title=body.title,
                description=body.description,
                kanban_status=body.kanban_status,
                sla_due_at=body.sla_due_at,
                assigned_to=body.assigned_to,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/move", response_model=FlowxEnrollmentRead)
def move_task(
    task_id: UUID,
    body: FlowxTaskMoveRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.move_task(
                db,
                task_id,
                kanban_status=body.kanban_status,
                position_index=body.position_index,
                client_updated_at=body.updated_at,
            )
        )
    except ValueError as exc:
        code = 409 if "another session" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/checklist", response_model=FlowxEnrollmentRead)
def update_task_checklist(
    task_id: UUID,
    body: FlowxTaskChecklistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.update_task_checklist(
                db,
                task_id,
                checked=body.checked,
                confirmed_complete=body.confirmed_complete,
                steps=body.steps,
                actor_id=current_user.id,
                client_updated_at=body.updated_at,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}/reorder", response_model=FlowxEnrollmentRead)
def reorder_task(
    task_id: UUID,
    body: FlowxTaskReorderRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.reorder_enrollment_task(
                db,
                task_id,
                position_index=body.position_index,
                client_updated_at=body.updated_at,
            )
        )
    except ValueError as exc:
        code = 409 if "another session" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/enrollments/{enrollment_id}/overrides", response_model=FlowxEnrollmentRead)
def override_enrollment(
    enrollment_id: UUID,
    body: FlowxOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return FlowxEnrollmentRead(
            **service.apply_override(
                db,
                enrollment_id,
                actor_id=current_user.id,
                action_type=body.action_type,
                target_entity=body.target_entity,
                reason=body.reason,
                evidence_url=body.evidence_url,
                track_name=body.track_name,
                stage_key=body.stage_key,
                title=body.title,
                description=body.description,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/enrollments/{enrollment_id}/audit", response_model=list[FlowxAuditLogRead])
def enrollment_audit(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(deps.get_current_user),
):
    return [FlowxAuditLogRead.model_validate(row) for row in service.list_audit_logs(db, enrollment_id, limit=limit)]


@router.get("/board", response_model=FlowxBoardResponse)
def board(
    db: Session = Depends(get_db),
    country: str | None = Query(None),
    _user: User = Depends(deps.get_current_user),
):
    return FlowxBoardResponse(**service.board_by_country(db, country_iso2=country))


@router.get("/workflow-rules", response_model=list[FlowxWorkflowRuleRead])
def workflow_rules(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    return [FlowxWorkflowRuleRead.model_validate(r) for r in service.list_workflow_rules(db)]


@router.post("/workflow-rules", response_model=FlowxWorkflowRuleRead, status_code=201)
def create_workflow_rule(
    body: FlowxWorkflowRuleCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    row = service.create_workflow_rule(
        db,
        rule_name=body.rule_name,
        trigger_condition=body.trigger_condition,
        action_payload=body.action_payload,
        is_active=body.is_active,
    )
    return FlowxWorkflowRuleRead.model_validate(row)


@router.post("/jobs/evaluate-sla")
def run_sla_job(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    changed = service.evaluate_sla_breach(db)
    return {"updated": changed}


@router.post("/jobs/seed-defaults")
def seed_defaults(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
):
    created = service.seed_default_country_workflows(db)
    return {"ensured_new": created, "workflows": len(service.list_country_workflows(db))}


@router.post("/jobs/clone-canada-processes")
@router.post("/jobs/clone-master-processes")
def clone_master_processes(
    db: Session = Depends(get_db),
    _user: User = Depends(deps.require_academia_admin),
    targets: str | None = Query(
        None,
        description="Optional comma-separated ISO2 list; default = all other active countries",
    ),
):
    """Replace active country boards with the Master Workflow process tree."""
    try:
        target_list = (
            [part.strip() for part in targets.split(",") if part.strip()]
            if targets
            else None
        )
        return service.apply_source_processes_to_active_countries(
            db,
            source_iso2=service.MASTER_WORKFLOW_ISO2,
            target_iso_codes=target_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
