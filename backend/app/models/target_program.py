from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class TargetProgram(Base):
    """Framework major / discipline umbrella (e.g. Engineering & Technology)."""

    __tablename__ = "target_programs"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    program = relationship("Program", back_populates="majors")
    courses = relationship(
        "TargetCourse",
        back_populates="program",
        cascade="all, delete-orphan",
    )

    @property
    def degree(self):
        """Backward-compatible alias for parent qualification program."""
        return self.program

    @property
    def degree_id(self):
        return self.program_id
