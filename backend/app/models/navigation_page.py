from sqlalchemy import Boolean, Column, Integer, String

from app.db.database import Base


class NavigationPage(Base):
    __tablename__ = "navigation_pages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    route = Column(String(255), unique=True, nullable=False, index=True)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
