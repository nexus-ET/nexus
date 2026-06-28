from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import cast, String, func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.models.agent_config import AgentConfig
from app.models.lead import Lead
from app.models.user import User
from app.schemas.agent import AgentConfigRead, AgentConfigUpdate, AiModelOptionRead, StaffMemberRead
from app.schemas.user import StatusChangeReasonRead
from app.services.admin_roles import get_active_admin_role_ids
from app.services.agent_runtime import get_or_create_agent_config, update_agent_config
from app.services.ai_providers import list_ai_model_options

router = APIRouter()

ADVISOR_ROLE_NAMES = {"Student Advisor", "Student Manager"}


def _role_label(role_name: str | None) -> str:
    if not role_name:
        return "Staff"
    return role_name


def _active_lead_filter():
    return or_(
        cast(Lead.stage, String).ilike("%HANDOFF%"),
        cast(Lead.stage, String).ilike("%AI_ACTIVE%"),
    )


@router.get("/config", response_model=AgentConfigRead)
@router.get("/config/", response_model=AgentConfigRead)
def get_agent_config(db: Session = Depends(get_db)):
    return get_or_create_agent_config(db)


@router.get("/models", response_model=list[AiModelOptionRead])
@router.get("/models/", response_model=list[AiModelOptionRead])
def get_agent_model_options():
    return list_ai_model_options()


@router.post("/config", response_model=AgentConfigRead)
@router.post("/config/", response_model=AgentConfigRead)
def save_agent_config(payload: AgentConfigUpdate, db: Session = Depends(get_db)):
    return update_agent_config(db, payload.model_dump())


@router.get("/staff", response_model=List[StaffMemberRead])
@router.get("/staff/", response_model=List[StaffMemberRead])
def get_agent_staff(db: Session = Depends(get_db)):
    staff_role_ids = get_active_admin_role_ids(db)
    users = (
        db.query(User)
        .options(
            joinedload(User.deactivation_reason_ref),
            joinedload(User.admin_role_ref),
        )
        .filter(
            or_(
                User.admin_role_id.in_(staff_role_ids),
                User.is_superuser.is_(True),
            )
        )
        .order_by(User.id.asc())
        .all()
    )

    lead_counts = dict(
        db.query(Lead.assigned_advisor_id, func.count(Lead.id))
        .filter(
            Lead.assigned_advisor_id.isnot(None),
            _active_lead_filter(),
            cast(Lead.stage, String).not_ilike("%ARCHIVE%"),
        )
        .group_by(Lead.assigned_advisor_id)
        .all()
    )

    shared_handoff_count = (
        db.query(func.count(Lead.id))
        .filter(
            _active_lead_filter(),
            cast(Lead.stage, String).not_ilike("%ARCHIVE%"),
            Lead.is_human_locked.is_(True),
            Lead.assigned_advisor_id.is_(None),
        )
        .scalar()
        or 0
    )

    response: list[StaffMemberRead] = []
    for user in users:
        assigned_count = lead_counts.get(user.id, 0)
        role_name = user.admin_role_ref.name if user.admin_role_ref else (
            "Super Admin" if user.is_superuser else "Staff"
        )
        if assigned_count == 0 and role_name in ADVISOR_ROLE_NAMES and shared_handoff_count > 0:
            assigned_count = shared_handoff_count

        deactivation_detail = None
        if user.deactivation_reason_ref:
            deactivation_detail = StatusChangeReasonRead.model_validate(
                user.deactivation_reason_ref
            )

        response.append(
            StaffMemberRead(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=role_name,
                role_label=_role_label(role_name),
                is_active=bool(user.is_active),
                lead_count=assigned_count,
                creation_reason=user.creation_reason,
                creation_date=user.creation_date,
                deactivation_reason=user.deactivation_reason,
                deactivation_date=user.deactivation_date,
                activation_reason=user.activation_reason,
                activation_date=user.activation_date,
                deactivation_reason_detail=deactivation_detail,
            )
        )

    return response
