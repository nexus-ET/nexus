from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.db.database import get_db
from app.models.user import User
from app.schemas.command_center import (
    OperationalPulseResponse,
    PipelineBoardResponse,
    PipelineCardOut,
    PipelineMoveRequest,
    TaskItemOut,
    TasksResponse,
)
from app.services import command_center_service
from app.services.audit_service import log_action
from app.services.websocket_service import broadcast_nexus_event

router = APIRouter()


@router.get("/command-center/pulse", response_model=OperationalPulseResponse)
@router.get("/command-center/pulse/", response_model=OperationalPulseResponse)
def read_operational_pulse(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    return OperationalPulseResponse(**command_center_service.get_operational_pulse(db))


@router.get("/command-center/pipeline", response_model=PipelineBoardResponse)
@router.get("/command-center/pipeline/", response_model=PipelineBoardResponse)
def read_pipeline_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    board = command_center_service.get_pipeline_board(db)
    columns = {
        stage: [PipelineCardOut(**card) for card in cards]
        for stage, cards in board["columns"].items()
    }
    return PipelineBoardResponse(stages=board["stages"], columns=columns)


@router.get("/command-center/tasks", response_model=TasksResponse)
@router.get("/command-center/tasks/", response_model=TasksResponse)
def read_open_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_counselling_admin),
):
    tasks = command_center_service.list_open_tasks(db)
    return TasksResponse(tasks=[TaskItemOut(**task) for task in tasks])


@router.post("/command-center/pipeline/move")
@router.post("/command-center/pipeline/move/", response_model=PipelineCardOut)
@log_action("move_pipeline_candidate", "lead")
def move_pipeline_card(
    request: Request,
    payload: PipelineMoveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_counselling_admin),
):
    lead = command_center_service.move_pipeline_candidate(
        db,
        lead_id=payload.lead_id,
        stage=payload.stage,
        counsellor_id=current_user.id,
    )
    card = {
        "lead_id": lead.id,
        "full_name": lead.full_name,
        "email": lead.email,
        "phone_number": lead.phone_number,
        "admission_stage": lead.admission_stage or payload.stage,
        "assigned_advisor_id": lead.assigned_advisor_id,
        "is_stalled": False,
        "latest_booking_id": None,
        "updated_at": lead.updated_at,
    }
    background_tasks.add_task(
        broadcast_nexus_event,
        "pipeline.updated",
        {"lead_id": lead.id, "stage": lead.admission_stage, "card": card},
    )
    return PipelineCardOut(**card)
