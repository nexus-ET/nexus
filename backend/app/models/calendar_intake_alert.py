from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from app.db.database import Base


class CalendarIntakeAlertLog(Base):
    """Tracks calendar intake reminder alerts to prevent duplicate notifications."""

    __tablename__ = "calendar_intake_alert_logs"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "entity_type",
            "entity_id",
            "term_name",
            "year",
            "alert_type",
            name="uq_calendar_intake_alert_scope",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(Integer, nullable=False)
    term_name = Column(String(120), nullable=False)
    year = Column(Integer, nullable=False)
    alert_type = Column(String(40), nullable=False, default="missing_intake")
    alerted_at = Column(DateTime, server_default=func.now(), nullable=False)
