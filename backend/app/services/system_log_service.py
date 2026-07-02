from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.system_log import SystemLog, SystemLogLevel

logger = logging.getLogger(__name__)


def log_system_event(
    db: Session,
    *,
    level: str,
    source: str,
    message: str,
    context: dict[str, Any] | None = None,
    student_id: int | None = None,
    commit: bool = False,
) -> SystemLog:
    normalized_level = (level or "info").strip().lower()
    if normalized_level not in {item.value for item in SystemLogLevel}:
        normalized_level = SystemLogLevel.ERROR.value

    row = SystemLog(
        level=SystemLogLevel(normalized_level),
        source=source[:120],
        message=message,
        context=json.dumps(context, default=str) if context else None,
        student_id=student_id,
    )
    db.add(row)
    db.flush()

    log_line = f"[{source}] {message}"
    if context:
        log_line = f"{log_line} | {context}"
    if normalized_level == SystemLogLevel.ERROR.value:
        logger.error(log_line)
    elif normalized_level == SystemLogLevel.WARNING.value:
        logger.warning(log_line)
    else:
        logger.info(log_line)

    if commit:
        db.commit()
        db.refresh(row)
    return row
