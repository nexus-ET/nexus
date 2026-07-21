from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.program import Program

# Legacy target_programs seed defaults — codes must exist in programs (added via UI).
MAJOR_DEFAULT_PROGRAM_CODE: dict[str, str] = {
    "BUSINESS_MANAGEMENT": "BBA",
    "NURSING_MIDWIFERY": "MSN",
    "ALLIED_HEALTH": "BSC_BIO",
    "MEDICINE_DENTISTRY": "MBBS",
    "MEDICAL_SCIENCES": "MSC_BIO",
    "ENGINEERING_TECHNOLOGY": "BENG",
    "COMPUTER_SCIENCE_IT": "BSC_CS",
    "HUMANITIES_SOCIAL_SCIENCES": "BA_PSYCH",
    "LAW_LEGAL_STUDIES": "LLB",
    "NATURAL_SCIENCES": "BSC_BIO",
}


def get_academic_program_by_code(db: Session, code: str) -> Program | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    return db.query(Program).filter(Program.code == normalized).first()


def seed_academic_programs(db: Session) -> None:
    """Programs are managed via Academia Hub UI (Level → Major → Program)."""
    return
