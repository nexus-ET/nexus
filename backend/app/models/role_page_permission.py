from sqlalchemy import Boolean, Column, ForeignKey, Integer, UniqueConstraint

from app.db.database import Base


class RolePagePermission(Base):
    __tablename__ = "role_page_permissions"
    __table_args__ = (
        UniqueConstraint("admin_role_id", "navigation_page_id", name="uq_role_page_permission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    admin_role_id = Column(Integer, ForeignKey("admin_roles.id"), nullable=False, index=True)
    navigation_page_id = Column(Integer, ForeignKey("navigation_pages.id"), nullable=False, index=True)
    can_access = Column(Boolean, default=False, nullable=False)
