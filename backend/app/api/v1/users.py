import traceback
from app.utils.timezone import utc_now
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func

from app.db.database import get_db
from app.api import deps
from app.models.user import User as UserModel
from app.models.status_change_reason import StatusChangeReason
from app.models.admin_role import AdminRole as AdminRoleModel
from app.models.lead import Lead
from app.models.note import Note
from app.models.client import Client
from app.schemas.user import (
    User as UserSchema,
    UserCreate,
    UserUpdate,
    UserStatusChange,
    UserProfileUpdate,
    ChangePasswordRequest,
    StatusChangeReasonRead,
    StatusChangeReasonType,
    AdminRoleRead,
)
from app.schemas.student_aspirations import (
    StudentAspirationsResponse,
    StudentAspirationsSaveRequest,
)
from app.services.student_aspirations_service import get_user_aspirations, save_user_aspirations
from app.core.security import get_password_hash, verify_password
from app.services.email_service import notify_super_admins_of_deactivation
from app.services.status_change_reasons import (
    ensure_initial_activation_reason,
    get_activate_reason,
    get_create_reason,
    get_reason_by_type,
)
from app.services.admin_roles import (
    get_active_admin_roles,
    get_active_admin_role_ids,
    get_admin_role_by_id,
    get_default_admin_role,
)

router = APIRouter()


def _admin_user_filter(db: Session):
    role_ids = get_active_admin_role_ids(db)
    return or_(
        UserModel.admin_role_id.in_(role_ids),
        UserModel.is_superuser.is_(True),
    )


def _resolve_admin_role(db: Session, admin_role_id: int | None) -> AdminRoleModel:
    if admin_role_id:
        role_record = get_admin_role_by_id(db, admin_role_id)
        if not role_record:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid admin role id: {admin_role_id}",
            )
        return role_record

    default_role = get_default_admin_role(db)
    if not default_role:
        raise HTTPException(
            status_code=500,
            detail="No admin roles configured. Contact a system administrator.",
        )
    return default_role


def _apply_admin_role(user: UserModel, db: Session, admin_role_id: int | None) -> None:
    role_record = _resolve_admin_role(db, admin_role_id)
    user.admin_role_id = role_record.id
    user.is_superuser = role_record.is_superuser


def _user_load_options():
    return (
        joinedload(UserModel.admin_role_ref),
        joinedload(UserModel.creation_reason_ref),
        joinedload(UserModel.deactivation_reason_ref),
        joinedload(UserModel.activation_reason_ref),
    )


def _serialize_user(user: UserModel) -> dict:
    admin_role = (
        AdminRoleRead.model_validate(user.admin_role_ref)
        if user.admin_role_ref
        else None
    )
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "admin_role_id": user.admin_role_id,
        "admin_role": admin_role,
        "role": admin_role.name if admin_role else None,
        "creation_reason": user.creation_reason,
        "creation_date": user.creation_date,
        "deactivation_reason": user.deactivation_reason,
        "deactivation_date": user.deactivation_date,
        "activation_reason": user.activation_reason,
        "activation_date": user.activation_date,
        "creation_reason_detail": (
            StatusChangeReasonRead.model_validate(user.creation_reason_ref)
            if user.creation_reason_ref
            else None
        ),
        "deactivation_reason_detail": (
            StatusChangeReasonRead.model_validate(user.deactivation_reason_ref)
            if user.deactivation_reason_ref
            else None
        ),
        "activation_reason_detail": (
            StatusChangeReasonRead.model_validate(user.activation_reason_ref)
            if user.activation_reason_ref
            else None
        ),
    }


def _get_admin_user_or_404(user_id: int, db: Session) -> UserModel:
    user = (
        db.query(UserModel)
        .options(*_user_load_options())
        .filter(UserModel.id == user_id, _admin_user_filter(db))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Admin user not found.")
    return user


def _format_user_name(user: UserModel) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.email


def _role_display_name(user: UserModel) -> str:
    if user.admin_role_ref:
        return user.admin_role_ref.name
    return "Web Admin"


def _now_utc_naive() -> datetime:
    return utc_now()


def _validate_status_reason(
    db: Session,
    reason_id: int,
    reason_type: str,
) -> StatusChangeReason:
    reason = get_reason_by_type(db, reason_type, reason_id=reason_id)
    if not reason:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {reason_type.lower()} reason selected.",
        )
    return reason


def _apply_creation(user: UserModel, reason_id: int) -> None:
    user.creation_reason = reason_id
    user.creation_date = _now_utc_naive()


def _apply_deactivation(user: UserModel, reason_id: int) -> None:
    user.deactivation_reason = reason_id
    user.deactivation_date = _now_utc_naive()


def _apply_activation(user: UserModel, reason_id: int) -> None:
    user.activation_reason = reason_id
    user.activation_date = _now_utc_naive()


def _backfill_user_lifecycle_fields(user: UserModel, db: Session) -> bool:
    """Fill missing create/activate metadata for legacy accounts. Returns True if changed."""
    changed = False

    if user.creation_date is None or user.creation_reason is None:
        create_reason = get_create_reason(db)
        if create_reason and user.creation_reason is None:
            user.creation_reason = create_reason.id
            changed = True
        if user.creation_date is None:
            # Prefer an existing activation timestamp; otherwise record backfill time.
            user.creation_date = user.activation_date or _now_utc_naive()
            changed = True

    if user.is_active and (user.activation_date is None or user.activation_reason is None):
        activate_reason = ensure_initial_activation_reason(db) or get_activate_reason(db)
        if activate_reason and user.activation_reason is None:
            user.activation_reason = activate_reason.id
            changed = True
        if user.activation_date is None:
            user.activation_date = user.creation_date or _now_utc_naive()
            changed = True

    return changed


def _remaining_super_admin_count(db: Session, exclude_user_id: int) -> int:
    super_admin_role_ids = [
        role.id
        for role in db.query(AdminRoleModel)
        .filter(AdminRoleModel.is_superuser.is_(True), AdminRoleModel.is_active.is_(True))
        .all()
    ]
    return (
        db.query(UserModel)
        .filter(
            UserModel.id != exclude_user_id,
            _admin_user_filter(db),
            or_(
                UserModel.is_superuser.is_(True),
                UserModel.admin_role_id.in_(super_admin_role_ids),
            ),
        )
        .count()
    )


def _delete_admin_user_record(db: Session, user: UserModel) -> None:
    user_id = user.id
    db.query(Note).filter(Note.owner_id == user_id).delete(synchronize_session=False)
    db.query(Client).filter(Client.owner_id == user_id).delete(synchronize_session=False)
    db.query(Lead).filter(Lead.assigned_advisor_id == user_id).update(
        {Lead.assigned_advisor_id: None},
        synchronize_session=False,
    )
    db.delete(user)


@router.get("/me", response_model=UserSchema)
@router.get("/me/", response_model=UserSchema)
def read_current_user(
    current_user: UserModel = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(UserModel)
        .options(*_user_load_options())
        .filter(UserModel.id == current_user.id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if _backfill_user_lifecycle_fields(user, db):
        db.commit()
        user = (
            db.query(UserModel)
            .options(*_user_load_options())
            .filter(UserModel.id == current_user.id)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
    return _serialize_user(user)


@router.patch("/me/profile", response_model=UserSchema)
@router.patch("/me/profile/", response_model=UserSchema)
def update_my_profile(
    payload: UserProfileUpdate,
    current_user: UserModel = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(UserModel)
        .options(*_user_load_options())
        .filter(UserModel.id == current_user.id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.phone_number is not None:
        cleaned = payload.phone_number.strip()
        user.phone_number = cleaned or None

    db.commit()
    refreshed = (
        db.query(UserModel)
        .options(*_user_load_options())
        .filter(UserModel.id == user.id)
        .first()
    )
    return _serialize_user(refreshed)


@router.get("/me/aspirations", response_model=StudentAspirationsResponse)
@router.get("/me/aspirations/", response_model=StudentAspirationsResponse)
def read_my_aspirations(
    current_user: UserModel = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    return get_user_aspirations(db, current_user)


@router.put("/me/aspirations", response_model=StudentAspirationsResponse)
@router.put("/me/aspirations/", response_model=StudentAspirationsResponse)
def save_my_aspirations(
    payload: StudentAspirationsSaveRequest,
    current_user: UserModel = Depends(deps.get_current_active_user),
    db: Session = Depends(get_db),
):
    return save_user_aspirations(db, current_user, payload)


@router.post("/me/change-password")
@router.post("/me/change-password/")
def change_my_password(
    payload: ChangePasswordRequest,
    current_user: UserModel = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


@router.get("/admin-roles", response_model=List[AdminRoleRead])
@router.get("/admin-roles/", response_model=List[AdminRoleRead])
def list_admin_roles(db: Session = Depends(get_db)):
    return get_active_admin_roles(db)


@router.get("/status-change-reasons", response_model=List[StatusChangeReasonRead])
@router.get("/status-change-reasons/", response_model=List[StatusChangeReasonRead])
def list_status_change_reasons(
    reason_type: StatusChangeReasonType = Query(...),
    db: Session = Depends(get_db),
):
    return (
        db.query(StatusChangeReason)
        .filter(
            StatusChangeReason.reason_type == reason_type,
            StatusChangeReason.is_active.is_(True),
        )
        .order_by(StatusChangeReason.id.asc())
        .all()
    )


@router.get("", response_model=List[UserSchema])
@router.get("/", response_model=List[UserSchema])
def list_admin_users(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = (
        db.query(UserModel)
        .options(*_user_load_options())
        .filter(_admin_user_filter(db))
    )
    if not include_inactive:
        query = query.filter(UserModel.is_active.is_(True))
    users = query.order_by(UserModel.id.desc()).all()
    return [_serialize_user(user) for user in users]


@router.post("", response_model=UserSchema)
@router.post("/", response_model=UserSchema)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    user = (
        db.query(UserModel)
        .filter(func.lower(UserModel.email) == user_in.email.lower())
        .first()
    )
    if user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists in the system.",
        )

    create_reason = get_create_reason(db)
    if not create_reason:
        raise HTTPException(
            status_code=500,
            detail="Create status reason is not configured. Contact a system administrator.",
        )

    try:
        db_user = UserModel(
            email=user_in.email,
            hashed_password=get_password_hash(user_in.password),
            first_name=user_in.first_name.strip(),
            last_name=user_in.last_name.strip(),
            phone_number=user_in.phone_number.strip(),
            is_active=user_in.is_active if user_in.is_active is not None else True,
            is_superuser=False,
        )
        _apply_admin_role(db_user, db, user_in.admin_role_id)
        _apply_creation(db_user, create_reason.id)
        if db_user.is_active:
            activate_reason = ensure_initial_activation_reason(db) or get_activate_reason(db)
            if not activate_reason:
                raise HTTPException(
                    status_code=500,
                    detail="Activate status reason is not configured. Contact a system administrator.",
                )
            _apply_activation(db_user, activate_reason.id)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return _serialize_user(_get_admin_user_or_404(db_user.id, db))
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print("--- DATABASE ERROR TRACEBACK ---")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create admin user: {str(e)}",
        )


@router.patch("/{user_id}", response_model=UserSchema)
def update_admin_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    user = _get_admin_user_or_404(user_id, db)

    if user_in.email and user_in.email.lower() != user.email.lower():
        existing = (
            db.query(UserModel)
            .filter(func.lower(UserModel.email) == user_in.email.lower())
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email is already in use.")

    update_data = user_in.model_dump(exclude_unset=True)
    password = update_data.pop("password", None)
    admin_role_id = update_data.pop("admin_role_id", None)

    if "phone_number" in update_data:
        update_data["phone_number"] = (update_data.get("phone_number") or "").strip() or None

    for field, value in update_data.items():
        setattr(user, field, value)

    if admin_role_id is not None:
        _apply_admin_role(user, db, admin_role_id)

    if password:
        user.hashed_password = get_password_hash(password)

    db.commit()
    return _serialize_user(_get_admin_user_or_404(user_id, db))


@router.patch("/{user_id}/deactivate", response_model=UserSchema)
def deactivate_admin_user(
    user_id: int,
    payload: UserStatusChange,
    db: Session = Depends(get_db),
):
    user = _get_admin_user_or_404(user_id, db)

    if not user.is_active:
        raise HTTPException(status_code=400, detail="This user is already deactivated.")

    reason = _validate_status_reason(db, payload.status_change_reason_id, "Deactivate")

    user.is_active = False
    _apply_deactivation(user, reason.id)

    super_admin_role_ids = [
        role.id
        for role in db.query(AdminRoleModel)
        .filter(AdminRoleModel.is_superuser.is_(True), AdminRoleModel.is_active.is_(True))
        .all()
    ]

    super_admin_emails = [
        admin.email
        for admin in db.query(UserModel)
        .filter(
            UserModel.is_active.is_(True),
            or_(
                UserModel.is_superuser.is_(True),
                UserModel.admin_role_id.in_(super_admin_role_ids),
            ),
        )
        .all()
        if admin.email
    ]

    db.commit()

    notify_super_admins_of_deactivation(
        deactivated_user_name=_format_user_name(user),
        deactivated_user_email=user.email,
        deactivated_user_role=_role_display_name(user),
        reason=reason.reason,
        reason_description=reason.description,
        super_admin_emails=super_admin_emails,
    )

    return _serialize_user(_get_admin_user_or_404(user_id, db))


@router.patch("/{user_id}/activate", response_model=UserSchema)
def activate_admin_user(
    user_id: int,
    payload: UserStatusChange,
    db: Session = Depends(get_db),
):
    user = _get_admin_user_or_404(user_id, db)

    if user.is_active:
        raise HTTPException(status_code=400, detail="This user is already active.")

    reason = _validate_status_reason(db, payload.status_change_reason_id, "Activate")

    user.is_active = True
    _apply_activation(user, reason.id)

    db.commit()
    return _serialize_user(_get_admin_user_or_404(user_id, db))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(deps.require_super_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    user = _get_admin_user_or_404(user_id, db)

    if user.is_superuser and _remaining_super_admin_count(db, user_id) == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last Super Admin account.",
        )

    try:
        _delete_admin_user_record(db, user)
        db.commit()
    except Exception as e:
        db.rollback()
        print("--- DATABASE ERROR TRACEBACK ---")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete admin user: {str(e)}",
        ) from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)
