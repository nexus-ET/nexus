from __future__ import annotations

import colorsys

from sqlalchemy.orm import Session

from app.models.education_major import EducationMajor

MAJOR_COLOR_PALETTE: tuple[str, ...] = (
    "#6366F1",
    "#8B5CF6",
    "#EC4899",
    "#F43F5E",
    "#F97316",
    "#EAB308",
    "#22C55E",
    "#14B8A6",
    "#06B6D4",
    "#3B82F6",
    "#A855F7",
    "#84CC16",
)


def _hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    red, green, blue = colorsys.hls_to_rgb(hue / 360, lightness / 100, saturation / 100)
    return "#{:02X}{:02X}{:02X}".format(
        int(red * 255),
        int(green * 255),
        int(blue * 255),
    )


def _used_major_colors(db: Session, *, exclude_id: int | None = None) -> set[str]:
    query = db.query(EducationMajor.color).filter(EducationMajor.color.isnot(None))
    if exclude_id is not None:
        query = query.filter(EducationMajor.id != exclude_id)
    return {row.color.upper() for row in query.all() if row.color}


def _generate_unique_color(
    used: set[str],
    *,
    label: str,
    major_count: int,
) -> str:
    seed = sum(ord(char) for char in (label or "").strip().lower()) or 1
    for attempt in range(360):
        hue = (seed * 47 + major_count * 29 + attempt * 41) % 360
        color = _hsl_to_hex(hue, 62, 50)
        if color not in used:
            return color
    return _hsl_to_hex((seed * 17) % 360, 62, 50)


def assign_major_color(db: Session, *, label: str, exclude_id: int | None = None) -> str:
    used = _used_major_colors(db, exclude_id=exclude_id)
    for color in MAJOR_COLOR_PALETTE:
        normalized = color.upper()
        if normalized not in used:
            return color
    major_count = db.query(EducationMajor).count()
    return _generate_unique_color(used, label=label, major_count=major_count)


def ensure_major_color(
    db: Session,
    record: EducationMajor,
    *,
    preferred_color: str | None = None,
) -> str:
    if record.color:
        return record.color
    if preferred_color:
        record.color = preferred_color
        return preferred_color
    color = assign_major_color(db, label=record.label, exclude_id=record.id)
    record.color = color
    return color
