from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.database import get_db
from app.models.navigation_page import NavigationPage
from app.models.role_page_permission import RolePagePermission
from app.models.user import User
from app.schemas.rbac import (
    MyRolePermissionsRead,
    NavigationPageRead,
    PermissionUpdate,
    RolePermissionItem,
    RolePermissionsRead,
)
from app.services.admin_roles import get_active_admin_roles
from app.services.navigation_rbac import (
    get_admin_role_by_name,
    get_allowed_routes_for_user,
    upsert_role_page_permission,
)

router = APIRouter()


def _require_super_admin(current_user: User = Depends(deps.get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Super Admin access required.")
    return current_user


@router.get("/pages", response_model=List[NavigationPageRead])
@router.get("/pages/", response_model=List[NavigationPageRead])
def list_navigation_pages(db: Session = Depends(get_db)):
    return (
        db.query(NavigationPage)
        .filter(NavigationPage.is_active.is_(True))
        .order_by(NavigationPage.sort_order.asc(), NavigationPage.id.asc())
        .all()
    )


@router.get("/permissions/my-role", response_model=MyRolePermissionsRead)
@router.get("/permissions/my-role/", response_model=MyRolePermissionsRead)
def get_my_role_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    user = (
        db.query(User)
        .options(joinedload(User.admin_role_ref))
        .filter(User.id == current_user.id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    return MyRolePermissionsRead(
        role=user.admin_role_ref.name if user.admin_role_ref else None,
        admin_role_id=user.admin_role_id,
        allowed_routes=get_allowed_routes_for_user(db, user),
    )


@router.get("/permissions/{role}", response_model=RolePermissionsRead)
@router.get("/permissions/{role}/", response_model=RolePermissionsRead)
def get_role_permissions(
    role: str,
    db: Session = Depends(get_db),
    _: User = Depends(_require_super_admin),
):
    role_record = get_admin_role_by_name(db, role)
    if not role_record:
        raise HTTPException(status_code=404, detail=f"Role '{role}' not found.")

    pages = (
        db.query(NavigationPage)
        .filter(NavigationPage.is_active.is_(True))
        .order_by(NavigationPage.sort_order.asc(), NavigationPage.id.asc())
        .all()
    )
    permission_map = {
        perm.navigation_page_id: perm.can_access
        for perm in db.query(RolePagePermission)
        .filter(RolePagePermission.admin_role_id == role_record.id)
        .all()
    }

    return RolePermissionsRead(
        role=role_record.name,
        admin_role_id=role_record.id,
        permissions=[
            RolePermissionItem(
                navigation_page_id=page.id,
                route=page.route,
                name=page.name,
                can_access=permission_map.get(page.id, False),
            )
            for page in pages
        ],
    )


@router.post("/permissions", response_model=RolePermissionItem)
@router.post("/permissions/", response_model=RolePermissionItem)
def update_role_permission(
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(_require_super_admin),
):
    role_record = get_admin_role_by_name(db, payload.role)
    if not role_record:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    page = (
        db.query(NavigationPage)
        .filter(
            NavigationPage.id == payload.navigation_page_id,
            NavigationPage.is_active.is_(True),
        )
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Navigation page not found.")

    upsert_role_page_permission(
        db,
        admin_role_id=role_record.id,
        navigation_page_id=page.id,
        can_access=payload.can_access,
    )

    return RolePermissionItem(
        navigation_page_id=page.id,
        route=page.route,
        name=page.name,
        can_access=payload.can_access,
    )


@router.get("/roles", response_model=list)
def list_roles_for_rbac(
    db: Session = Depends(get_db),
    _: User = Depends(_require_super_admin),
):
    return [
        {"id": role.id, "name": role.name, "is_superuser": role.is_superuser}
        for role in get_active_admin_roles(db)
    ]
