from pydantic import BaseModel, Field


class NavigationPageRead(BaseModel):
    id: int
    name: str
    route: str
    icon: str | None = None
    sort_order: int = 0
    is_active: bool = True

    class Config:
        from_attributes = True


class RolePermissionItem(BaseModel):
    navigation_page_id: int
    route: str
    name: str
    can_access: bool


class RolePermissionsRead(BaseModel):
    role: str
    admin_role_id: int
    permissions: list[RolePermissionItem]


class PermissionUpdate(BaseModel):
    role: str = Field(min_length=1)
    navigation_page_id: int = Field(gt=0)
    can_access: bool


class MyRolePermissionsRead(BaseModel):
    role: str | None = None
    admin_role_id: int | None = None
    allowed_routes: list[str]
